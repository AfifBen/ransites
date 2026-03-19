import io
import json
import csv
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from openpyxl import Workbook

from app import db
from app.models import Road
from app.security import admin_required, get_accessible_site_ids, login_required
from app.services.road_analysis_service import (
    DEFAULT_BEAM_LENGTH_M,
    DEFAULT_SITE_DISTANCE_M,
    DEFAULT_BEAM_WIDTH_DEG,
    DEFAULT_MAX_SITES,
    analyze_road_for_sites_and_sectors,
)


road_bp = Blueprint("road_bp", __name__)


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _analysis_params_from_request():
    return {
        "max_sites": max(1, _safe_int(request.values.get("max_sites"), DEFAULT_MAX_SITES)),
        "site_distance_m": max(100.0, min(100000.0, _safe_float(request.values.get("site_distance_m"), DEFAULT_SITE_DISTANCE_M))),
        "beam_width_deg": max(10.0, min(120.0, _safe_float(request.values.get("beam_width_deg"), DEFAULT_BEAM_WIDTH_DEG))),
        "beam_length_m": max(100.0, min(10000.0, _safe_float(request.values.get("beam_length_m"), DEFAULT_BEAM_LENGTH_M))),
    }


def _as_float(value):
    if value is None:
        raise ValueError("empty")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        raise ValueError("empty")
    return float(text)


def _csv_points_to_geometry(upload, road_name, road_code=None):
    raw = upload.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except Exception:
        dialect = csv.excel
        dialect.delimiter = ","
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("CSV has no header row.")

    headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    lon_key = headers.get("longitude") or headers.get("lon") or headers.get("lng") or headers.get("x")
    lat_key = headers.get("latitude") or headers.get("lat") or headers.get("y")
    order_key = headers.get("order") or headers.get("seq") or headers.get("index") or headers.get("id")
    if not lon_key or not lat_key:
        raise ValueError("CSV must contain longitude/lon and latitude/lat columns.")

    points = []
    for idx, row in enumerate(reader, start=1):
        try:
            lon = _as_float(row.get(lon_key))
            lat = _as_float(row.get(lat_key))
        except Exception:
            continue
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            continue
        seq = idx
        if order_key and row.get(order_key) not in (None, ""):
            try:
                seq = int(float(str(row.get(order_key)).replace(",", ".")))
            except Exception:
                pass
        points.append((seq, lon, lat))

    if len(points) < 2:
        raise ValueError("CSV must provide at least 2 valid points.")

    points.sort(key=lambda x: x[0])
    coords = [[p[1], p[2]] for p in points]
    return {
        "type": "Feature",
        "properties": {
            "name": road_name,
            "code": road_code or None,
            "source": "CSV points upload",
        },
        "geometry": {
            "type": "LineString",
            "coordinates": coords,
        },
    }


def _parse_kml_coord_text(text):
    coords = []
    if not text:
        return coords
    normalized = str(text).replace("\n", " ").replace("\t", " ")
    for token in normalized.split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            lon = _as_float(parts[0])
            lat = _as_float(parts[1])
        except Exception:
            continue
        if -180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0:
            coords.append([lon, lat])
    return coords


def _kml_to_geometry(upload, road_name, road_code=None):
    raw = upload.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    try:
        root = ET.fromstring(text)
    except Exception as exc:
        raise ValueError(f"Invalid KML XML: {exc}") from exc

    lines = []
    # Priority 1: use LineString geometries (best representation for roads).
    for elem in root.iter():
        if not isinstance(elem.tag, str) or not elem.tag.endswith("LineString"):
            continue
        for child in list(elem):
            if isinstance(child.tag, str) and child.tag.endswith("coordinates"):
                current = _parse_kml_coord_text(child.text)
                if len(current) >= 2:
                    lines.append(current)

    # Priority 2: fallback to ordered Point placemarks if no LineString found.
    if not lines:
        coords = []
        for elem in root.iter():
            if not isinstance(elem.tag, str) or not elem.tag.endswith("Point"):
                continue
            for child in list(elem):
                if isinstance(child.tag, str) and child.tag.endswith("coordinates"):
                    current = _parse_kml_coord_text(child.text)
                    if current:
                        coords.append(current[0])
        if len(coords) >= 2:
            lines = [coords]

    if not lines:
        raise ValueError("KML must contain at least 2 coordinates (LineString or Point list).")

    if len(lines) == 1:
        geom = {"type": "LineString", "coordinates": lines[0]}
    else:
        geom = {"type": "MultiLineString", "coordinates": lines}

    return {
        "type": "Feature",
        "properties": {
            "name": road_name,
            "code": road_code or None,
            "source": "KML upload",
        },
        "geometry": geom,
    }


