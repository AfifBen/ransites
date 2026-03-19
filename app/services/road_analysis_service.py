import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    from shapely.geometry import LineString, MultiLineString, Point, Polygon, shape
    from shapely.ops import nearest_points, transform
    from pyproj import CRS, Transformer
    _GEO_LIBS_AVAILABLE = True
except ModuleNotFoundError:
    LineString = MultiLineString = Point = Polygon = object
    shape = nearest_points = transform = None
    CRS = Transformer = None
    _GEO_LIBS_AVAILABLE = False

from app.models import Sector, Site


DEFAULT_MAX_SITES = 200
DEFAULT_BEAM_WIDTH_DEG = 60.0
DEFAULT_BEAM_LENGTH_M = 1000.0
DEFAULT_SITE_DISTANCE_M = 5000.0


@dataclass
class RoadAnalysisResult:
    road_id: int
    road_name: str
    site_rows: List[Dict[str, Any]]
    sector_rows: List[Dict[str, Any]]
    total_sites: int
    total_sectors: int


def ensure_geo_libs_available():
    if _GEO_LIBS_AVAILABLE:
        return
    raise RuntimeError(
        "Road analysis requires optional dependencies 'shapely' and 'pyproj'. "
        "Install them with: pip install shapely pyproj"
    )


def _normalize_linestring(geom_obj):
    if isinstance(geom_obj, LineString):
        return geom_obj
    if isinstance(geom_obj, MultiLineString):
        return geom_obj
    raise ValueError("Road geometry must be LineString or MultiLineString.")


def parse_road_geometry(road_geojson: str):
    ensure_geo_libs_available()
    if not road_geojson:
        raise ValueError("Road geometry is empty.")
    try:
        data = json.loads(road_geojson)
        geom = shape(data)
        return _normalize_linestring(geom)
    except Exception as exc:
        raise ValueError(f"Invalid road geometry JSON: {exc}") from exc


def _project_to_metric(point_wgs84: Point, line_wgs84):
    ensure_geo_libs_available()
    # Use local Azimuthal Equidistant projection centered on the site point.
    # This avoids fragile dynamic EPSG generation and keeps metric precision locally.
    src = CRS.from_epsg(4326)
    local_metric = CRS.from_proj4(
        f"+proj=aeqd +lat_0={point_wgs84.y} +lon_0={point_wgs84.x} +datum=WGS84 +units=m +no_defs"
    )
    tx = Transformer.from_crs(src, local_metric, always_xy=True)
    to_wgs = Transformer.from_crs(local_metric, src, always_xy=True)
    point_m = transform(tx.transform, point_wgs84)
    line_m = transform(tx.transform, line_wgs84)
    return point_m, line_m, to_wgs


def _iter_segments(road_m):
    if isinstance(road_m, LineString):
        lines = [road_m]
    elif isinstance(road_m, MultiLineString):
        lines = list(road_m.geoms)
    else:
        lines = []
    for line in lines:
        coords = list(line.coords)
        for i in range(1, len(coords)):
            a = coords[i - 1]
            b = coords[i]
            yield a, b


def _iter_lines(road_m):
    if isinstance(road_m, LineString):
        return [road_m]
    if isinstance(road_m, MultiLineString):
        return list(road_m.geoms)
    return []


def _beam_polygon_metric(site_m: Point, azimuth_deg: float, beam_width_deg: float = 40.0, radius_m: float = 1000.0):
    half = float(beam_width_deg) / 2.0
    start = float(azimuth_deg) - half
    end = float(azimuth_deg) + half
    steps = 24
    pts = [(site_m.x, site_m.y)]
    for i in range(steps + 1):
        b = start + ((end - start) * i / steps)
        x, y = _point_from_bearing_xy(site_m.x, site_m.y, b, float(radius_m))
        pts.append((x, y))
    pts.append((site_m.x, site_m.y))
    return Polygon(pts)


def _center_point_on_clipped_road(clipped_geom):
    if clipped_geom is None or clipped_geom.is_empty:
        return None
    gt = getattr(clipped_geom, "geom_type", "")
    if gt == "LineString":
        return clipped_geom.interpolate(clipped_geom.length / 2.0)
    if gt == "MultiLineString":
        geoms = list(clipped_geom.geoms)
        if not geoms:
            return None
        longest = max(geoms, key=lambda g: float(g.length))
        return longest.interpolate(longest.length / 2.0)
    if gt == "Point":
        return clipped_geom
    if gt == "MultiPoint":
        pts = list(clipped_geom.geoms)
        return pts[0] if pts else None
    if gt == "GeometryCollection":
        # Prefer line center; fallback to point.
        lines = [g for g in clipped_geom.geoms if getattr(g, "geom_type", "") in {"LineString", "MultiLineString"}]
        if lines:
            return _center_point_on_clipped_road(lines[0])
        points = [g for g in clipped_geom.geoms if getattr(g, "geom_type", "") in {"Point", "MultiPoint"}]
        if points:
            return _center_point_on_clipped_road(points[0])
    return None


