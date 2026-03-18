"""
Fetch Algerian national roads from Overpass API and export a GeoJSON file.

Usage:
    .\\venv\\Scripts\\python.exe scripts\\fetch_algeria_roads_overpass.py
    .\\venv\\Scripts\\python.exe scripts\\fetch_algeria_roads_overpass.py --output output\\algeria_roads_real.geojson
"""

import argparse
import json
import re
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from time import sleep


DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_FALLBACK_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
DEFAULT_OUTPUT = "output/algeria_roads_real.geojson"
OSRM_ROUTE_URL = "https://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson"

RN_WAYPOINTS = {
    # (lon, lat) checkpoints to force corridor close to RN5 axis.
    "RN5": [
        (3.0588, 36.7538),  # Algiers
        (4.1887, 36.4700),  # Bouira axis
        (5.4137, 36.1906),  # Setif
        (6.6147, 36.3650),  # Constantine
    ]
}


def _ref_regex(road_ref: str) -> str:
    # Accept variants: RN5, RN 5, N5, N 5, RN05
    text = (road_ref or "").strip().upper()
    m = re.search(r"(\d+)", text)
    if not m:
        safe = re.escape(text.replace(" ", ""))
        return rf"^{safe}$"
    num = int(m.group(1))
    # Match inside multi-ref strings too (e.g. "A1;RN 5;CW 12"), but avoid RN50/RN51.
    return rf"(^|[^0-9])((RN|N)\s*0*{num}([A-Z])?)([^0-9]|$)"


def build_query(road_ref: str | None = None) -> str:
    # Algeria area + national roads (ref starts with RN) + major roads.
    # The query returns ways with their geometry.
    if road_ref:
        safe_ref_regex = _ref_regex(road_ref)
        num_match = re.search(r"(\d+)", road_ref or "")
        num = num_match.group(1) if num_match else ""
        return f"""
[out:json][timeout:120];
area["ISO3166-1"="DZ"][admin_level=2]->.dz;
(
  way(area.dz)["highway"]["ref"~"{safe_ref_regex}"];
  way(area.dz)["highway"]["nat_ref"~"{safe_ref_regex}"];
  way(area.dz)["highway"]["name"~"([Rr]oute\\s+[Nn]ationale\\s*{num}|\\bRN\\s*0*{num}\\b|\\bN\\s*0*{num}\\b)"];
);
out tags geom;
"""
    return """
[out:json][timeout:120];
area["ISO3166-1"="DZ"][admin_level=2]->.dz;
(
  way(area.dz)["highway"]["ref"~"^RN"];
  way(area.dz)["highway"~"motorway|trunk|primary"]["ref"];
);
out tags geom;
"""


def overpass_fetch(overpass_url: str, query: str) -> dict:
    data = urlencode({"data": query}).encode("utf-8")
    urls = [overpass_url] + [u for u in OVERPASS_FALLBACK_URLS if u != overpass_url]
    last_error = None
    for url in urls:
        for attempt in range(1, 4):
            try:
                req = Request(
                    url,
                    data=data,
                    headers={"User-Agent": "RANSites-RoadFetcher/1.0"},
                )
                with urlopen(req, timeout=180) as resp:
                    raw = resp.read()
                return json.loads(raw.decode("utf-8"))
            except (HTTPError, URLError, TimeoutError) as exc:
                last_error = exc
                sleep(1.5 * attempt)
                continue
    raise RuntimeError(f"Overpass request failed after retries: {last_error}")