def _extract_geojson_features(payload):
    if not isinstance(payload, dict):
        raise ValueError("GeoJSON payload must be a JSON object.")
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("GeoJSON must contain a FeatureCollection with features.")
    return features


def _upsert_roads_from_features(features):
    grouped = {}
    for idx, feat in enumerate(features, start=1):
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties") or {}
        geom = feat.get("geometry")
        if not isinstance(geom, dict):
            continue
        gtype = geom.get("type")
        if gtype not in {"LineString", "MultiLineString"}:
            continue
        road_name = str(
            props.get("name")
            or props.get("road_name")
            or props.get("route")
            or props.get("ref")
            or f"Road {idx}"
        ).strip()
        road_code = str(props.get("code") or props.get("road_code") or props.get("ref") or "").strip() or None
        key = road_code or road_name
        bucket = grouped.setdefault(
            key,
            {
                "name": road_name,
                "code": road_code,
                "lines": [],
            },
        )
        coords = geom.get("coordinates") or []
        if gtype == "LineString":
            if len(coords) >= 2:
                bucket["lines"].append(coords)
        elif gtype == "MultiLineString":
            for line in coords:
                if isinstance(line, list) and len(line) >= 2:
                    bucket["lines"].append(line)

    added = 0
    updated = 0
    for item in grouped.values():
        if not item["lines"]:
            continue
        road_name = item["name"]
        road_code = item["code"]
        if len(item["lines"]) == 1:
            geom = {"type": "LineString", "coordinates": item["lines"][0]}
        else:
            geom = {"type": "MultiLineString", "coordinates": item["lines"]}
        geom_json = json.dumps(geom, ensure_ascii=True)

        existing = None
        if road_code:
            existing = Road.query.filter_by(code=road_code).first()
        if not existing:
            existing = Road.query.filter_by(name=road_name).first()

        if existing:
            existing.name = road_name
            existing.code = road_code
            existing.geometry_geojson = geom_json
            existing.is_active = True
            updated += 1
        else:
            db.session.add(
                Road(
                    code=road_code,
                    name=road_name,
                    geometry_geojson=geom_json,
                    is_active=True,
                )
            )
            added += 1
    db.session.commit()
    return added, updated


def _load_geojson_from_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must start with http:// or https://")
    timeout = int(current_app.config.get("ROAD_IMPORT_HTTP_TIMEOUT", 45))
    req = Request(url, headers={"User-Agent": "RANSites-RoadImporter/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except HTTPError as exc:
        raise ValueError(f"HTTP error {exc.code} while fetching roads URL.") from exc
    except URLError as exc:
        raise ValueError(f"Network error while fetching roads URL: {exc.reason}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Fetched file is not valid JSON: {exc}") from exc


@road_bp.route("/road-analysis", methods=["GET"])
@login_required
def road_analysis_page():
    roads = Road.query.filter_by(is_active=True).order_by(Road.name.asc()).all()
    return render_template(
        "road_analysis/select.html",
        title="Road Analysis",
        roads=roads,
        defaults={
            "max_sites": DEFAULT_MAX_SITES,
            "site_distance_m": int(DEFAULT_SITE_DISTANCE_M),
            "beam_width_deg": int(DEFAULT_BEAM_WIDTH_DEG),
            "beam_length_m": int(DEFAULT_BEAM_LENGTH_M),
        },
    )


@road_bp.route("/road-analysis/import-geojson", methods=["POST"])
@login_required
@admin_required
def import_roads_geojson():
    upload = request.files.get("roads_file")
    if not upload or not upload.filename:
        flash("Please select a GeoJSON file.", "danger")
        return redirect(url_for("road_bp.road_analysis_page"))

    try:
        payload = json.loads(upload.read().decode("utf-8"))
    except Exception as exc:
        flash(f"Invalid GeoJSON file: {exc}", "danger")
        return redirect(url_for("road_bp.road_analysis_page"))

    try:
        features = _extract_geojson_features(payload)
        added, updated = _upsert_roads_from_features(features)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("road_bp.road_analysis_page"))

    flash(f"Road import completed: {added} added, {updated} updated.", "success")
    return redirect(url_for("road_bp.road_analysis_page"))


@road_bp.route("/road-analysis/import-url", methods=["POST"])
@login_required
@admin_required
def import_roads_from_url():
    roads_url = (request.form.get("roads_geojson_url") or "").strip()
    if not roads_url:
        roads_url = (current_app.config.get("ROADS_GEOJSON_URL") or "").strip()
    if not roads_url:
        flash("No roads URL configured. Set ROADS_GEOJSON_URL or paste a URL.", "danger")
        return redirect(url_for("road_bp.road_analysis_page"))

    try:
        payload = _load_geojson_from_url(roads_url)
        features = _extract_geojson_features(payload)
        added, updated = _upsert_roads_from_features(features)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("road_bp.road_analysis_page"))

    flash(f"Road URL import completed: {added} added, {updated} updated.", "success")
    return redirect(url_for("road_bp.road_analysis_page"))


