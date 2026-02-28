import json
from pathlib import Path


DEFAULT_RAN_REFERENCE = [
    # Operational single-point values set to the MAX of the agreed realistic ranges.
    {"tech": "2G", "band": 900, "cell_radius_km": 35.0, "bs_nominal_power_dbm": 48.0},
    {"tech": "2G", "band": 1800, "cell_radius_km": 20.0, "bs_nominal_power_dbm": 46.0},
    {"tech": "3G", "band": 900, "cell_radius_km": 25.0, "bs_nominal_power_dbm": 46.0},
    {"tech": "3G", "band": 2100, "cell_radius_km": 15.0, "bs_nominal_power_dbm": 46.0},
    {"tech": "4G", "band": 800, "cell_radius_km": 20.0, "bs_nominal_power_dbm": 46.0},
    {"tech": "4G", "band": 900, "cell_radius_km": 20.0, "bs_nominal_power_dbm": 46.0},
    {"tech": "4G", "band": 1800, "cell_radius_km": 12.0, "bs_nominal_power_dbm": 46.0},
    {"tech": "4G", "band": 2100, "cell_radius_km": 10.0, "bs_nominal_power_dbm": 46.0},
    {"tech": "4G", "band": 2300, "cell_radius_km": 7.0, "bs_nominal_power_dbm": 44.0},
    {"tech": "5G", "band": 3500, "cell_radius_km": 4.0, "bs_nominal_power_dbm": 46.0},
]


def _ran_reference_path(instance_path):
    return Path(instance_path) / "ran_reference.json"


def load_ran_reference(instance_path):
    p = _ran_reference_path(instance_path)
    if not p.exists():
        return list(DEFAULT_RAN_REFERENCE)
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(rows, list):
            return rows
    except Exception:
        pass
    return list(DEFAULT_RAN_REFERENCE)


def save_ran_reference(instance_path, rows):
    p = _ran_reference_path(instance_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, ensure_ascii=True, indent=2), encoding="utf-8")


def build_ran_reference_map(instance_path):
    rows = load_ran_reference(instance_path)
    mapping = {}
    for r in rows:
        try:
            tech = str(r.get("tech", "")).strip().upper()
            band = int(float(r.get("band")))
            radius = float(r.get("cell_radius_km"))
            power = float(r.get("bs_nominal_power_dbm"))
        except (TypeError, ValueError):
            continue
        if not tech:
            continue
        mapping[(tech, band)] = {"radius": radius, "power": power}
    return mapping