def _bearing_from_xy(x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return 0.0
    return (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0


def _point_from_bearing_xy(x, y, bearing_deg, distance_m):
    rad = math.radians(float(bearing_deg))
    # Bearing is clockwise from North.
    return (x + (distance_m * math.sin(rad)), y + (distance_m * math.cos(rad)))


def _extract_points_from_geom(geom):
    pts = []
    if geom is None or geom.is_empty:
        return pts
    gt = getattr(geom, "geom_type", "")
    if gt == "Point":
        pts.append(geom)
    elif gt == "MultiPoint":
        pts.extend(list(geom.geoms))
    elif gt == "LineString":
        coords = list(geom.coords)
        if coords:
            pts.append(Point(coords[0][0], coords[0][1]))
            if len(coords) > 1:
                pts.append(Point(coords[-1][0], coords[-1][1]))
    elif gt in {"MultiLineString", "GeometryCollection"}:
        for g in geom.geoms:
            pts.extend(_extract_points_from_geom(g))
    return pts


def _intersection_candidates_on_ray(site_m: Point, road_geom, bearing_deg: float, ray_length_m: float = 2500.0):
    x2, y2 = _point_from_bearing_xy(site_m.x, site_m.y, bearing_deg, ray_length_m)
    ray = LineString([(site_m.x, site_m.y), (x2, y2)])
    inter = road_geom.intersection(ray)
    candidates = _extract_points_from_geom(inter)
    out = []
    for p in candidates:
        d = float(site_m.distance(p))
        if d < 1e-6:
            continue
        out.append((p, d))
    out.sort(key=lambda x: x[1])
    return out


def _point_to_segment_projection(px, py, ax, ay, bx, by):
    vx = bx - ax
    vy = by - ay
    vv = (vx * vx) + (vy * vy)
    if vv == 0:
        return ax, ay, 0.0
    t = ((px - ax) * vx + (py - ay) * vy) / vv
    proj_x = ax + t * vx
    proj_y = ay + t * vy
    return proj_x, proj_y, t


def road_distance_metrics(site_lon: float, site_lat: float, road_line_wgs84) -> Dict[str, Any]:
    ensure_geo_libs_available()
    site_point = Point(float(site_lon), float(site_lat))
    site_m, road_m, to_wgs = _project_to_metric(site_point, road_line_wgs84)
    nearest_on_road_m = nearest_points(site_m, road_m)[1]
    min_distance_m = float(site_m.distance(nearest_on_road_m))
    nearest_wgs = transform(to_wgs.transform, nearest_on_road_m)

    px, py = site_m.x, site_m.y
    best_seg_dist = None
    best_proj_line = None
    for (ax, ay), (bx, by) in _iter_segments(road_m):
        proj_x, proj_y, t = _point_to_segment_projection(px, py, ax, ay, bx, by)
        t_clamped = max(0.0, min(1.0, t))
        seg_x = ax + (bx - ax) * t_clamped
        seg_y = ay + (by - ay) * t_clamped
        dist_seg = math.hypot(px - seg_x, py - seg_y)
        if best_seg_dist is None or dist_seg < best_seg_dist:
            best_seg_dist = dist_seg
            best_proj_line = (proj_x, proj_y)

    if best_proj_line is None:
        perp_point_m = nearest_on_road_m
        perp_distance_m = min_distance_m
    else:
        perp_point_m = Point(best_proj_line[0], best_proj_line[1])
        perp_distance_m = float(site_m.distance(perp_point_m))
    perp_wgs = transform(to_wgs.transform, perp_point_m)

    # Third approach: take a local road window around the projection point:
    # 200 m before and 200 m after on the nearest line, then midpoint between those two points.
    closest_line = None
    closest_proj_dist = None
    closest_proj_d = 0.0
    for line in _iter_lines(road_m):
        d = float(line.project(site_m))
        p = line.interpolate(d)
        dist = float(site_m.distance(p))
        if closest_proj_dist is None or dist < closest_proj_dist:
            closest_proj_dist = dist
            closest_line = line
            closest_proj_d = d

    if closest_line is not None:
        line_len = float(closest_line.length)
        d_before = max(0.0, closest_proj_d - 200.0)
        d_after = min(line_len, closest_proj_d + 200.0)
        p_before = closest_line.interpolate(d_before)
        p_after = closest_line.interpolate(d_after)
        mid_x = (float(p_before.x) + float(p_after.x)) / 2.0
        mid_y = (float(p_before.y) + float(p_after.y)) / 2.0
        window_mid_m = Point(mid_x, mid_y)
    else:
        window_mid_m = nearest_on_road_m

    window_mid_wgs = transform(to_wgs.transform, window_mid_m)
    distance_window_mid_m = float(site_m.distance(window_mid_m))

    return {
        "nearest_wgs": nearest_wgs,
        "distance_min_m": min_distance_m,
        "perpendicular_wgs": perp_wgs,
        "distance_perpendicular_m": perp_distance_m,
        "window_mid_wgs": window_mid_wgs,
        "distance_window_mid_m": distance_window_mid_m,
    }


def sector_intersection_on_road(
    site_lon: float,
    site_lat: float,
    road_line_wgs84,
    sector_azimuth_deg: float,
    max_distance_m: float = 1000.0,
    beam_width_deg: float = 60.0,
):
    ensure_geo_libs_available()
    site_point = Point(float(site_lon), float(site_lat))
    site_m, road_m, to_wgs = _project_to_metric(site_point, road_line_wgs84)
    beam = _beam_polygon_metric(site_m, float(sector_azimuth_deg), float(beam_width_deg), float(max_distance_m))
    clipped = road_m.intersection(beam)
    if clipped is None or clipped.is_empty:
        return None
    # Use center of clipped road segment within beam (requested behavior).
    p = _center_point_on_clipped_road(clipped)
    if p is None:
        return None
    d = float(site_m.distance(p))
    if d <= 0.0 or d > float(max_distance_m):
        return None
    p_wgs = transform(to_wgs.transform, p)
    bearing = calculate_bearing_deg(site_lat, site_lon, p_wgs.y, p_wgs.x)
    return {
        "point_wgs": p_wgs,
        "distance_m": float(d),
        "bearing_deg": float(bearing),
    }


def radio_optimized_point_on_road(
    site_lon: float,
    site_lat: float,
    road_line_wgs84,
    sector_azimuth_deg: float,
    window_m: float = 500.0,
    step_m: float = 20.0,
) -> Dict[str, Any]:
    ensure_geo_libs_available()
    site_point = Point(float(site_lon), float(site_lat))
    site_m, road_m, to_wgs = _project_to_metric(site_point, road_line_wgs84)

    # Use nearest route component first; midpoint must stay on the same route geometry.
    base_line = None
    base_line_dist = None
    for line in _iter_lines(road_m):
        p = nearest_points(site_m, line)[1]
        d = float(site_m.distance(p))
        if base_line_dist is None or d < base_line_dist:
            base_line = line
            base_line_dist = d

    if base_line is None:
        best_point = nearest_points(site_m, road_m)[1]
    else:
        # Requested method:
        # 1) first route intersection on azimuth-50 ray
        # 2) first route intersection on azimuth+50 ray
        # 3) midpoint ALONG THE ROUTE between both intersections
        d0 = float(base_line.project(nearest_points(site_m, base_line)[1]))
        along_window_m = max(250.0, float(window_m))
        radial_max_m = 2000.0

        left_candidates = _intersection_candidates_on_ray(site_m, base_line, float(sector_azimuth_deg) - 50.0)
        right_candidates = _intersection_candidates_on_ray(site_m, base_line, float(sector_azimuth_deg) + 50.0)

        def pick_local(cands):
            for p, radial_d in cands:
                if radial_d > radial_max_m:
                    continue
                dp = float(base_line.project(p))
                if abs(dp - d0) <= along_window_m:
                    return p
            return None

        left_pt = pick_local(left_candidates)
        right_pt = pick_local(right_candidates)

        if left_pt is not None and right_pt is not None:
            d_left = float(base_line.project(left_pt))
            d_right = float(base_line.project(right_pt))
            d_mid = (d_left + d_right) / 2.0
            best_point = base_line.interpolate(d_mid)
        elif left_pt is not None:
            best_point = left_pt
        elif right_pt is not None:
            best_point = right_pt
        else:
            best_point = nearest_points(site_m, base_line)[1]

    best_distance = float(site_m.distance(best_point))
    best_bearing = _bearing_from_xy(site_m.x, site_m.y, best_point.x, best_point.y)
    point_wgs = transform(to_wgs.transform, best_point)
    return {
        "point_wgs": point_wgs,
        "distance_m": float(best_distance),
        "bearing_deg": float(best_bearing),
    }


def calculate_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dlambda = math.radians(float(lon2) - float(lon1))
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def angular_difference_deg(a1: float, a2: float) -> float:
    diff = abs(float(a1) - float(a2)) % 360.0
    return min(diff, 360.0 - diff)


def detect_sector_beamwidth(sector: Sector) -> Optional[float]:
    # If beamwidth can be inferred from linked cell antennas, use average H-beamwidth.
    try:
        cells = sector.cells.all() if hasattr(sector.cells, "all") else list(sector.cells)
    except Exception:
        cells = []
    widths = []
    for cell in cells:
        ant = getattr(cell, "antenna", None)
        if not ant:
            continue
        bw = getattr(ant, "hbeamwidth", None)
        if bw is None:
            continue
        try:
            val = float(bw)
        except (TypeError, ValueError):
            continue
        if 1.0 <= val <= 180.0:
            widths.append(val)
    if not widths:
        return None
    return round(sum(widths) / len(widths), 2)


def collect_sector_dlarfcn(sector: Sector) -> str:
    values = set()
    try:
        cells = sector.cells.all() if hasattr(sector.cells, "all") else list(sector.cells)
    except Exception:
        cells = []
    for cell in cells:
        p3 = getattr(cell, "profile_3g", None)
        if not p3:
            continue
        val = getattr(p3, "dlarfcn", None)
        if val is None:
            continue
        text = str(val).strip()
        if not text:
            continue
        values.add(text)
    if not values:
        return "-"
    return ", ".join(sorted(values))


def is_sector_facing_road(
    sector_azimuth: float,
    bearing_to_road: float,
    tolerance_deg: float = 30.0,
    beamwidth_deg: Optional[float] = None,
) -> Tuple[bool, float, float]:
    diff = angular_difference_deg(sector_azimuth, bearing_to_road)
    if beamwidth_deg is not None and beamwidth_deg > 0:
        threshold = max(5.0, beamwidth_deg / 2.0)
    else:
        threshold = max(1.0, float(tolerance_deg))
    return diff <= threshold, diff, threshold


def analyze_road_for_sites_and_sectors(
    road_obj,
    accessible_site_ids: Optional[set],
    max_sites: int = DEFAULT_MAX_SITES,
    beam_width_deg: float = DEFAULT_BEAM_WIDTH_DEG,
    beam_length_m: float = DEFAULT_BEAM_LENGTH_M,
    site_distance_m: float = DEFAULT_SITE_DISTANCE_M,
) -> RoadAnalysisResult:
    ensure_geo_libs_available()
    road_line = parse_road_geometry(road_obj.geometry_geojson)

    query = Site.query.order_by(Site.code_site.asc())
    if accessible_site_ids is not None:
        if not accessible_site_ids:
            return RoadAnalysisResult(
                road_id=road_obj.id,
                road_name=road_obj.name,
                site_rows=[],
                sector_rows=[],
                total_sites=0,
                total_sectors=0,
            )
        query = query.filter(Site.id.in_(list(accessible_site_ids)))

    candidates = []
    for site in query.all():
        if site.latitude is None or site.longitude is None:
            continue
        try:
            site_lat = float(site.latitude)
            site_lon = float(site.longitude)
        except (TypeError, ValueError):
            continue
        if not (-90.0 <= site_lat <= 90.0 and -180.0 <= site_lon <= 180.0):
            continue
        metrics = road_distance_metrics(site_lon, site_lat, road_line)
        dist_m = float(metrics["distance_min_m"])
        if dist_m > float(site_distance_m):
            continue
        nearest_wgs = metrics["nearest_wgs"]
        perp_wgs = metrics["perpendicular_wgs"]
        perp_dist_m = float(metrics["distance_perpendicular_m"])
        win_mid_wgs = metrics["window_mid_wgs"]
        win_mid_dist_m = float(metrics["distance_window_mid_m"])
        bearing = calculate_bearing_deg(site_lat, site_lon, nearest_wgs.y, nearest_wgs.x)
        bearing_perp = calculate_bearing_deg(site_lat, site_lon, perp_wgs.y, perp_wgs.x)
        bearing_win_mid = calculate_bearing_deg(site_lat, site_lon, win_mid_wgs.y, win_mid_wgs.x)
        candidates.append((
            site, site_lat, site_lon, nearest_wgs, dist_m, bearing, perp_wgs, perp_dist_m, bearing_perp,
            win_mid_wgs, win_mid_dist_m, bearing_win_mid
        ))

    candidates.sort(key=lambda x: x[2])
    candidates = candidates[: max(int(max_sites), 1)]

    site_rows = []
    sector_rows = []
    for site, site_lat, site_lon, nearest_wgs, dist_m, bearing_to_road, perp_wgs, perp_dist_m, bearing_perp, win_mid_wgs, win_mid_dist_m, bearing_win_mid in candidates:
        site_rows.append({
            "site_id": site.id,
            "site_code": site.code_site,
            "site_name": site.name,
            "latitude": site.latitude,
            "longitude": site.longitude,
            "selected_road": road_obj.name,
            "distance_to_road_m": round(dist_m, 2),  # minimum geometric distance
            "distance_perpendicular_m": round(perp_dist_m, 2),
            "nearest_road_latitude": round(float(nearest_wgs.y), 6),
            "nearest_road_longitude": round(float(nearest_wgs.x), 6),
            "perpendicular_road_latitude": round(float(perp_wgs.y), 6),
            "perpendicular_road_longitude": round(float(perp_wgs.x), 6),
            "window_mid_road_latitude": round(float(win_mid_wgs.y), 6),
            "window_mid_road_longitude": round(float(win_mid_wgs.x), 6),
            "bearing_to_road_deg": round(float(bearing_to_road), 2),
            "bearing_perpendicular_deg": round(float(bearing_perp), 2),
            "distance_window_mid_m": round(float(win_mid_dist_m), 2),
            "bearing_window_mid_deg": round(float(bearing_win_mid), 2),
        })

        sectors = site.sectors.order_by(Sector.code_sector.asc()).all() if hasattr(site.sectors, "order_by") else list(site.sectors)
        for sector in sectors:
            try:
                az = float(sector.azimuth)
            except (TypeError, ValueError):
                continue
            intercept = sector_intersection_on_road(
                site_lon=site_lon,
                site_lat=site_lat,
                road_line_wgs84=road_line,
                sector_azimuth_deg=az,
                max_distance_m=float(beam_length_m),
                beam_width_deg=float(beam_width_deg),
            )
            is_favorable = intercept is not None
            intercept_point = intercept["point_wgs"] if intercept else None
            beamwidth = detect_sector_beamwidth(sector)
            facing, diff, threshold = is_sector_facing_road(
                sector_azimuth=az,
                bearing_to_road=bearing_to_road,
                tolerance_deg=max(1.0, float(beam_width_deg) / 2.0),
                beamwidth_deg=beamwidth,
            )
            sector_rows.append({
                "site_id": site.id,
                "site_code": site.code_site,
                "site_name": site.name,
                "site_latitude": site.latitude,
                "site_longitude": site.longitude,
                "sector_id": sector.id,
                "sector_code": sector.code_sector,
                "dlarfcn_list": collect_sector_dlarfcn(sector),
                "azimuth_deg": round(az, 2),
                "distance_to_road_m": round(dist_m, 2),
                "distance_perpendicular_m": round(perp_dist_m, 2),
                "distance_window_mid_m": round(float(win_mid_dist_m), 2),
                "distance_intersection_m": round(float(intercept["distance_m"]), 2) if intercept else None,
                "bearing_to_road_deg": round(float(bearing_to_road), 2),
                "bearing_perpendicular_deg": round(float(bearing_perp), 2),
                "bearing_window_mid_deg": round(float(bearing_win_mid), 2),
                "bearing_intersection_deg": round(float(intercept["bearing_deg"]), 2) if intercept else None,
                "intersection_road_latitude": round(float(intercept_point.y), 6) if intercept else None,
                "intersection_road_longitude": round(float(intercept_point.x), 6) if intercept else None,
                "intersects_road_1km_beam60": bool(is_favorable),
                "angular_difference_deg": round(float(diff), 2),
                "facing_road": bool(is_favorable),
                "facing_threshold_deg": round(float(threshold), 2),
                "beamwidth_deg": round(float(beamwidth), 2) if beamwidth is not None else None,
            })

    sector_rows.sort(
        key=lambda x: (
            x.get("distance_intersection_m") if x.get("distance_intersection_m") is not None else 999999.0,
            x["angular_difference_deg"],
        )
    )
    return RoadAnalysisResult(
        road_id=road_obj.id,
        road_name=road_obj.name,
        site_rows=site_rows,
        sector_rows=sector_rows,
        total_sites=len(site_rows),
        total_sectors=len(sector_rows),
    )
