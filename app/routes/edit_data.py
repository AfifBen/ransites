import logging
import json
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from flask import Blueprint, current_app, jsonify, request

from app import db
from app.models import Antenna, Cell, Cell2G, Cell3G, Cell4G, Cell5G, Commune, Region, Sector, Site, Supplier, User, Wilaya
from app.security import append_audit_event, csrf_protect, get_accessible_site_ids, is_admin_user, login_required

edit_data_bp = Blueprint('edit_data', __name__)
logger = logging.getLogger(__name__)

MODEL_MAP = {
    'site': Site,
    'sites': Site,
    'sector': Sector,
    'sectors': Sector,
    'cell': Cell,
    'cells': Cell,
    'region': Region,
    'regions': Region,
    'wilaya': Wilaya,
    'wilayas': Wilaya,
    'commune': Commune,
    'communes': Commune,
    'antenna': Antenna,
    'antennas': Antenna,
    'vendor': Supplier,
    'vendors': Supplier,
    'supplier': Supplier,
    'user': User,
    'users': User,
}


def _to_int_or_none(raw):
    if raw is None:
        return None
    txt = str(raw).strip()
    if not txt:
        return None
    try:
        return int(float(txt))
    except (TypeError, ValueError):
        return None


def _to_float_or_none(raw):
    if raw is None:
        return None
    txt = str(raw).strip()
    if not txt:
        return None
    try:
        return float(txt)
    except (TypeError, ValueError):
        return None


def _fetch_ground_altitude(latitude, longitude):
    try:
        query = urlencode({"locations": f"{latitude},{longitude}"})
        url = f"https://api.open-elevation.com/api/v1/lookup?{query}"
        with urlopen(url, timeout=4) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        results = payload.get("results") or []
        if not results:
            return None
        val = results[0].get("elevation")
        return float(val) if val is not None else None
    except Exception:
        return None


def _auto_fill_site_altitude(site):
    if site is None or site.altitude not in (None, ""):
        return
    lat = _to_float_or_none(site.latitude)
    lon = _to_float_or_none(site.longitude)
    if lat is None or lon is None:
        return
    alt = _fetch_ground_altitude(lat, lon)
    if alt is not None:
        site.altitude = round(float(alt), 1)


def _auto_assign_cell_sector(cell):
    if not cell:
        return False
    cellname = (cell.cellname or "").strip()
    tech = (cell.technology or "").strip().upper()
    freq = (cell.frequency or "").strip()
    if not cellname or not tech or not freq:
        return False
    try:
        from app.routes.import_data import resolve_sector_id_for_cell
        with db.session.no_autoflush:
            sector_id, _ = resolve_sector_id_for_cell(cellname, tech, freq)
        if sector_id is not None:
            cell.sector_id = int(sector_id)
            return True
    except Exception:
        logger.exception("Cell sector auto-resolution failed")
    return False


