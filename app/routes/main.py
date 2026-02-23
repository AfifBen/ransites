import io
import re
import csv
import math
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, jsonify
from openpyxl import Workbook, load_workbook
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.models import Region, Wilaya, Commune, Site, Antenna, Supplier, Sector, Mapping, Cell
from app.security import login_required, csrf_protect, get_accessible_site_ids

main_bp = Blueprint('main', __name__)


def _haversine_km(lat1, lon1, lat2, lon2):
    # Great-circle distance between two GPS points (in km).
    r = 6371.0
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dlat = math.radians(float(lat2) - float(lat1))
    dlon = math.radians(float(lon2) - float(lon1))
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c

IMPORT_TEMPLATE_SPECS = {
    "sites": {
        "sheets": {
            "sites": [
                "site_code",
                "site_name",
                "commune_id",
                "supplier_name",
                "latitude",
                "longitude",
                "laltitude",
                "addresses",
                "altitude",
                "support_nature",
                "support_type",
                "support_hight",
                "Comments",
            ]
        }
    },
    "sectors": {
        "sheets": {
            "sectors": [
                "code_sector",
                "azimuth",
                "hba",
                "code_site",
                "coverage_goal",
                "comments",
            ]
        }
    },
    "cells": {
        "sheets": {
            "2G": [
                "CELLNAME",
                "TECHNOLOGY",
                "FREQUENCY",
                "ANTENNA_TECH",
                "MECHANICALTILT",
                "ELECTRICALTILT",
                "ANTENNA",
                "BSC",
                "LAC",
                "RAC",
                "BSIC",
                "BCCH",
            ],
            "3G": [
                "CELLNAME",
                "TECHNOLOGY",
                "FREQUENCY",
                "ANTENNA_TECH",
                "MECHANICALTILT",
                "ELECTRICALTILT",
                "ANTENNA",
                "RNC",
                "LAC",
                "RAC",
                "PSC",
                "DLARFCN",
            ],
            "4G": [
                "CELLNAME",
                "TECHNOLOGY",
                "FREQUENCY",
                "ANTENNA_TECH",
                "MECHANICALTILT",
                "ELECTRICALTILT",
                "ANTENNA",
                "ENODEB",
                "TAC",
                "RSI",
                "PCI",
                "EARFCN",
            ],
            "5G": [
                "CELLNAME",
                "TECHNOLOGY",
                "FREQUENCY",
                "ANTENNA_TECH",
                "MECHANICALTILT",
                "ELECTRICALTILT",
                "ANTENNA",
                "GNODEB",
                "LAC",
                "RSI",
                "PCI",
                "ARFCN",
            ],
        }
    },
    "mapping": {
        "sheets": {
            "mapping": [
                "MAP_ID",
                "CELL_CODE",
                "ANTENNA_TECH",
                "BAND",
                "SECTOR_CODE",
                "TECHNOLOGY",
            ]
        }
    },
    "antennas": {
        "sheets": {
            "antennas": [
                "Supplier",
                "Model",
                "Frequency",
                "HBEAMWIDTH",
                "VBEAMWIDTH",
                "Name",
                "Port",
                "Type",
                "GAIN",
            ]
        }
    },
    "suppliers": {"sheets": {"suppliers": ["SUPPLIER_NAME"]}},
    "regions": {"sheets": {"regions": ["name"]}},
    "wilayas": {"sheets": {"wilayas": ["wilaya_code", "wilaya_name", "region_name"]}},
    "communes": {"sheets": {"communes": ["commune_id", "commune_name", "wilaya_name"]}},
}

