import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    from shapely.geometry import LineString, MultiLineString, Point, shape
    from shapely.ops import nearest_points, transform
    from pyproj import CRS, Transformer
    _GEO_LIBS_AVAILABLE = True
except ModuleNotFoundError:
    LineString = MultiLineString = Point = object
    shape = nearest_points = transform = None
    CRS = Transformer = None
    _GEO_LIBS_AVAILABLE = False

from app.models import Sector, Site


DEFAULT_MAX_SITES = 200
DEFAULT_MAX_DISTANCE_M = 10000.0
DEFAULT_AZ_TOLERANCE_DEG = 35.0


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
        # Keep a single connected analysis line by merging all coordinates.
        coords = []
        for line in geom_obj.geoms:
            coords.extend(list(line.coords))
        if len(coords) >= 2:
            return LineString(coords)
    raise ValueError("Road geometry must be LineString or MultiLineString.")


def parse_road_geometry(road_geojson: str) -> LineString:
    ensure_geo_libs_available()
    if not road_geojson:
        raise ValueError("Road geometry is empty.")
    try:
        data = json.loads(road_geojson)
        geom = shape(data)
        return _normalize_linestring(geom)
    except Exception as exc:
        raise ValueError(f"Invalid road geometry JSON: {exc}") from exc


def _utm_epsg_for_lonlat(lon: float, lat: float) -> int:
    zone = int((lon + 180.0) // 6.0) + 1
    if lat >= 0:
        return 32600 + zone
    return 32700 + zone


def _project_to_metric(point_wgs84: Point, line_wgs84: LineString):
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


def nearest_point_on_road(site_lon: float, site_lat: float, road_line_wgs84: LineString) -> Tuple[Point, float]:
    ensure_geo_libs_available()
    site_point = Point(float(site_lon), float(site_lat))
    site_m, road_m, to_wgs = _project_to_metric(site_point, road_line_wgs84)
    nearest_on_road_m = nearest_points(site_m, road_m)[1]
    distance_m = float(site_m.distance(nearest_on_road_m))
    nearest_wgs = transform(to_wgs.transform, nearest_on_road_m)
    return nearest_wgs, distance_m


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
    tolerance_deg: float = DEFAULT_AZ_TOLERANCE_DEG,
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
    max_distance_m: float = DEFAULT_MAX_DISTANCE_M,
    azimuth_tolerance_deg: float = DEFAULT_AZ_TOLERANCE_DEG,
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
        nearest_wgs, dist_m = nearest_point_on_road(site_lon, site_lat, road_line)
        if dist_m > float(max_distance_m):
            continue
        bearing = calculate_bearing_deg(site_lat, site_lon, nearest_wgs.y, nearest_wgs.x)
        candidates.append((site, nearest_wgs, dist_m, bearing))

    candidates.sort(key=lambda x: x[2])
    candidates = candidates[: max(int(max_sites), 1)]

    site_rows = []
    sector_rows = []
    for site, nearest_wgs, dist_m, bearing_to_road in candidates:
        site_rows.append({
            "site_id": site.id,
            "site_code": site.code_site,
            "site_name": site.name,
            "latitude": site.latitude,
            "longitude": site.longitude,
            "selected_road": road_obj.name,
            "distance_to_road_m": round(dist_m, 2),
            "nearest_road_latitude": round(float(nearest_wgs.y), 6),
            "nearest_road_longitude": round(float(nearest_wgs.x), 6),
            "bearing_to_road_deg": round(float(bearing_to_road), 2),
        })

        sectors = site.sectors.order_by(Sector.code_sector.asc()).all() if hasattr(site.sectors, "order_by") else list(site.sectors)
        for sector in sectors:
            try:
                az = float(sector.azimuth)
            except (TypeError, ValueError):
                continue
            beamwidth = detect_sector_beamwidth(sector)
            facing, diff, threshold = is_sector_facing_road(
                sector_azimuth=az,
                bearing_to_road=bearing_to_road,
                tolerance_deg=azimuth_tolerance_deg,
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
                "bearing_to_road_deg": round(float(bearing_to_road), 2),
                "angular_difference_deg": round(float(diff), 2),
                "facing_road": bool(facing),
                "facing_threshold_deg": round(float(threshold), 2),
                "beamwidth_deg": round(float(beamwidth), 2) if beamwidth is not None else None,
            })

    sector_rows.sort(key=lambda x: (x["distance_to_road_m"], x["angular_difference_deg"]))
    return RoadAnalysisResult(
        road_id=road_obj.id,
        road_name=road_obj.name,
        site_rows=site_rows,
        sector_rows=sector_rows,
        total_sites=len(site_rows),
        total_sectors=len(sector_rows),
    )