@road_bp.route("/road-analysis/import-csv-points", methods=["POST"])
@login_required
@admin_required
def import_road_from_csv_points():
    upload = request.files.get("road_points_file")
    road_name = (request.form.get("road_name") or "").strip()
    road_code = (request.form.get("road_code") or "").strip() or None
    replace_existing = str(request.form.get("replace_existing") or "").strip().lower() in {"1", "true", "yes", "on"}
    if not upload or not upload.filename:
        flash("Please select a CSV points file.", "danger")
        return redirect(url_for("road_bp.road_analysis_page"))
    if not road_name:
        flash("Road name is required for CSV import.", "danger")
        return redirect(url_for("road_bp.road_analysis_page"))

    try:
        if replace_existing:
            Road.query.delete()
            db.session.commit()
        feature = _csv_points_to_geometry(upload, road_name=road_name, road_code=road_code)
        added, updated = _upsert_roads_from_features([feature])
    except ValueError as exc:
        flash(f"CSV import failed: {exc}", "danger")
        return redirect(url_for("road_bp.road_analysis_page"))

    flash(f"CSV points import completed: {added} added, {updated} updated.", "success")
    return redirect(url_for("road_bp.road_analysis_page"))


@road_bp.route("/road-analysis/import-route", methods=["POST"])
@login_required
@admin_required
def import_road_from_file():
    upload = request.files.get("road_file")
    road_name = (request.form.get("road_name") or "").strip()
    road_code = (request.form.get("road_code") or "").strip() or None
    replace_existing = str(request.form.get("replace_existing") or "").strip().lower() in {"1", "true", "yes", "on"}

    if not upload or not upload.filename:
        flash("Please select a route file (.csv or .kml).", "danger")
        return redirect(url_for("road_bp.road_analysis_page"))
    if not road_name:
        flash("Road name is required.", "danger")
        return redirect(url_for("road_bp.road_analysis_page"))

    try:
        if replace_existing:
            Road.query.delete()
            db.session.commit()

        filename = (upload.filename or "").lower()
        if filename.endswith(".csv"):
            feature = _csv_points_to_geometry(upload, road_name=road_name, road_code=road_code)
        elif filename.endswith(".kml"):
            feature = _kml_to_geometry(upload, road_name=road_name, road_code=road_code)
        else:
            raise ValueError("Unsupported format. Please upload .csv or .kml")

        added, updated = _upsert_roads_from_features([feature])
    except ValueError as exc:
        flash(f"Route import failed: {exc}", "danger")
        return redirect(url_for("road_bp.road_analysis_page"))

    flash(f"Route import completed: {added} added, {updated} updated.", "success")
    return redirect(url_for("road_bp.road_analysis_page"))