IMPORT_TEMPLATE_EXAMPLES = {
    "sites": {
        "sites": [
            "C28SU217",
            "SUT_SMAYER_ZRAYEF",
            2801,
            "Nokia",
            35.82046,
            4.78125,
            35.82046,
            "MSILA",
            520,
            "Wall Mounted",
            "Directional",
            18,
            "Example site",
        ]
    },
    "sectors": {
        "sectors": [
            "C28SU217_1",
            120,
            20,
            "C28SU217",
            "Coverage",
            "Example sector",
        ]
    },
    "cells": {
        "2G": ["2C28SU217_1", "2G", "GSM900", "2G", 2, 1, "ANT-900-65", "BSC01", "1201", "1", "63", 62],
        "3G": ["3C28SU217_1", "3G", "U2100", "3G", 2, 1, "ANT-2100-65", "RNC01", "1201", "1", 245, "10612"],
        "4G": ["4C28SU217_1", "4G", "L1800", "4G", 2, 1, "ANT-L18-65", "ENB2801", "2801", "12", 321, "1650"],
        "5G": ["5C28SU217_1", "5G", "N78", "5G", 2, 1, "ANT-N78-64T", "GNB2801", "1201", "15", 501, "636666"],
    },
    "mapping": {"mapping": ["MAP_0001", "1", "4G", "L1800", "1", "4G"]},
    "antennas": {"antennas": ["Nokia", "ANT-L18-65", 1800, 65, 6.5, "Panel 18", 2, "Panel", 17.8]},
    "suppliers": {"suppliers": ["Nokia"]},
    "regions": {"regions": ["Hauts Plateaux"]},
    "wilayas": {"wilayas": [28, "MSILA", "Hauts Plateaux"]},
    "communes": {"communes": [2801, "MSILA", "MSILA"]},
}

ALLPLAN_HEADERS = {
    "2G": [
        "CELLNAME", "LONGITUDE", "LATITUDE", "AZIMUTH", "HEIGHT", "ANTENNA",
        "ELECTRICALTILT", "MECHANICALTILT", "HBEAMWIDTH", "VBEAMWIDTH", "GAIN",
        "SITENAME", "SITE_TYPE", "INDOORFLAG", "SECTORID", "ARFCN", "LAC",
        "CELLIDENTITY", "BCCH", "BSIC(octal)", "Core or Buffer", "New Cell", "COMMUNE",
    ],
    "3G": [
        "CELLNAME", "LONGITUDE", "LATITUDE", "AZIMUTH", "HEIGHT", "ANTENNA",
        "ELECTRICALTILT", "MECHANICALTILT", "HBEAMWIDTH", "VBEAMWIDTH", "GAIN",
        "SITENAME", "SITE_TYPE", "INDOORFLAG", "SECTORID", "DL UARFCN", "LAC",
        "RNCID", "UTRANCELLIDENTITY", "Core or Buffer", "New Cell", "COMMUNE",
    ],
    "4G": [
        "CELLNAME", "LONGITUDE", "LATITUDE", "AZIMUTH", "HEIGHT", "ANTENNA",
        "ELECTRICALTILT", "MECHANICALTILT", "HBEAMWIDTH", "VBEAMWIDTH", "ANTENNAGAIN",
        "ENODEBNAME", "ENODEBID", "CI", "PCI", "DL EARFCN", "SITENAME", "SITE_TYPE",
        "INDOORFLAG", "SECTORID", "Core or Buffer", "New Cell", "COMMUNE",
    ],
}


def get_stats():
    return {
        'total_regions': Region.query.count(),
        'total_wilayas': Wilaya.query.count(),
        'total_communes': Commune.query.count(),
        'total_suppliers': Supplier.query.count(),
        'total_antennas': Antenna.query.count(),
        'total_cell_id_mapping': Mapping.query.count(),
        'total_cells': Cell.query.count(),
        'total_sectors': Sector.query.count(),
        'total_sites': Site.query.count(),
    }


def _normalize_tech_for_dashboard(value):
    tech = _normalize_tech(value)
    return tech if tech else "Other"