def overpass_to_geojson(payload: dict) -> dict:
    features = []
    for el in payload.get("elements", []):
        if el.get("type") != "way":
            continue
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        coords = [[float(p["lon"]), float(p["lat"])] for p in geom if "lon" in p and "lat" in p]
        if len(coords) < 2:
            continue
        tags = el.get("tags") or {}
        ref = (tags.get("ref") or "").strip()
        name = (tags.get("name") or "").strip()
        road_name = name or ref or f"Way {el.get('id')}"
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "code": ref or None,
                    "name": road_name,
                    "source": "OpenStreetMap/Overpass",
                    "osm_way_id": el.get("id"),
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def aggregate_by_code(features: list[dict], forced_ref: str | None = None) -> list[dict]:
    grouped = {}
    for feat in features:
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        if geom.get("type") != "LineString":
            continue
        coords = geom.get("coordinates") or []
        if len(coords) < 2:
            continue
        code = (props.get("code") or "").strip()
        name = (props.get("name") or "").strip()
        if forced_ref:
            code = forced_ref
            if not name:
                name = forced_ref
        key = code or name or "UNNAMED"
        bucket = grouped.setdefault(
            key,
            {"code": code or None, "name": name or key, "coords_list": []},
        )
        bucket["coords_list"].append(coords)

    out = []
    for _, item in grouped.items():
        coords_list = item["coords_list"]
        if len(coords_list) == 1:
            geom = {"type": "LineString", "coordinates": coords_list[0]}
        else:
            geom = {"type": "MultiLineString", "coordinates": coords_list}
        out.append(
            {
                "type": "Feature",
                "properties": {"code": item["code"], "name": item["name"], "source": "OpenStreetMap/Overpass"},
                "geometry": geom,
            }
        )
    return out


def _haversine_m(lon1, lat1, lon2, lat2):
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def feature_length_km(feature: dict) -> float:
    geom = feature.get("geometry") or {}
    gtype = geom.get("type")
    total_m = 0.0
    if gtype == "LineString":
        lines = [geom.get("coordinates") or []]
    elif gtype == "MultiLineString":
        lines = geom.get("coordinates") or []
    else:
        return 0.0
    for line in lines:
        for i in range(1, len(line)):
            lon1, lat1 = line[i - 1]
            lon2, lat2 = line[i]
            total_m += _haversine_m(lon1, lat1, lon2, lat2)
    return total_m / 1000.0


def osrm_corridor_feature(road_ref: str) -> dict | None:
    key = road_ref.upper().replace(" ", "")
    points = RN_WAYPOINTS.get(key)
    if not points or len(points) < 2:
        return None
    coords = ";".join(f"{lon},{lat}" for lon, lat in points)
    url = OSRM_ROUTE_URL.format(coords=coords)
    req = Request(url, headers={"User-Agent": "RANSites-RoadFetcher/1.0"})
    with urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    routes = payload.get("routes") or []
    if not routes:
        return None
    geom = routes[0].get("geometry")
    if not geom:
        return None
    return {
        "type": "Feature",
        "properties": {
            "code": key,
            "name": f"{key} corridor (OSRM fallback)",
            "source": "OSRM route fallback",
        },
        "geometry": geom,
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch Algeria roads from Overpass and export GeoJSON.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output GeoJSON path")
    parser.add_argument("--overpass-url", default=DEFAULT_OVERPASS_URL, help="Overpass API endpoint URL")
    parser.add_argument("--ref", default="", help='Road reference filter, e.g. "RN5"')
    parser.add_argument("--min-length-km", type=float, default=100.0, help="If road is shorter than this, try OSRM fallback")
    args = parser.parse_args()

    road_ref = (args.ref or "").strip() or None
    payload = overpass_fetch(args.overpass_url, build_query(road_ref=road_ref))
    raw_geojson = overpass_to_geojson(payload)
    features = raw_geojson.get("features", [])
    if road_ref:
        features = aggregate_by_code(features, forced_ref=road_ref.upper().replace(" ", ""))
    else:
        features = aggregate_by_code(features, forced_ref=None)

    if road_ref and features:
        length_km = feature_length_km(features[0])
        if length_km < float(args.min_length_km):
            try:
                fallback = osrm_corridor_feature(road_ref)
            except Exception:
                fallback = None
            if fallback is not None:
                features = [fallback]

    geojson = {"type": "FeatureCollection", "features": features}
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")
    print(f"Generated {out_path} with {len(geojson.get('features', []))} roads")


if __name__ == "__main__":
    main()