def _append_admin_runtime_log(entity, action, status, message):
    # Shared JSON index consumed by Administration > Import Logs page.
    try:
        reports_dir = Path(current_app.instance_path) / "import_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        index_path = reports_dir / "import_reports_index.json"
        rows = []
        if index_path.exists():
            rows = json.loads(index_path.read_text(encoding="utf-8"))
        rows.append({
            "id": f"log_{uuid.uuid4().hex}",
            "created_at": datetime.utcnow().isoformat(),
            "entity": (entity or "").strip().lower(),
            "import_kind": action,
            "source_file": "",
            "status": status,
            "message": str(message or ""),
            "failed_rows_count": 0,
            "report_path": "",
            "log_source": "runtime",
        })
        rows = sorted(rows, key=lambda x: x.get("created_at", ""), reverse=True)
        index_path.write_text(json.dumps(rows, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception:
        logger.exception("Failed to append admin runtime log")


def _sync_cell_profile(cell, data):
    tech = (getattr(cell, "technology", "") or "").strip().upper()

    if tech == "2G":
        cell.profile_3g = None
        cell.profile_4g = None
        cell.profile_5g = None
        p = cell.profile_2g or Cell2G()
        p.bsc = (data.get("bsc") or "").strip() or None
        p.lac = (data.get("lac_2g") or "").strip() or None
        p.rac = (data.get("rac_2g") or "").strip() or None
        p.bcch = _to_int_or_none(data.get("bcch"))
        p.bsic = (data.get("bsic") or "").strip() or None
        p.ci = _to_int_or_none(data.get("ci_2g"))
        cell.profile_2g = p
    elif tech == "3G":
        cell.profile_2g = None
        cell.profile_4g = None
        cell.profile_5g = None
        p = cell.profile_3g or Cell3G()
        p.lac = (data.get("lac_3g") or "").strip() or None
        p.rac = (data.get("rac_3g") or "").strip() or None
        p.psc = _to_int_or_none(data.get("psc"))
        p.rnc = (data.get("rnc") or "").strip() or None
        p.dlarfcn = (data.get("dlarfcn") or "").strip() or None
        p.ci = _to_int_or_none(data.get("ci_3g"))
        cell.profile_3g = p
    elif tech == "4G":
        cell.profile_2g = None
        cell.profile_3g = None
        cell.profile_5g = None
        p = cell.profile_4g or Cell4G()
        p.enodeb = (data.get("enodeb") or "").strip() or None
        p.tac = (data.get("tac") or "").strip() or None
        p.rsi = (data.get("rsi_4g") or "").strip() or None
        p.pci = _to_int_or_none(data.get("pci_4g"))
        p.earfcn = (data.get("earfcn") or "").strip() or None
        p.ci = _to_int_or_none(data.get("ci_4g"))
        cell.profile_4g = p
    elif tech == "5G":
        cell.profile_2g = None
        cell.profile_3g = None
        cell.profile_4g = None
        p = cell.profile_5g or Cell5G()
        p.gnodeb = (data.get("gnodeb") or "").strip() or None
        p.lac = (data.get("lac_5g") or "").strip() or None
        p.rsi = (data.get("rsi_5g") or "").strip() or None
        p.pci = _to_int_or_none(data.get("pci_5g"))
        p.arfcn = (data.get("arfcn") or "").strip() or None
        p.ci = _to_int_or_none(data.get("ci_5g"))
        cell.profile_5g = p


def _item_allowed(item):
    if is_admin_user():
        return True

    accessible_sites = get_accessible_site_ids()
    if accessible_sites is None:
        return True

    if isinstance(item, Site):
        return item.id in accessible_sites
    if isinstance(item, Sector):
        return bool(item.site and item.site.id in accessible_sites)
    if isinstance(item, Cell):
        return bool(item.sector and item.sector.site and item.sector.site.id in accessible_sites)

    return False


@edit_data_bp.route('/get_item/<entity>/<int:item_id>', methods=['GET'])
@login_required
def get_item(entity, item_id):
    model = MODEL_MAP.get(entity.lower())
    if not model:
        return jsonify({'error': f"Entite '{entity}' non reconnue"}), 400

    item = db.session.get(model, item_id)
    if not item:
        return jsonify({'error': 'Element non trouve'}), 404

    if model is User and not is_admin_user():
        return jsonify({'error': 'Acces refuse'}), 403
    if not _item_allowed(item):
        return jsonify({'error': 'Acces refuse'}), 403

    data = {column.name: getattr(item, column.name) for column in item.__table__.columns}

    if model is User:
        data['region_ids'] = [r.id for r in item.assigned_regions]
        data['wilaya_ids'] = [w.id for w in item.assigned_wilayas]
        data['commune_ids'] = [c.id for c in item.assigned_communes]
        data['site_ids'] = [s.id for s in item.assigned_sites]
        data.pop('password_hash', None)
    elif model is Cell:
        data['bsc'] = item.profile_2g.bsc if item.profile_2g else None
        data['lac_2g'] = item.profile_2g.lac if item.profile_2g else None
        data['rac_2g'] = item.profile_2g.rac if item.profile_2g else None
        data['bcch'] = item.profile_2g.bcch if item.profile_2g else None
        data['bsic'] = item.profile_2g.bsic if item.profile_2g else None
        data['ci_2g'] = item.profile_2g.ci if item.profile_2g else None
        data['lac_3g'] = item.profile_3g.lac if item.profile_3g else None
        data['rac_3g'] = item.profile_3g.rac if item.profile_3g else None
        data['psc'] = item.profile_3g.psc if item.profile_3g else None
        data['rnc'] = item.profile_3g.rnc if item.profile_3g else None
        data['dlarfcn'] = item.profile_3g.dlarfcn if item.profile_3g else None
        data['ci_3g'] = item.profile_3g.ci if item.profile_3g else None
        data['enodeb'] = item.profile_4g.enodeb if item.profile_4g else None
        data['tac'] = item.profile_4g.tac if item.profile_4g else None
        data['rsi_4g'] = item.profile_4g.rsi if item.profile_4g else None
        data['pci_4g'] = item.profile_4g.pci if item.profile_4g else None
        data['earfcn'] = item.profile_4g.earfcn if item.profile_4g else None
        data['ci_4g'] = item.profile_4g.ci if item.profile_4g else None
        data['gnodeb'] = item.profile_5g.gnodeb if item.profile_5g else None
        data['lac_5g'] = item.profile_5g.lac if item.profile_5g else None
        data['rsi_5g'] = item.profile_5g.rsi if item.profile_5g else None
        data['pci_5g'] = item.profile_5g.pci if item.profile_5g else None
        data['arfcn'] = item.profile_5g.arfcn if item.profile_5g else None
        data['ci_5g'] = item.profile_5g.ci if item.profile_5g else None

    return jsonify(data)


@edit_data_bp.route('/update_item/<entity>', methods=['POST'])
@login_required
@csrf_protect
def update_item(entity):
    data = request.get_json()
    is_cell_entity = (entity or "").strip().lower() in {"cell", "cells"}

    if not data or 'id' not in data:
        if is_cell_entity:
            _append_admin_runtime_log("cells", "cell_edit", "FAILED", "ID missing in update payload.")
        return jsonify({'success': False, 'message': 'ID manquant'}), 400

    model = MODEL_MAP.get(entity.lower())
    if not model:
        if is_cell_entity:
            _append_admin_runtime_log("cells", "cell_edit", "FAILED", f"Invalid entity '{entity}' for update.")
        return jsonify({'success': False, 'message': f"Entite '{entity}' invalide"}), 400

    item = db.session.get(model, data['id'])
    if not item:
        if is_cell_entity:
            _append_admin_runtime_log("cells", "cell_edit", "FAILED", f"Cell id={data.get('id')} not found.")
        return jsonify({'success': False, 'message': 'Element non trouve'}), 404

    if model is User and not is_admin_user():
        return jsonify({'success': False, 'message': 'Acces reserve a l administrateur.'}), 403
    if not _item_allowed(item):
        return jsonify({'success': False, 'message': 'Acces refuse'}), 403

    try:
        if model is User:
            username = (data.get('username') or '').strip()
            if not username:
                return jsonify({'success': False, 'message': 'Username obligatoire'}), 400

            conflict = User.query.filter(User.username == username, User.id != item.id).first()
            if conflict:
                return jsonify({'success': False, 'message': 'Username deja utilise'}), 400

            item.username = username
            item.is_admin = bool(data.get('is_admin', False))
            item.is_active = bool(data.get('is_active', True))

            password = (data.get('password') or '').strip()
            if password:
                if len(password) < 6:
                    return jsonify({'success': False, 'message': 'Mot de passe min 6 caracteres'}), 400
                item.set_password(password)

            region_ids = [int(v) for v in data.get('region_ids', []) if str(v).isdigit()]
            wilaya_ids = [int(v) for v in data.get('wilaya_ids', []) if str(v).isdigit()]
            commune_ids = [int(v) for v in data.get('commune_ids', []) if str(v).isdigit()]
            site_ids = [int(v) for v in data.get('site_ids', []) if str(v).isdigit()]

            item.assigned_regions = Region.query.filter(Region.id.in_(region_ids)).all() if region_ids else []
            item.assigned_wilayas = Wilaya.query.filter(Wilaya.id.in_(wilaya_ids)).all() if wilaya_ids else []
            item.assigned_communes = Commune.query.filter(Commune.id.in_(commune_ids)).all() if commune_ids else []
            item.assigned_sites = Site.query.filter(Site.id.in_(site_ids)).all() if site_ids else []

            db.session.commit()
            append_audit_event("update", entity, "SUCCESS", f"user id={item.id}")
            return jsonify({'success': True, 'message': 'User mis a jour avec succes'})

        for key, value in data.items():
            if key.lower() != 'id' and hasattr(item, key):
                setattr(item, key, value if value != '' else None)

        if model is Site:
            _auto_fill_site_altitude(item)

        if model is Cell:
            item.technology = (item.technology or '').strip().upper()
            _sync_cell_profile(item, data)
            _auto_assign_cell_sector(item)
            if not item.sector_id:
                _append_admin_runtime_log("cells", "cell_edit", "FAILED", f"Cell '{item.cellname}' sector auto-resolution failed.")
                return jsonify({'success': False, 'message': 'Sector auto-resolution failed (check mapping/sector/site).'}), 400
            if not _item_allowed(item):
                _append_admin_runtime_log("cells", "cell_edit", "FAILED", f"Cell '{item.cellname}' resolved sector outside scope.")
                return jsonify({'success': False, 'message': 'Resolved sector is outside your scope.'}), 403

        db.session.commit()
        append_audit_event("update", entity, "SUCCESS", f"id={item.id}")
        return jsonify({'success': True, 'message': f"{entity.capitalize()} mis a jour avec succes"})

    except Exception as e:
        db.session.rollback()
        logger.exception('UPDATE ERROR')
        append_audit_event("update", entity, "FAILED", str(e))
        if is_cell_entity or model is Cell:
            _append_admin_runtime_log("cells", "cell_edit", "FAILED", f"Unhandled update error: {str(e)}")
        return jsonify({'success': False, 'message': f"Erreur lors de la mise a jour : {str(e)}"}), 500