def get_dashboard_data(region_id=None):
    global_stats = get_stats()

    region_filter = None
    if region_id is not None:
        try:
            region_filter = int(region_id)
        except (TypeError, ValueError):
            region_filter = None

    site_base_query = Site.query
    if region_filter is not None:
        site_base_query = (
            site_base_query
            .join(Commune, Site.commune_id == Commune.id)
            .join(Wilaya, Commune.wilaya_id == Wilaya.id)
            .filter(Wilaya.region_id == region_filter)
        )

    total_sites = site_base_query.count()

    sector_base_query = Sector.query.join(Site, Sector.site_id == Site.id)
    if region_filter is not None:
        sector_base_query = (
            sector_base_query
            .join(Commune, Site.commune_id == Commune.id)
            .join(Wilaya, Commune.wilaya_id == Wilaya.id)
            .filter(Wilaya.region_id == region_filter)
        )
    total_sectors = sector_base_query.count()

    cell_base_query = Cell.query.outerjoin(Sector, Cell.sector_id == Sector.id).outerjoin(Site, Sector.site_id == Site.id)
    if region_filter is not None:
        cell_base_query = (
            cell_base_query
            .join(Commune, Site.commune_id == Commune.id)
            .join(Wilaya, Commune.wilaya_id == Wilaya.id)
            .filter(Wilaya.region_id == region_filter)
        )
    total_cells = cell_base_query.count()

    stats = {
        "total_sites": total_sites,
        "total_sectors": total_sectors,
        "total_cells": total_cells,
        "total_regions": global_stats["total_regions"],
        "total_wilayas": global_stats["total_wilayas"],
        "total_communes": global_stats["total_communes"],
        "total_suppliers": global_stats["total_suppliers"],
        "total_antennas": global_stats["total_antennas"],
        "total_cell_id_mapping": global_stats["total_cell_id_mapping"],
    }

    avg_sectors_per_site = round(total_sectors / total_sites, 2) if total_sites else 0
    avg_cells_per_sector = round(total_cells / total_sectors, 2) if total_sectors else 0

    tech_query = cell_base_query.with_entities(Cell.technology, func.count(Cell.id)).group_by(Cell.technology)
    tech_raw = tech_query.all()
    tech_counts = {"2G": 0, "3G": 0, "4G": 0, "Other": 0}
    for tech, count in tech_raw:
        tech_counts[_normalize_tech_for_dashboard(tech)] += count

    tech_distribution = []
    for label in ("2G", "3G", "4G", "Other"):
        value = tech_counts[label]
        pct = round((value * 100.0 / total_cells), 1) if total_cells else 0
        tech_distribution.append({"label": label, "value": value, "pct": pct})

    top_wilayas_query = (
        Wilaya.query.with_entities(Wilaya.name, func.count(Site.id).label("site_count"))
        .join(Commune, Commune.wilaya_id == Wilaya.id)
        .outerjoin(Site, Site.commune_id == Commune.id)
        .group_by(Wilaya.id, Wilaya.name)
    )
    if region_filter is not None:
        top_wilayas_query = top_wilayas_query.filter(Wilaya.region_id == region_filter)
    top_wilayas_raw = top_wilayas_query.order_by(func.count(Site.id).desc(), Wilaya.name.asc()).limit(8).all()
    max_wilaya = max((row.site_count for row in top_wilayas_raw), default=1)
    top_wilayas = [
        {
            "name": row.name,
            "count": row.site_count,
            "pct": round((row.site_count * 100.0 / max_wilaya), 1) if max_wilaya else 0,
        }
        for row in top_wilayas_raw
    ]

    top_suppliers_query = (
        site_base_query.with_entities(
            func.coalesce(Supplier.name, "Unassigned").label("supplier"),
            func.count(Site.id).label("site_count"),
        )
        .outerjoin(Supplier, Site.supplier_id == Supplier.id)
        .group_by(func.coalesce(Supplier.name, "Unassigned"))
    )
    top_suppliers_raw = top_suppliers_query.order_by(func.count(Site.id).desc()).limit(8).all()
    max_supplier = max((row.site_count for row in top_suppliers_raw), default=1)
    top_suppliers = [
        {
            "name": row.supplier,
            "count": row.site_count,
            "pct": round((row.site_count * 100.0 / max_supplier), 1) if max_supplier else 0,
        }
        for row in top_suppliers_raw
    ]

    sites_without_sectors = (
        site_base_query.outerjoin(Sector, Sector.site_id == Site.id)
        .filter(Sector.id.is_(None))
        .count()
    )
    sectors_without_cells = (
        sector_base_query.outerjoin(Cell, Cell.sector_id == Sector.id)
        .filter(Cell.id.is_(None))
        .count()
    )
    cells_without_sector_query = Cell.query.filter(Cell.sector_id.is_(None))
    if region_filter is not None:
        cells_without_sector_query = (
            Cell.query.outerjoin(Sector, Cell.sector_id == Sector.id)
            .outerjoin(Site, Sector.site_id == Site.id)
            .join(Commune, Site.commune_id == Commune.id)
            .join(Wilaya, Commune.wilaya_id == Wilaya.id)
            .filter(Wilaya.region_id == region_filter)
            .filter(Cell.sector_id.is_(None))
        )
    cells_without_sector = cells_without_sector_query.count()

    cells_without_antenna_query = cell_base_query.filter(Cell.antenna_id.is_(None))
    cells_without_antenna = cells_without_antenna_query.count()

    sites_without_supplier = site_base_query.filter(Site.supplier_id.is_(None)).count()

    mapping_codes = {
        (code or "").strip()
        for (code,) in Mapping.query.with_entities(Mapping.cell_code).distinct().all()
        if (code or "").strip()
    }
    mapped_cells = 0
    for (cellname,) in cell_base_query.with_entities(Cell.cellname).all():
        code = _extract_cell_code(cellname)
        if code and code in mapping_codes:
            mapped_cells += 1
    mapping_coverage = round((mapped_cells * 100.0 / total_cells), 1) if total_cells else 0

    data_quality = {
        "sites_without_sectors": sites_without_sectors,
        "sectors_without_cells": sectors_without_cells,
        "cells_without_sector": cells_without_sector,
        "cells_without_antenna": cells_without_antenna,
        "sites_without_supplier": sites_without_supplier,
        "mapped_cells": mapped_cells,
        "mapping_coverage_pct": mapping_coverage,
    }

    return {
        "stats": stats,
        "avg_sectors_per_site": avg_sectors_per_site,
        "avg_cells_per_sector": avg_cells_per_sector,
        "tech_distribution": tech_distribution,
        "top_wilayas": top_wilayas,
        "top_suppliers": top_suppliers,
        "data_quality": data_quality,
        "region_filter": region_filter,
        "regions": Region.query.order_by(Region.name.asc()).all(),
        "charts": {
            "tech_labels": [row["label"] for row in tech_distribution],
            "tech_values": [row["value"] for row in tech_distribution],
            "wilaya_labels": [row["name"] for row in top_wilayas],
            "wilaya_values": [row["count"] for row in top_wilayas],
            "supplier_labels": [row["name"] for row in top_suppliers],
            "supplier_values": [row["count"] for row in top_suppliers],
            "mapping": {
                "mapped": mapped_cells,
                "unmapped": max(total_cells - mapped_cells, 0),
            },
        },
        "generated_at": datetime.utcnow(),
    }