@road_bp.route("/road-analysis/import-kml", methods=["POST"])
@login_required
@admin_required
def import_road_from_kml():
    upload = request.files.get("road_kml_file")
    road_name = (request.form.get("road_name") or "").strip()
    road_code = (request.form.get("road_code") or "").strip() or None
    replace_existing = str(request.form.get("replace_existing") or "").strip().lower() in {"1", "true", "yes", "on"}

    if not upload or not upload.filename:
        flash("Please select a KML file.", "danger")
        return redirect(url_for("road_bp.road_analysis_page"))
    if not road_name:
        flash("Road name is required for KML import.", "danger")
        return redirect(url_for("road_bp.road_analysis_page"))

    try:
        if replace_existing:
            Road.query.delete()
            db.session.commit()
        feature = _kml_to_geometry(upload, road_name=road_name, road_code=road_code)
        added, updated = _upsert_roads_from_features([feature])
    except ValueError as exc:
        flash(f"KML import failed: {exc}", "danger")
        return redirect(url_for("road_bp.road_analysis_page"))

    flash(f"KML import completed: {added} added, {updated} updated.", "success")
    return redirect(url_for("road_bp.road_analysis_page"))


@road_bp.route("/road-analysis/results", methods=["POST"])
@login_required
def road_analysis_results():
    road_id = _safe_int(request.form.get("road_id"), 0)
    road = Road.query.get(road_id)
    if not road or not road.is_active:
        flash("Selected road not found.", "danger")
        return redirect(url_for("road_bp.road_analysis_page"))

    params = _analysis_params_from_request()
    try:
        result = analyze_road_for_sites_and_sectors(
            road_obj=road,
            accessible_site_ids=get_accessible_site_ids(),
            max_sites=params["max_sites"],
            beam_width_deg=params["beam_width_deg"],
            beam_length_m=params["beam_length_m"],
            site_distance_m=params["site_distance_m"],
        )
    except RuntimeError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("road_bp.road_analysis_page"))
    return render_template(
        "road_analysis/results.html",
        title="Road Analysis Results",
        result=result,
        params=params,
        road_geometry_geojson=road.geometry_geojson,
    )


@road_bp.route("/road-analysis/export/<int:road_id>", methods=["GET"])
@login_required
def road_analysis_export(road_id):
    road = Road.query.get(road_id)
    if not road or not road.is_active:
        flash("Selected road not found.", "danger")
        return redirect(url_for("road_bp.road_analysis_page"))

    params = _analysis_params_from_request()
    try:
        result = analyze_road_for_sites_and_sectors(
            road_obj=road,
            accessible_site_ids=get_accessible_site_ids(),
            max_sites=params["max_sites"],
            beam_width_deg=params["beam_width_deg"],
            beam_length_m=params["beam_length_m"],
            site_distance_m=params["site_distance_m"],
        )
    except RuntimeError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("road_bp.road_analysis_page"))

    wb = Workbook()
    ws_sites = wb.active
    ws_sites.title = "Sites"
    site_headers = [
        "site_code",
        "site_name",
        "latitude",
        "longitude",
        "selected_road",
        "distance_to_road_m",
        "distance_perpendicular_m",
        "nearest_road_latitude",
        "nearest_road_longitude",
        "perpendicular_road_latitude",
        "perpendicular_road_longitude",
        "bearing_to_road_deg",
        "bearing_perpendicular_deg",
    ]
    ws_sites.append(site_headers)
    for row in result.site_rows:
        ws_sites.append([row.get(h) for h in site_headers])

    ws_sectors = wb.create_sheet("Sectors")
    sector_headers = [
        "site_code",
        "site_name",
        "sector_code",
        "dlarfcn_list",
        "azimuth_deg",
        "distance_to_road_m",
        "distance_perpendicular_m",
        "distance_intersection_m",
        "bearing_to_road_deg",
        "bearing_perpendicular_deg",
        "bearing_intersection_deg",
        "intersection_road_latitude",
        "intersection_road_longitude",
        "intersects_road_1km_beam60",
        "angular_difference_deg",
        "beamwidth_deg",
        "facing_threshold_deg",
        "facing_road",
    ]
    ws_sectors.append(sector_headers)
    for row in result.sector_rows:
        ws_sectors.append([row.get(h) for h in sector_headers])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"road_analysis_{road.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