def _normalize_tech(value):
    tech = (value or "").strip().upper()
    if tech.startswith("2") or tech in {"GSM"}:
        return "2G"
    if tech.startswith("3") or tech in {"UMTS", "WCDMA"}:
        return "3G"
    if tech.startswith("4") or tech in {"LTE"}:
        return "4G"
    return None


def _extract_sector_id(cellname):
    if not cellname:
        return None
    parts = str(cellname).rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return int(parts[1])
    return None


def _extract_cell_code(cellname):
    if not cellname:
        return None
    parts = str(cellname).rsplit("_", 1)
    if len(parts) == 2 and parts[1]:
        return parts[1]
    return None


def _parse_cell_list(raw_text):
    tokens = re.split(r"[,\s;]+", raw_text or "")
    ordered = []
    seen = set()
    for token in tokens:
        cell = token.strip()
        if not cell:
            continue
        if cell not in seen:
            seen.add(cell)
            ordered.append(cell)
    return ordered


def _parse_cell_file(file_storage):
    filename = (file_storage.filename or "").lower()
    raw = file_storage.read()
    if not raw:
        return []

    values = []
    if filename.endswith(".xlsx"):
        wb = load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_col=1, max_col=1, values_only=True):
            values.append(row[0])
    elif filename.endswith(".csv"):
        text = raw.decode("utf-8-sig", errors="ignore")
        reader = csv.reader(io.StringIO(text))
        for row in reader:
            values.append(row[0] if row else None)
    else:
        raise ValueError("Format non supporté. Utilisez .xlsx ou .csv.")

    ordered = []
    seen = set()
    for value in values:
        cell = str(value or "").strip()
        if not cell:
            continue
        if cell.lower() in {"cellname", "cell_name", "cell", "cells"}:
            continue
        if cell not in seen:
            seen.add(cell)
            ordered.append(cell)
    return ordered


@main_bp.route('/')
@main_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', dashboard=get_dashboard_data())


@main_bp.route('/import_export')
@login_required
def import_export():
    return render_template('import_export.html', title='Import & Export')


@main_bp.route('/site-profile/<int:site_id>', methods=['GET'])
@login_required
def site_profile(site_id):
    # 1) Load site + enforce access scope for non-admin users.
    site = Site.query.get(site_id)
    if not site:
        return jsonify({"success": False, "message": "Site not found."}), 404

    accessible = get_accessible_site_ids()
    if accessible is not None and site.id not in accessible:
        return jsonify({"success": False, "message": "Access denied for this site."}), 403

    # 2) Gather full local topology for the selected site.
    sectors = site.sectors.order_by(Sector.code_sector.asc()).all()
    cells = []
    tech_set = set()
    antenna_models = set()
    for sector in sectors:
        sector_cells = sector.cells.order_by(Cell.cellname.asc()).all()
        cells.extend(sector_cells)
        for cell in sector_cells:
            tech_val = (cell.technology or "").strip().upper()
            if tech_val:
                tech_set.add(tech_val)
            if cell.antenna and cell.antenna.model:
                antenna_models.add(cell.antenna.model)

    # 3) Compute nearest sites from the same accessible perimeter.
    base_query = Site.query
    if accessible is not None:
        if not accessible:
            base_query = base_query.filter(False)
        else:
            base_query = base_query.filter(Site.id.in_(list(accessible)))
    candidates = base_query.filter(Site.id != site.id).all()

    nearest = []
    if site.latitude is not None and site.longitude is not None:
        for other in candidates:
            if other.latitude is None or other.longitude is None:
                continue
            dist_km = _haversine_km(site.latitude, site.longitude, other.latitude, other.longitude)
            nearest.append(
                {
                    "id": other.id,
                    "code_site": other.code_site,
                    "name": other.name,
                    "latitude": other.latitude,
                    "longitude": other.longitude,
                    "distance_km": round(dist_km, 2),
                }
            )
        nearest.sort(key=lambda row: row["distance_km"])
        nearest = nearest[:5]

    # 4) Return a single JSON payload consumed by the Site Profile modal.
    response = {
        "success": True,
        "site": {
            "id": site.id,
            "code_site": site.code_site,
            "name": site.name,
            "address": site.address,
            "latitude": site.latitude,
            "longitude": site.longitude,
            "altitude": site.altitude,
            "status": site.status,
            "support_nature": site.support_nature,
            "support_type": site.support_type,
            "support_height": site.support_height,
            "supplier_name": site.supplier.name if site.supplier else None,
            "commune_name": site.commune.name if site.commune else None,
            "wilaya_name": site.commune.wilaya.name if site.commune and site.commune.wilaya else None,
            "region_name": site.commune.wilaya.region.name if site.commune and site.commune.wilaya and site.commune.wilaya.region else None,
            "sectors_count": len(sectors),
            "cells_count": len(cells),
            "techs": sorted(tech_set),
            "antennas": sorted(antenna_models),
        },
        "sectors": [
            {
                "id": s.id,
                "code_sector": s.code_sector,
                "azimuth": s.azimuth,
                "hba": s.hba,
                "coverage_goal": s.coverage_goal,
                "cells_count": s.cells.count(),
            }
            for s in sectors
        ],
        "cells": [
            {
                "id": c.id,
                "cellname": c.cellname,
                "technology": c.technology,
                "frequency": c.frequency,
                "sector_code": c.sector.code_sector if c.sector else None,
                "antenna_model": c.antenna.model if c.antenna else None,
            }
            for c in cells
        ],
        "nearest_sites": nearest,
    }
    return jsonify(response)


@main_bp.route('/import-template/<entity>', methods=['GET'])
@login_required
def download_import_template(entity):
    key = (entity or "").strip().lower()
    if key in {"vendor", "vendors", "supplier"}:
        key = "suppliers"

    spec = IMPORT_TEMPLATE_SPECS.get(key)
    if not spec:
        flash(f'No template available for entity "{entity}".', "warning")
        return redirect(url_for("main.import_export"))

    wb = Workbook()
    wb.remove(wb.active)
    for sheet_name, headers in spec.get("sheets", {}).items():
        ws = wb.create_sheet(sheet_name[:31] or "Sheet1")
        ws.append(headers)
        sample_row = IMPORT_TEMPLATE_EXAMPLES.get(key, {}).get(sheet_name)
        if sample_row and len(sample_row) == len(headers):
            ws.append(sample_row)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"{key}_import_template.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@main_bp.route('/allplan_export')
@login_required
def allplan_export_page():
    return render_template('allplan_export.html', title='Allplan Export')


@main_bp.route('/kml_export')
@login_required
def kml_export_page():
    return render_template('kml_export.html', title='KML Export')


@main_bp.route('/export-data/<entity>', methods=['GET'])
@login_required
def export_data(entity):
    flash(f"Démarrage de l'exportation pour l'entité \"{entity.upper()}\"...", "info")
    return redirect(url_for('main.import_export'))


@main_bp.route('/export-allplan', methods=['POST'])
@login_required
@csrf_protect
def export_allplan():
    uploaded_file = request.files.get("cell_file")
    raw_cells = request.form.get('cell_list', '')

    cell_names = []
    if uploaded_file and uploaded_file.filename:
        try:
            cell_names = _parse_cell_file(uploaded_file)
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("main.import_export"))
    else:
        cell_names = _parse_cell_list(raw_cells)

    if not cell_names:
        flash('Veuillez fournir un fichier (ou une liste texte) contenant au moins une cellule.', 'warning')
        return redirect(url_for('main.import_export'))

    cells = (
        Cell.query.options(
            joinedload(Cell.sector).joinedload(Sector.site).joinedload(Site.commune),
            joinedload(Cell.antenna),
        )
        .filter(Cell.cellname.in_(cell_names))
        .all()
    )

    by_name = {c.cellname: c for c in cells}
    rows = {'2G': [], '3G': [], '4G': []}
    not_found_rows = []

    cell_codes = {_extract_cell_code(name) for name in cell_names}
    cell_codes.discard(None)
    mappings = Mapping.query.filter(Mapping.cell_code.in_(list(cell_codes))).all() if cell_codes else []

    mapping_full = {}
    mapping_tech = {}
    mapping_code = {}
    for m in mappings:
        code = (m.cell_code or "").strip()
        tech_key = (m.technology or "").strip().upper()
        band_key = (m.band or "").strip()
        if code and tech_key and band_key:
            mapping_full[(code, tech_key, band_key)] = m.sector_code
        if code and tech_key:
            mapping_tech[(code, tech_key)] = m.sector_code
        if code:
            mapping_code[code] = m.sector_code

    for name in cell_names:
        cell = by_name.get(name)
        if not cell:
            not_found_rows.append({
                "CELLNAME": name,
                "TECHNOLOGY": None,
                "ISSUE": "CELL_MISSING",
                "DETAIL": "Cellule introuvable dans la table Cell.",
            })
            continue
        tech = _normalize_tech(cell.technology)
        if tech not in rows:
            not_found_rows.append({
                "CELLNAME": cell.cellname,
                "TECHNOLOGY": cell.technology,
                "ISSUE": "TECHNOLOGY_UNSUPPORTED",
                "DETAIL": "Technologie non supportée pour export Allplan.",
            })
            continue

        sector = cell.sector
        site = sector.site if sector else None
        antenna = cell.antenna
        commune_name = site.commune.name if site and site.commune else None
        site_type = site.support_type if site else None
        cell_code = _extract_cell_code(cell.cellname)
        tech_key = (cell.technology or "").strip().upper()
        band_key = (cell.frequency or "").strip() if cell.frequency is not None else ""
        sector_id_from_mapping = (
            mapping_full.get((cell_code, tech_key, band_key))
            or mapping_tech.get((cell_code, tech_key))
            or mapping_code.get(cell_code)
        )

        issues = []
        if not sector:
            issues.append("SECTOR_MISSING")
        if sector and not site:
            issues.append("SITE_MISSING")
        if not sector_id_from_mapping:
            issues.append("MAPPING_MISSING")
        if issues:
            not_found_rows.append({
                "CELLNAME": cell.cellname,
                "TECHNOLOGY": cell.technology,
                "ISSUE": ", ".join(issues),
                "DETAIL": "Verifier les relations Cell->Sector->Site et la table Mapping.",
            })

        common = {
            'CELLNAME': cell.cellname,
            'LONGITUDE': site.longitude if site else None,
            'LATITUDE': site.latitude if site else None,
            'AZIMUTH': sector.azimuth if sector else None,
            'HEIGHT': sector.hba if sector else None,
            'ANTENNA': antenna.model if antenna else None,
            'ELECTRICALTILT': cell.tilt_electrical,
            'MECHANICALTILT': cell.tilt_mechanical,
            'HBEAMWIDTH': antenna.hbeamwidth if antenna else None,
            'VBEAMWIDTH': antenna.vbeamwidth if antenna else None,
            'GAIN': antenna.gain if antenna else None,
            'ANTENNAGAIN': antenna.gain if antenna else None,
            'SITENAME': site.code_site if site else None,
            'SITE_TYPE': site_type,
            'INDOORFLAG': None,
            'SECTORID': sector_id_from_mapping,
            'ARFCN': None,
            'DL UARFCN': None,
            'DL EARFCN': cell.frequency,
            'LAC': None,
            'CELLIDENTITY': None,
            'BCCH': None,
            'BSIC(octal)': None,
            'RNCID': None,
            'UTRANCELLIDENTITY': None,
            'ENODEBNAME': None,
            'ENODEBID': None,
            'CI': None,
            'PCI': None,
            'Core or Buffer': 'Core',
            'New Cell': None,
            'COMMUNE': commune_name,
        }
        rows[tech].append(common)

    wb = Workbook()
    wb.remove(wb.active)

    for tech in ('2G', '3G', '4G'):
        ws = wb.create_sheet(tech)
        headers = ALLPLAN_HEADERS[tech]
        ws.append(headers)
        for row in rows[tech]:
            ws.append([row.get(h) for h in headers])

    ws_nf = wb.create_sheet("NOT_FOUND")
    nf_headers = ["CELLNAME", "TECHNOLOGY", "ISSUE", "DETAIL"]
    ws_nf.append(nf_headers)
    for row in not_found_rows:
        ws_nf.append([row.get(h) for h in nf_headers])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"allplan_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
