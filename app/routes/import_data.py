from flask import Blueprint, request, redirect, url_for, flash, jsonify, current_app, send_file
import pandas as pd 
import io 
from sqlalchemy import select 
from datetime import datetime
import numpy as np 
import logging
import traceback
import threading
import uuid
import tempfile
from pathlib import Path
import re
import json
import time
from urllib.parse import urlencode
from urllib.request import urlopen
from app.security import append_audit_event, login_required, csrf_protect, admin_required
# --- IMPORTS CRITIQUES : Ajustez si nécessaire ---
try:
    from app import db 
    # Ajout du modèle Cell
    from app.models import Region, Wilaya, Commune, Site, Antenna, Supplier, Sector, Mapping, Cell, Cell2G, Cell3G, Cell4G, Cell5G
except ImportError:
    # Définir des classes factices si l'environnement Flask/SQLAlchemy n'est pas complet
    class DummyDB:
        def __init__(self):
            class DummySession:
                def no_autoflush(self): return self
                def __enter__(self): pass
                def __exit__(self, exc_type, exc_val, exc_tb): pass
                def execute(self, statement): return self 
                def scalars(self): return self
                def first(self): return None
                def scalar_one_or_none(self): return None
            self.session = DummySession()
        def session(self): return self.session
        def rollback(self): pass
        def commit(self): pass
        def add(self, obj): pass
    db = DummyDB()
    class Region: pass
    class Wilaya: pass
    class Commune: pass
    class Site: 
        def __init__(self, **kwargs):
            for k, v in kwargs.items(): setattr(self, k, v)
    class Antenna:
        def __init__(self, **kwargs):
            self.model = kwargs.get('model')
            self.frequency = kwargs.get('frequency')
            self.id = 1 # Dummy ID
            for k, v in kwargs.items(): setattr(self, k, v)
    class Supplier: pass
    class Sector:
        def __init__(self, **kwargs):
            self.code_sector = kwargs.get('code_sector') 
            for k, v in kwargs.items(): setattr(self, k, v)
    class Mapping:
        def __init__(self, **kwargs):
            self.map_id = kwargs.get('map_id')
            for k, v in kwargs.items(): setattr(self, k, v)
    # Ajout de la classe factice Cell
    class Cell:
        def __init__(self, **kwargs):
            self.cellname = kwargs.get('cellname')
            for k, v in kwargs.items(): setattr(self, k, v)
    class Cell2G:
        pass
    class Cell3G:
        pass
    class Cell4G:
        pass
    class Cell5G:
        pass
# --- FIN DES IMPORTS ---


# Création du Blueprint dédié à l'importation
import_bp = Blueprint('import_bp', __name__) 
logger = logging.getLogger(__name__)

_fpall_jobs = {}
_fpall_jobs_lock = threading.Lock()
_latest_import_reports = {}
_latest_import_reports_lock = threading.Lock()


def _reports_dir():
    reports_dir = Path(current_app.instance_path) / "import_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def _reports_index_path():
    return _reports_dir() / "import_reports_index.json"


def _load_reports_index():
    index_path = _reports_index_path()
    if not index_path.exists():
        return []
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to read import reports index")
        return []


def _save_reports_index(rows):
    index_path = _reports_index_path()
    index_path.write_text(json.dumps(rows, ensure_ascii=True, indent=2), encoding="utf-8")


def _register_report_entry(entry):
    try:
        from flask_login import current_user
        if "username" not in entry and getattr(current_user, "is_authenticated", False):
            entry["username"] = getattr(current_user, "username", "unknown")
    except Exception:
        entry.setdefault("username", "system")
    rows = _load_reports_index()
    rows.append(entry)
    rows = sorted(rows, key=lambda x: x.get("created_at", ""), reverse=True)
    _save_reports_index(rows)


def _append_runtime_error_log(entity, action, message):
    _register_report_entry({
        "id": f"log_{uuid.uuid4().hex}",
        "created_at": datetime.utcnow().isoformat(),
        "entity": (entity or "").strip().lower(),
        "import_kind": action,
        "source_file": "",
        "status": "FAILED",
        "message": str(message or ""),
        "failed_rows_count": 0,
        "report_path": "",
        "log_source": "runtime",
    })


def _find_report_entry(report_id):
    for row in _load_reports_index():
        if str(row.get("id", "")) == str(report_id):
            return row
    return None


def _coerce_import_result(result):
    if isinstance(result, tuple):
        if len(result) == 3:
            success, message, details = result
        elif len(result) == 2:
            success, message = result
            details = {}
        else:
            return False, "Import function returned an invalid result format.", {}
        if details is None:
            details = {}
        if not isinstance(details, dict):
            details = {"raw_details": str(details)}
        details.setdefault("failed_rows", [])
        return bool(success), str(message), details
    return False, "Import function returned an invalid result.", {}


def _set_fpall_job(job_id, **fields):
    with _fpall_jobs_lock:
        job = _fpall_jobs.get(job_id, {})
        job.update(fields)
        _fpall_jobs[job_id] = job
        return job


def _get_fpall_job(job_id):
    with _fpall_jobs_lock:
        return dict(_fpall_jobs.get(job_id, {}))


def _extract_validation_report_from_message(message):
    text = str(message or "")
    marker = "validation_"
    idx = text.lower().find(marker)
    if idx < 0:
        return None
    end = text.find(".xlsx", idx)
    if end < 0:
        return None
    return text[idx:end + 5]


def _write_fpall_final_report(job_id, source_filename, success, message, started_at, finished_at, details=None):
    details = details or {}
    report_path = _reports_dir() / f"fpall_report_{job_id}.xlsx"

    validation_report = _extract_validation_report_from_message(message)
    summary_df = pd.DataFrame([
        {
            "job_id": job_id,
            "source_file": source_filename,
            "status": "SUCCESS" if success else "FAILED",
            "message": message,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": round((finished_at - started_at).total_seconds(), 2),
            "validation_report_file": validation_report or "",
        }
    ])
    failed_rows = details.get("failed_rows") or []
    failed_df = pd.DataFrame(failed_rows)
    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        if not failed_df.empty:
            failed_df.to_excel(writer, sheet_name="Failed Rows", index=False)

    _register_report_entry({
        "id": f"fpall_{job_id}",
        "created_at": finished_at.isoformat(),
        "entity": "cells",
        "import_kind": "fpall",
        "source_file": source_filename or "",
        "status": "SUCCESS" if success else "FAILED",
        "message": str(message or ""),
        "failed_rows_count": int(len(failed_rows)),
        "report_path": str(report_path),
    })
    return str(report_path)


def _run_fpall_job(app, job_id, temp_file_path, original_filename):
    started_at = datetime.utcnow()
    _set_fpall_job(
        job_id,
        status="processing",
        progress=15,
        message="Reading FPall workbook...",
        started_at=started_at.isoformat(),
        processed_rows=0,
        total_rows=0,
        eta_seconds=None,
    )

    try:
        with open(temp_file_path, "rb") as f:
            content = f.read()

        class _MemoryUpload:
            def __init__(self, filename, payload):
                self.filename = filename
                self._payload = payload
            def read(self):
                return self._payload

        def _progress_update(**kwargs):
            _set_fpall_job(job_id, **kwargs)

        with app.app_context():
            _set_fpall_job(job_id, progress=45, message="Normalizing sheets and validating columns...")
            success, message, details = process_file_data(
                _MemoryUpload(original_filename, content),
                "cells",
                progress_cb=_progress_update,
            )
            _set_fpall_job(job_id, progress=96, message="Finalizing import report...", eta_seconds=None)

            finished_at = datetime.utcnow()
            report_path = _write_fpall_final_report(
                job_id=job_id,
                source_filename=original_filename,
                success=success,
                message=message,
                started_at=started_at,
                finished_at=finished_at,
                details=details,
            )

            _set_fpall_job(
                job_id,
                status="completed" if success else "failed",
                progress=100,
                message=message,
                finished_at=finished_at.isoformat(),
                report_path=report_path,
                eta_seconds=None,
                duration_seconds=round((finished_at - started_at).total_seconds(), 2),
            )
    except Exception as exc:
        logger.exception("FPall async import failed")
        finished_at = datetime.utcnow()
        with app.app_context():
            report_path = _write_fpall_final_report(
                job_id=job_id,
                source_filename=original_filename,
                success=False,
                message=f"Unhandled FPall import error: {exc}",
                started_at=started_at,
                finished_at=finished_at,
            )
        _set_fpall_job(
            job_id,
            status="failed",
            progress=100,
            message=f"Unhandled FPall import error: {exc}",
            finished_at=finished_at.isoformat(),
            report_path=report_path,
            eta_seconds=None,
            duration_seconds=round((finished_at - started_at).total_seconds(), 2),
        )
    finally:
        try:
            Path(temp_file_path).unlink(missing_ok=True)
        except Exception:
            pass


def _write_entity_import_report(entity, source_filename, success, message, details=None, import_kind="standard"):
    details = details or {}
    report_id = uuid.uuid4().hex
    out_path = _reports_dir() / f"{entity}_import_report_{report_id}.xlsx"

    msg = str(message or "")
    extracted = {}
    for key in ("added", "updated", "ignored"):
        m = re.search(rf"(\\d+)\\s+{key}", msg, flags=re.IGNORECASE)
        if m:
            extracted[key] = int(m.group(1))

    created_at = datetime.utcnow()
    failed_rows = details.get("failed_rows") or []
    row = {
        "timestamp_utc": created_at.isoformat(),
        "entity": entity,
        "import_kind": import_kind,
        "source_file": source_filename or "",
        "status": "SUCCESS" if success else "FAILED",
        "message": msg,
        "added": extracted.get("added"),
        "updated": extracted.get("updated"),
        "ignored": extracted.get("ignored"),
        "failed_rows_count": len(failed_rows),
    }
    summary_df = pd.DataFrame([row])
    failed_df = pd.DataFrame(failed_rows)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        if not failed_df.empty:
            failed_df.to_excel(writer, sheet_name="Failed Rows", index=False)

    with _latest_import_reports_lock:
        _latest_import_reports[entity] = str(out_path)

    _register_report_entry({
        "id": report_id,
        "created_at": created_at.isoformat(),
        "entity": entity,
        "import_kind": import_kind,
        "source_file": source_filename or "",
        "status": "SUCCESS" if success else "FAILED",
        "message": msg,
        "failed_rows_count": int(len(failed_rows)),
        "report_path": str(out_path),
    })
    return report_id, str(out_path)

# ====================================================================
# Fonctions Utilitaires
# ====================================================================

def parse_float_or_nan(value):
    """
    Convertit une valeur en float. Si échec ou vide/NaN, retourne np.nan.
    """
    if value is None or pd.isna(value):
        return np.nan
    
    try:
        s_val = str(value).strip()
    except Exception:
        s_val = ''
        
    if not s_val or s_val.lower() in ['nan', 'none', '']:
        return np.nan
        
    try:
        f_val = float(s_val)
        return f_val if not np.isnan(f_val) else np.nan 
    except (ValueError, TypeError):
        return np.nan

def parse_int_or_none(value):
    """ Convertit une valeur en int ou retourne None si échec ou NaN. """
    if pd.isna(value) or value is None:
        return None
    try:
        # Tente d'abord de convertir en float (pour gérer les décimales accidentelles) puis en int
        return int(float(value)) 
    except (ValueError, TypeError):
        return None
        
def parse_float_or_none(value):
    """ Convertit une valeur en float ou retourne None si échec ou NaN. """
    nan_val = parse_float_or_nan(value)
    return nan_val if pd.notna(nan_val) else None


def _fetch_ground_altitude(latitude, longitude):
    # Best-effort elevation lookup. Never raises to caller.
    try:
        query = urlencode({"locations": f"{latitude},{longitude}"})
        url = f"https://api.open-elevation.com/api/v1/lookup?{query}"
        with urlopen(url, timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        results = payload.get("results") or []
        if not results:
            return None
        val = results[0].get("elevation")
        return float(val) if val is not None else None
    except Exception:
        return None

# ====================================================================
# FONCTION DE RESOLUTION DU SECTEUR (CORRIGÉE)
# ====================================================================

def resolve_sector_id_for_cell(cellname, technology, frequency):
    """
    Résout le sector_id en utilisant le Mapping pour une Cell.
    
    Extraction du code_site: Le code commence par 'C', 'A', ou 'O' et est limité par '_'.
    (e.g., '4C28X100_1' -> code_site='C28X100', cell_code='1')

    Retourne: (sector_id, sector_code) ou (None, None)
    """
    # 1. Extraction du Cell Code Suffix (cell_code) et du Code Site
    try:
        # rsplit('_', 1) sépare la partie Site/Secteur du suffixe Cell
        parts = cellname.rsplit('_', 1)
        if len(parts) == 2:
            raw_site_part = parts[0].strip()  # e.g., '4C28X100'
            cell_code_suffix = parts[1].strip() # CELL_CODE pour la table Mapping (e.g., '1')
        else:
            # Si le format standard SITE_CODE_CELL_CODE n'est pas respecté
            return None, None
            
        # Extraction du CODE_SITE réel: recherche de la première lettre C, A, ou O
        code_site = raw_site_part
        for i, char in enumerate(raw_site_part):
            if char.upper() in ['C', 'A', 'O']:
                code_site = raw_site_part[i:] # e.g., 'C28X100'
                break
                
    except Exception:
        return None, None
        
    if not cell_code_suffix or not code_site:
        return None, None

    # Normalisation des valeurs pour la recherche (Mapping.band correspond à Cell.frequency)
    tech_search = technology.strip() if technology else None
    freq_search = frequency.strip() if frequency else None
    
    # Nous avons besoin de la technologie et de la fréquence (band) pour trouver le mapping
    if not tech_search or not freq_search:
        return None, None

    sector_code_value = None
    sector_id_value = None

    try:
        # 2. Recherche dans la table Mapping (Cell Code + Tech + Band/Freq)
        with db.session.no_autoflush:
            mapping_obj = db.session.execute(
                select(Mapping).filter_by(
                    cell_code=cell_code_suffix, # '1' dans l'exemple
                    technology=tech_search,
                    band=freq_search 
                )
            ).scalar_one_or_none()

        if mapping_obj:
            sector_code_value = code_site+"_"+mapping_obj.sector_code
            logger.debug("sector_code_value: %s", sector_code_value)
            # 3. Recherche du Sector ID à partir du Sector Code
            if sector_code_value:
                sector_obj = db.session.execute(
                    select(Sector).filter_by(code_sector=sector_code_value)
                ).scalar_one_or_none()

                if sector_obj:
                    sector_id_value = sector_obj.id
    except Exception as e:
        # print(f"Erreur lors de la résolution du secteur pour {cellname}: {e}") # Commenté pour éviter log excessif
        return None, None
    print (sector_code_value,sector_id_value)   
    return sector_id_value, sector_code_value

# ====================================================================
# FONCTIONS D'IMPORTATION 
# ====================================================================

def import_suppliers(df):
    SUPPLIER_NAME_COL = 'SUPPLIER_NAME'
    added = 0
    ignored = 0
    row_errors = 0 
    df_clean = df.dropna(subset=[SUPPLIER_NAME_COL]).drop_duplicates(subset=[SUPPLIER_NAME_COL])
    try:
        for idx, row in df_clean.iterrows():
            supplier_name = str(row[SUPPLIER_NAME_COL]).strip()
            if not supplier_name:
                row_errors += 1
                continue
            existing_supplier = db.session.execute(
                select(Supplier).filter_by(name=supplier_name)
            ).scalar_one_or_none() 
            if existing_supplier:
                ignored += 1
            else:
                new_supplier = Supplier(name=supplier_name) 
                db.session.add(new_supplier)
                added += 1
        db.session.commit()
        ignored_total = ignored + row_errors + (len(df) - len(df_clean)) 
        msg = (f"Importation des fournisseurs réussie : {added} ajoutés, "
               f"{ignored} ignorés (déjà existants). "
               f"Total lignes ignorées : {ignored_total}."
        )
        return (True, msg)
    except Exception as e:
        db.session.rollback()
        logger.exception("Erreur DB complète (Supplier Import)")
        error_msg = f"Erreur fatale lors de l'importation des fournisseurs : {type(e).__name__}. Détails: {str(e)}"
        return (False, error_msg)

def import_regions(df):
    REGION_NAME_COL = 'name'
    added = 0
    ignored = 0
    df_clean = df.dropna(subset=[REGION_NAME_COL]).drop_duplicates(subset=[REGION_NAME_COL])
    try:
        for idx, row in df_clean.iterrows():
            region_name = str(row[REGION_NAME_COL]).strip()
            if not region_name: continue
            existing_region = db.session.execute(select(Region).filter_by(name=region_name)).scalars().first() 
            if existing_region:
                ignored += 1
                continue
            new_region = Region(name=region_name)
            db.session.add(new_region)
            added += 1
        db.session.commit()
        msg = f"Importation des régions réussie : {added} ajoutées, {ignored} ignorées sur {len(df_clean)} lignes uniques traitées."
        return (True, msg)
    except Exception as e:
        db.session.rollback()
        logger.exception("Erreur DB complète (Region Import)")
        error_msg = f"Erreur fatale lors de l'importation des régions : {type(e).__name__}. Détails: {str(e)}"
        return (False, error_msg)

def import_wilayas(df):
    WILAYA_NAME_COL = 'wilaya_name' 
    REGION_NAME_COL = 'region_name' 
    WILAYA_CODE_COL = 'wilaya_code' # <--- Ajoute cette colonne dans ton Excel
    
    added = 0
    ignored = 0
    failed_dependencies = 0 
    
    # Nettoyage
    df_clean = df.dropna(subset=[WILAYA_NAME_COL, REGION_NAME_COL, WILAYA_CODE_COL]).drop_duplicates(subset=[WILAYA_NAME_COL])
    
    try:
        for idx, row in df_clean.iterrows():
            wilaya_name = str(row[WILAYA_NAME_COL]).strip()
            region_name = str(row[REGION_NAME_COL]).strip()
            
            # Conversion du code en entier (ex: "28" -> 28)
            try:
                wilaya_id = int(row[WILAYA_CODE_COL])
            except:
                continue # Ignore si le code n'est pas un nombre

            if not wilaya_name or not region_name: continue

            # Vérifier la région
            region_obj = db.session.execute(select(Region).filter_by(name=region_name)).scalars().first() 
            if region_obj is None:
                failed_dependencies += 1
                continue 

            # Vérifier si la Wilaya existe déjà par ID (le code) ou par Nom
            existing_wilaya = db.session.execute(
                select(Wilaya).filter((Wilaya.id == wilaya_id) | (Wilaya.name == wilaya_name))
            ).scalars().first()

            if existing_wilaya:
                existing_wilaya.region_id = region_obj.id
                ignored += 1
                continue

            # CRÉATION : On force l'ID avec le code wilaya
            new_wilaya = Wilaya(
                id=wilaya_id, # <--- C'est ici qu'on force l'ID
                name=wilaya_name, 
                region_id=region_obj.id
            )
            db.session.add(new_wilaya)
            added += 1
            
        db.session.commit()
        msg = f"Importation réussie : {added} ajoutées avec codes officiels."
        return (True, msg)
        
    except Exception as e:
        db.session.rollback()
        return (False, f"Erreur: {str(e)}")

def import_communes(df):
    COMMUNE_ID_COL = 'commune_id'   
    COMMUNE_NAME_COL = 'commune_name'
    WILAYA_NAME_COL = 'wilaya_name'
    added = 0
    updated = 0
    failed_dependencies = 0 
    row_errors = 0 
    required_cols = [COMMUNE_ID_COL, COMMUNE_NAME_COL, WILAYA_NAME_COL]
    df_clean = df.dropna(subset=required_cols).drop_duplicates(subset=[COMMUNE_ID_COL])
    try:
        for idx, row in df_clean.iterrows():
            commune_name = str(row[COMMUNE_NAME_COL]).strip()
            wilaya_name = str(row[WILAYA_NAME_COL]).strip()
            try:
                commune_id = int(row[COMMUNE_ID_COL])
            except (ValueError, TypeError):
                row_errors += 1
                continue
            if not commune_name or not wilaya_name:
                row_errors += 1
                continue
            wilaya_obj = db.session.execute(select(Wilaya).filter_by(name=wilaya_name)).scalars().first() 
            if wilaya_obj is None:
                failed_dependencies += 1
                continue 
            existing_commune = db.session.execute(select(Commune).filter_by(id=commune_id)).scalar_one_or_none() 
            if existing_commune:
                commune_to_save = existing_commune
                updated += 1
            else:
                commune_to_save = Commune(id=commune_id) 
                db.session.add(commune_to_save)
                added += 1
            commune_to_save.name = commune_name
            commune_to_save.wilaya_id = wilaya_obj.id
        db.session.commit()
        msg = (f"Importation des communes réussie : {added} ajoutées, "f"{updated} mises à jour (par ID). "f"{failed_dependencies} ignorées (Wilaya manquante). "f"{row_errors} lignes ignorées (données ou ID invalide).")
        return (True, msg)
    except Exception as e:
        db.session.rollback()
        logger.exception("Erreur DB complète (Commune Import)")
        error_msg = f"Erreur fatale lors de l'importation des communes : {type(e).__name__}. Détails: {str(e)}"
        return (False, error_msg)

def import_antennas(df):
    SUPPLIER_COL = 'Supplier'      
    MODEL_COL = 'Model'            
    FREQUENCY_COL = 'Frequency'    
    HBEAMWIDTH_COL = 'HBEAMWIDTH'
    VBEAMWIDTH_COL = 'VBEAMWIDTH'
    NAME_COL = 'Name'
    PORT_COL = 'Port'
    TYPE_COL = 'Type'
    GAIN_COL = 'GAIN'
    
    added = 0
    updated = 0
    
    required_cols = [MODEL_COL, SUPPLIER_COL, FREQUENCY_COL, HBEAMWIDTH_COL, VBEAMWIDTH_COL]
    FLOAT_COLS = [FREQUENCY_COL, HBEAMWIDTH_COL, VBEAMWIDTH_COL, PORT_COL, GAIN_COL]
    
    try:
        for col in FLOAT_COLS:
            if col in df.columns:
                 df[col] = df[col].apply(lambda x: parse_float_or_nan(x))
                 df[col] = pd.to_numeric(df[col], errors='coerce')

        df_clean = df.dropna(subset=required_cols).drop_duplicates(subset=[MODEL_COL, FREQUENCY_COL])
        df_clean = df_clean.reset_index(drop=True)
        ignored = len(df) - len(df_clean)

    except Exception as e:
        error_msg = f"Erreur lors du pré-traitement des données d'antennes (colonne manquante ou type invalide) : {type(e).__name__}. Détails: {str(e)}";
        logger.exception("Erreur de pré-traitement (Antenna Import)")
        return (False, error_msg)

    try:
        for idx, row in df_clean.iterrows():
            model_name = str(row[MODEL_COL]).strip()
            supplier_name = str(row[SUPPLIER_COL]).strip()
            
            frequency_value = row[FREQUENCY_COL]
            h_beamwidth_value = row[HBEAMWIDTH_COL]
            v_beamwidth_value = row[VBEAMWIDTH_COL]
            
            with db.session.no_autoflush:
                existing_antenna = db.session.execute(
                    select(Antenna).filter_by(model=model_name, frequency=frequency_value)
                ).scalar_one_or_none() 
            
            if existing_antenna:
                antenna_to_save = existing_antenna
                updated += 1
            else:
                antenna_to_save = Antenna(
                    model=model_name, 
                    frequency=float(frequency_value),
                    hbeamwidth=float(h_beamwidth_value),
                    vbeamwidth=float(v_beamwidth_value)
                )
                db.session.add(antenna_to_save)
                added += 1
            
            antenna_to_save.supplier = supplier_name 
            antenna_to_save.name = row.get(NAME_COL)
            antenna_to_save.type = row.get(TYPE_COL)
            
            port_value = row.get(PORT_COL)
            gain_value = row.get(GAIN_COL)
            
            antenna_to_save.hbeamwidth = float(h_beamwidth_value)
            antenna_to_save.vbeamwidth = float(v_beamwidth_value)
            
            antenna_to_save.port = float(port_value) if pd.notna(port_value) else None 
            antenna_to_save.gain = float(gain_value) if pd.notna(gain_value) else None
                
        db.session.commit()
        
        msg = (f"Importation des modèles d'antennes réussie : {added} ajoutés, "
               f"{updated} mis à jour (par Modèle + Fréquence). "
               f"{ignored} lignes ignorées (données manquantes/invalides)."
        )
        return (True, msg)
        
    except Exception as e:
        db.session.rollback()
        if "IntegrityError" in str(e):
            error_msg = f"Erreur de contrainte de base de données (NOT NULL ou clé unique) : {str(e)}"
        else:
            error_msg = f"Erreur fatale lors de l'importation des antennes : {type(e).__name__}. Détails: {str(e)}"
            
        logger.exception("Erreur DB complète (Antenna Import)")
        return (False, error_msg)

def import_sites(df):
    # Colonnes telles que spécifiées par l'utilisateur
    SITE_CODE_COL = 'site_code'    
    SITE_NAME_COL = 'site_name'    
    COMMUNE_ID_COL = 'commune_id'         
    SUPPLIER_NAME_COL = 'supplier_name'   
    LATITUDE_COL = 'latitude'
    ALT_LATITUDE_COL = 'laltitude'
    LONGITUDE_COL = 'longitude'
    
    ADDRESS_COL = 'addresses'             
    ALTITUDE_COL = 'altitude'
    SUPPORT_NATURE_COL = 'support_nature'
    SUPPORT_TYPE_COL = 'support_type'
    SUPPORT_HEIGHT_COL = 'support_hight'  
    COMMENTS_COL = 'Comments'             
    
    added = 0
    updated = 0
    failed_dependencies = 0 
    row_errors = 0 
    failed_rows = []
    altitude_auto_filled = 0
    altitude_lookup_failed = 0
    altitude_cache = {}
    
    required_cols = [SITE_CODE_COL, SITE_NAME_COL, COMMUNE_ID_COL, SUPPLIER_NAME_COL, LATITUDE_COL, LONGITUDE_COL]
    FLOAT_COLS = [LATITUDE_COL, LONGITUDE_COL, ALTITUDE_COL, SUPPORT_HEIGHT_COL]
    
    try:
        # Compatibilite avec anciens fichiers qui utilisaient "laltitude"
        if LATITUDE_COL not in df.columns and ALT_LATITUDE_COL in df.columns:
            df[LATITUDE_COL] = df[ALT_LATITUDE_COL]

        df = df.copy()
        df["__row_number"] = df.index + 2

        # --- PRÉ-TRAITEMENT DES DONNÉES ---\n
        for col in FLOAT_COLS:
            if col in df.columns:
                 df[col] = df[col].apply(lambda x: parse_float_or_nan(x))
                 df[col] = pd.to_numeric(df[col], errors='coerce')

        required_ok = df[required_cols].notna().all(axis=1)
        for _, bad_row in df[~required_ok].iterrows():
            failed_rows.append({
                "row_number": int(bad_row["__row_number"]),
                "entity": "site",
                "item_code": str(bad_row.get(SITE_CODE_COL) or "").strip(),
                "cause": "Missing required columns.",
            })

        duplicate_mask = df.duplicated(subset=[SITE_CODE_COL], keep="first") & required_ok
        for _, dup_row in df[duplicate_mask].iterrows():
            failed_rows.append({
                "row_number": int(dup_row["__row_number"]),
                "entity": "site",
                "item_code": str(dup_row.get(SITE_CODE_COL) or "").strip(),
                "cause": "Duplicate site_code in file.",
            })

        # Nettoyage des lignes et gestion des doublons sur la clé unique SITE_CODE
        df_clean = df[required_ok & ~duplicate_mask].copy()
        df_clean = df_clean.reset_index(drop=True)

    except Exception as e:
        error_msg = f"Erreur lors du pré-traitement des données de sites : {type(e).__name__}. Détails: {str(e)}"
        logger.exception("Erreur de pré-traitement (Site Import)")
        return (False, error_msg, {"failed_rows": []})

    # --- TRAITEMENT DB ---
    try:
        for idx, row in df_clean.iterrows():
            row_number = int(row.get("__row_number", idx + 2))
            site_code = str(row[SITE_CODE_COL]).strip()
            site_name = str(row[SITE_NAME_COL]).strip()
            
            commune_id_value = parse_int_or_none(row.get(COMMUNE_ID_COL)) 
            supplier_name = str(row[SUPPLIER_NAME_COL]).strip()
            
            latitude_value = row[LATITUDE_COL]
            longitude_value = row[LONGITUDE_COL]
            
            # Récupération des valeurs optionnelles
            altitude_value = row.get(ALTITUDE_COL)
            support_nature_value = str(row.get(SUPPORT_NATURE_COL)).strip() if pd.notna(row.get(SUPPORT_NATURE_COL)) else None
            support_type_value = str(row.get(SUPPORT_TYPE_COL)).strip() if pd.notna(row.get(SUPPORT_TYPE_COL)) else None
            support_height_value = row.get(SUPPORT_HEIGHT_COL)
            comments_value = str(row.get(COMMENTS_COL)) if pd.notna(row.get(COMMENTS_COL)) else None
            address_value = str(row.get(ADDRESS_COL)) if pd.notna(row.get(ADDRESS_COL)) else None
            
            if not site_code or not site_name or commune_id_value is None or not supplier_name:
                row_errors += 1
                failed_rows.append({
                    "row_number": row_number,
                    "entity": "site",
                    "item_code": site_code or "",
                    "cause": "Missing required fields (site_code/site_name/commune_id/supplier_name).",
                })
                continue
                
            # 1. Vérification de la dépendance Commune par ID
            commune_obj = db.session.execute(select(Commune).filter_by(id=commune_id_value)).scalar_one_or_none() 
            if commune_obj is None:
                failed_dependencies += 1
                failed_rows.append({
                    "row_number": row_number,
                    "entity": "site",
                    "item_code": site_code,
                    "cause": f"Dependency missing: commune_id={commune_id_value} not found.",
                })
                continue 
                
            # 2. Vérification de la dépendance Supplier par NAME
            supplier_obj = db.session.execute(select(Supplier).filter_by(name=supplier_name)).scalar_one_or_none()
            if supplier_obj is None:
                failed_dependencies += 1
                failed_rows.append({
                    "row_number": row_number,
                    "entity": "site",
                    "item_code": site_code,
                    "cause": f"Dependency missing: supplier_name='{supplier_name}' not found.",
                })
                continue
            
            supplier_id_value = supplier_obj.id

            # 3. Vérification d'Existence (UPSERT)
            existing_site = db.session.execute(
                select(Site).filter_by(code_site=site_code)
            ).scalar_one_or_none() 
            
            if existing_site:
                site_to_save = existing_site
                updated += 1
            else:
                site_to_save = Site(
                    code_site=site_code,
                    latitude=float(latitude_value),
                    longitude=float(longitude_value)
                ) 
                db.session.add(site_to_save)
                added += 1
            
            # 4. Affectation des attributs
            site_to_save.name = site_name
            site_to_save.commune_id = commune_id_value
            site_to_save.latitude = float(latitude_value)
            site_to_save.longitude = float(longitude_value)

            site_to_save.address = address_value
            resolved_altitude = float(altitude_value) if pd.notna(altitude_value) else None
            if resolved_altitude is None:
                # Auto-compute altitude from lat/lon in best-effort mode (never blocks import on failure).
                cache_key = (round(float(latitude_value), 6), round(float(longitude_value), 6))
                if cache_key in altitude_cache:
                    resolved_altitude = altitude_cache[cache_key]
                else:
                    computed = _fetch_ground_altitude(cache_key[0], cache_key[1])
                    altitude_cache[cache_key] = computed
                    resolved_altitude = computed
                if resolved_altitude is not None:
                    altitude_auto_filled += 1
                else:
                    altitude_lookup_failed += 1

            site_to_save.altitude = resolved_altitude
            site_to_save.support_nature = support_nature_value
            site_to_save.support_type = support_type_value
            site_to_save.support_height = float(support_height_value) if pd.notna(support_height_value) else None
            site_to_save.comments = comments_value
            site_to_save.supplier_id = supplier_id_value
                
        db.session.commit()
        
        # --- CRÉATION DU MESSAGE DE SUCCÈS ---
        ignored_total = len(failed_rows)
        
        msg = (f"Importation des sites réussie : {added} ajoutés, "
               f"{updated} mis à jour (par site_code). "
               f"Total ignoré : {ignored_total} ({failed_dependencies} dépendances manquantes). "
               f"Altitude auto-remplie: {altitude_auto_filled}, échec lookup: {altitude_lookup_failed}."
        )
        return (True, msg, {"failed_rows": failed_rows})
        
    except Exception as e:
        db.session.rollback()
        logger.exception("Erreur DB complète (Site Import)")
        error_msg = f"Erreur fatale lors de l'importation des sites : {type(e).__name__}. Détails: {str(e)}"
        return (False, error_msg, {"failed_rows": failed_rows})

def import_sectors(df):
    # Canonical columns expected after normalization.
    SECTOR_CODE_COL = 'code_sector'
    SITE_CODE_COL = 'code_site'
    AZIMUTH_COL = 'azimuth'
    HBA_COL = 'hba'
    COMMENTS_COL = 'comments'
    COVERAGE_GOAL_COL = 'coverage_goal'
    
    added = 0
    updated = 0
    failed_dependencies = 0 
    row_errors = 0 
    failed_rows = []
    
    # Colonnes requises (non nulles dans le modèle ou pour les dépendances)
    required_cols = [SECTOR_CODE_COL, SITE_CODE_COL, AZIMUTH_COL, HBA_COL]
    
    try:
        df = df.copy()
        # Normalize sector headers and accept legacy aliases.
        alias = {
            "sectors": "code_sector",
            "sector": "code_sector",
            "sector_code": "code_sector",
            "code_sector": "code_sector",
            "site": "code_site",
            "site_code": "code_site",
            "code_site": "code_site",
            "azimuth": "azimuth",
            "hba": "hba",
            "coverage_goal": "coverage_goal",
            "coveragegoal": "coverage_goal",
            "comments": "comments",
            "comment": "comments",
        }
        renamed = {}
        for col in df.columns:
            raw = str(col or "").strip()
            key = raw.lower().replace(" ", "_").replace("-", "_")
            while "__" in key:
                key = key.replace("__", "_")
            renamed[col] = alias.get(key, key)
        df = df.rename(columns=renamed)

        df["__row_number"] = df.index + 2
        missing_required = [c for c in required_cols if c not in df.columns]
        if missing_required:
            return (
                False,
                "Colonnes obligatoires manquantes pour sectors: "
                + ", ".join(missing_required),
                {"failed_rows": []},
            )

        required_ok = df[required_cols].notna().all(axis=1)
        for _, bad_row in df[~required_ok].iterrows():
            failed_rows.append({
                "row_number": int(bad_row["__row_number"]),
                "entity": "sector",
                "item_code": str(bad_row.get(SECTOR_CODE_COL) or "").strip(),
                "cause": "Missing required columns.",
            })

        duplicate_mask = df.duplicated(subset=[SECTOR_CODE_COL], keep="first") & required_ok
        for _, dup_row in df[duplicate_mask].iterrows():
            failed_rows.append({
                "row_number": int(dup_row["__row_number"]),
                "entity": "sector",
                "item_code": str(dup_row.get(SECTOR_CODE_COL) or "").strip(),
                "cause": "Duplicate sector code in file.",
            })

        # Nettoyage des lignes et gestion des doublons sur la clé unique SECTOR_CODE
        df_clean = df[required_ok & ~duplicate_mask].copy()
        df_clean = df_clean.reset_index(drop=True)
        ignored_preprocessing = len(df) - len(df_clean)

    except Exception as e:
        error_msg = f"Erreur lors du pré-traitement des données de secteurs : {type(e).__name__}. Détails: {str(e)}"
        logger.exception("Erreur de pré-traitement (Sector Import)")
        return (False, error_msg, {"failed_rows": []})

    try:
        for idx, row in df_clean.iterrows():
            row_number = int(row.get("__row_number", idx + 2))
            sector_code = str(row[SECTOR_CODE_COL]).strip()
            site_code = str(row[SITE_CODE_COL]).strip()
            
            # Les champs Azimuth et HBA sont définis comme INTEGER et NOT NULL dans le modèle
            azimuth_value = parse_int_or_none(row.get(AZIMUTH_COL))
            hba_value = parse_int_or_none(row.get(HBA_COL))
            
            # Champs optionnels
            comments_value = str(row.get(COMMENTS_COL)) if pd.notna(row.get(COMMENTS_COL)) else None
            coverage_goal_value = str(row.get(COVERAGE_GOAL_COL)).strip() if pd.notna(row.get(COVERAGE_GOAL_COL)) else None
            
            # Validation des colonnes non nulles
            if not sector_code or not site_code or azimuth_value is None or hba_value is None:
                row_errors += 1
                failed_rows.append({
                    "row_number": row_number,
                    "entity": "sector",
                    "item_code": sector_code or "",
                    "cause": "Missing/invalid required fields (sector/site/azimuth/hba).",
                })
                continue
            
            # 1. Vérification de la dépendance Site par CODE (Site.code_site)
            site_obj = db.session.execute(select(Site).filter_by(code_site=site_code)).scalar_one_or_none() 
            if site_obj is None:
                logger.warning("Secteur ignoré: code=%s site=%s", sector_code, site_code)
                failed_dependencies += 1
                failed_rows.append({
                    "row_number": row_number,
                    "entity": "sector",
                    "item_code": sector_code,
                    "cause": f"Dependency missing: site='{site_code}' not found.",
                })
                continue 
            
            site_id = site_obj.id 
            
            # 2. Vérification d'Existence (UPSERT)
            # 'sectors' du fichier est utilisé comme 'code_sector' dans le modèle pour l'UPSERT.
            existing_sector = db.session.execute(
                select(Sector).filter_by(code_sector=sector_code) 
            ).scalar_one_or_none() 
            
            if existing_sector:
                sector_to_save = existing_sector
                updated += 1
            else:
                sector_to_save = Sector(
                    code_sector=sector_code, 
                    azimuth=azimuth_value,
                    hba=hba_value,
                    site_id=site_id
                ) 
                db.session.add(sector_to_save)
                added += 1
            
            # 3. Affectation des attributs
            sector_to_save.azimuth = azimuth_value
            sector_to_save.hba = hba_value
            sector_to_save.site_id = site_id

            sector_to_save.coverage_goal = coverage_goal_value
            
            # Gestion du champ 'comments' s'il existe dans le modèle Sector
            if hasattr(sector_to_save, 'comments'):
                sector_to_save.comments = comments_value
                
        db.session.commit()
        
        # --- CRÉATION DU MESSAGE DE SUCCÈS ---
        ignored_total = len(failed_rows)
        
        msg = (f"Importation des secteurs réussie : {added} ajoutés, "
               f"{updated} mis à jour (par code de secteur). "
               f"Total ignoré : {ignored_total} ({failed_dependencies} dépendances Site manquantes)."
        )
        return (True, msg, {"failed_rows": failed_rows})
        
    except Exception as e:
        db.session.rollback()
        logger.exception("Erreur DB complète (Sector Import)")
        error_msg = f"Erreur fatale lors de l'importation des secteurs : {type(e).__name__}. Détails: {str(e)}"
        return (False, error_msg, {"failed_rows": failed_rows})

def import_mapping(df):
    MAP_ID_COL = 'MAP_ID'
    CELL_CODE_COL = 'CELL_CODE'
    ANTENNA_TECH_COL = 'ANTENNA_TECH'
    BAND_COL = 'BAND'
    SECTOR_CODE_COL = 'SECTOR_CODE'
    TECHNOLOGY_COL = 'TECHNOLOGY'
    
    added = 0
    updated = 0
    row_errors = 0 
    
    required_cols = [MAP_ID_COL, CELL_CODE_COL, ANTENNA_TECH_COL, BAND_COL, SECTOR_CODE_COL, TECHNOLOGY_COL]

    try:
        # Pré-nettoyage : supprime les lignes avec des NaN dans les colonnes requises et les doublons sur la clé unique
        df_clean = df.dropna(subset=required_cols).drop_duplicates(subset=[MAP_ID_COL])
        df_clean = df_clean.reset_index(drop=True)
        ignored_preprocessing = len(df) - len(df_clean)

    except Exception as e:
        error_msg = f"Erreur lors du pré-traitement des données de mapping : {type(e).__name__}. Détails: {str(e)}"
        logger.exception("Erreur de pré-traitement (Mapping Import)")
        return (False, error_msg)

    try:
        for idx, row in df_clean.iterrows():
            map_id = str(row[MAP_ID_COL]).strip()
            cell_code = str(row[CELL_CODE_COL]).strip()
            antenna_tech = str(row[ANTENNA_TECH_COL]).strip()
            band = str(row[BAND_COL]).strip()
            sector_code = str(row[SECTOR_CODE_COL]).strip()
            technology = str(row[TECHNOLOGY_COL]).strip()
            
            # Vérification finale des données non vides
            if not all([map_id, cell_code, antenna_tech, band, sector_code, technology]):
                row_errors += 1
                continue
                
            # UPSERT basé sur map_id (clé unique)
            existing_mapping = db.session.execute(
                select(Mapping).filter_by(map_id=map_id) 
            ).scalar_one_or_none() 
            
            if existing_mapping:
                mapping_to_save = existing_mapping
                updated += 1
            else:
                mapping_to_save = Mapping(map_id=map_id)
                db.session.add(mapping_to_save)
                added += 1
            
            # Affectation des attributs
            mapping_to_save.cell_code = cell_code
            mapping_to_save.antenna_tech = antenna_tech
            mapping_to_save.band = band
            mapping_to_save.sector_code = sector_code
            mapping_to_save.technology = technology
                
        db.session.commit()
        
        ignored_total = ignored_preprocessing + row_errors
        
        msg = (f"Importation des mappings réussie : {added} ajoutés, "
               f"{updated} mis à jour (par MAP_ID). "
               f"Total lignes ignorées : {ignored_total}."
        )
        return (True, msg)
        
    except Exception as e:
        db.session.rollback()
        logger.exception("Erreur DB complète (Mapping Import)")
        error_msg = f"Erreur fatale lors de l'importation des mappings : {type(e).__name__}. Détails: {str(e)}"
        return (False, error_msg)

def _normalize_cell_columns(df):
    # Normalize many header variants to a stable import schema.
    alias_map = {
        "cell": "CELLNAME",
        "cell_name": "CELLNAME",
        "cellname": "CELLNAME",
        "tech": "TECHNOLOGY",
        "technology": "TECHNOLOGY",
        "band": "FREQUENCY",
        "frequency": "FREQUENCY",
        "frequencyband": "FREQUENCY",
        "antenna_tech": "ANTENNA_TECH",
        "sup": "ANTENNA_TECH",
        "mechanicaltilt": "MECHANICALTILT",
        "electricaltilt": "ELECTRICALTILT",
        "antenna": "ANTENNA",
        "bsc": "BSC",
        "lac": "LAC",
        "rac": "RAC",
        "bcch": "BCCH",
        "bsic": "BSIC",
        "rnc": "RNC",
        "psc": "PSC",
        "dlarfcn": "DLARFCN",
        "enodeb": "ENODEB",
        "tac": "TAC",
        "rsi": "RSI",
        "pci": "PCI",
        "earfcn": "EARFCN",
        "cid": "CI",
        "ci": "CI",
        "eutrancellid": "CI",
        "e_utran_cellid": "CI",
        "e_utran_cell_id": "CI",
        "e_utran_cellid": "CI",
        "gnodeb": "GNODEB",
        "arfcn": "ARFCN",
    }

    renamed = {}
    for col in df.columns:
        raw = str(col or "").strip()
        key = "".join(ch.lower() if ch.isalnum() else "_" for ch in raw).strip("_")
        while "__" in key:
            key = key.replace("__", "_")
        renamed[col] = alias_map.get(key, raw.upper())
    return df.rename(columns=renamed)


def _infer_tech_from_sheet_name(sheet_name):
    # Infer technology from sheet names like "2G", "3G", "4G", "5G".
    txt = str(sheet_name or "").strip().upper()
    for tech in ("2G", "3G", "4G", "5G"):
        if tech in txt:
            return tech
    return None


def import_cells(df, progress_cb=None):
    CELLNAME_COL = "CELLNAME"
    TECHNOLOGY_COL = "TECHNOLOGY"
    FREQUENCY_COL = "FREQUENCY"
    ANTENNA_TECH_COL = "ANTENNA_TECH"
    TILT_MECH_COL = "MECHANICALTILT"
    TILT_ELEC_COL = "ELECTRICALTILT"
    ANTENNA_MODEL_COL = "ANTENNA"

    added = 0
    updated = 0
    failed_antenna_dependencies = 0
    failed_sector_resolutions = 0
    failed_rows = []
    batch_size = 1000
    pending_in_batch = 0

    def to_int_or_none(value):
        if pd.isna(value) or value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def get_text(row, key):
        if key not in row:
            return None
        val = row.get(key)
        if pd.isna(val):
            return None
        txt = str(val).strip()
        return txt if txt else None

    def has_value(row, key):
        return get_text(row, key) is not None

    def row_ref(row_obj):
        src_row = row_obj.get("__source_row")
        src_sheet = row_obj.get("__source_sheet")
        if pd.notna(src_row):
            try:
                row_no = int(float(src_row))
            except (TypeError, ValueError):
                row_no = int(row_obj.name) + 2
        else:
            row_no = int(row_obj.name) + 2
        return row_no, (str(src_sheet).strip() if pd.notna(src_sheet) else "")

    try:
        # 1) Preprocess the dataframe and validate mandatory key columns.
        df = _normalize_cell_columns(df)
        if TILT_MECH_COL in df.columns:
            df[TILT_MECH_COL] = pd.to_numeric(df[TILT_MECH_COL], errors="coerce")
        if TILT_ELEC_COL in df.columns:
            df[TILT_ELEC_COL] = pd.to_numeric(df[TILT_ELEC_COL], errors="coerce")

        if CELLNAME_COL not in df.columns:
            return (False, "CELLNAME column is required for cell import.", {"failed_rows": []})

        required_ok = df[CELLNAME_COL].notna()
        for _, bad_row in df[~required_ok].iterrows():
            rn, sh = row_ref(bad_row)
            failed_rows.append({
                "row_number": rn,
                "source_sheet": sh,
                "entity": "cell",
                "item_code": "",
                "cause": "Missing required column: CELLNAME.",
            })

        duplicate_mask = df.duplicated(subset=[CELLNAME_COL], keep="first") & required_ok
        for _, dup_row in df[duplicate_mask].iterrows():
            rn, sh = row_ref(dup_row)
            failed_rows.append({
                "row_number": rn,
                "source_sheet": sh,
                "entity": "cell",
                "item_code": str(dup_row.get(CELLNAME_COL) or "").strip(),
                "cause": "Duplicate CELLNAME in file.",
            })

        df_clean = df[required_ok & ~duplicate_mask].copy()
        df_clean = df_clean.reset_index(drop=True)
        ignored_preprocessing = len(df) - len(df_clean)
    except Exception as e:
        return (False, f"Erreur pre-traitement: {str(e)}", {"failed_rows": []})

    try:
        total_rows = int(len(df_clean))
        progress_window_start = 46
        progress_window_end = 94
        progress_every = 250
        started_ts = time.monotonic()

        def emit_progress(processed_rows, force=False, message=None):
            if not progress_cb:
                return
            if not force and processed_rows > 0 and (processed_rows % progress_every) != 0:
                return
            if total_rows <= 0:
                percent = 100
                eta_seconds = 0
            else:
                percent = int((processed_rows / total_rows) * 100)
                elapsed = max(time.monotonic() - started_ts, 1e-6)
                speed = processed_rows / elapsed if processed_rows > 0 else 0.0
                remaining = max(total_rows - processed_rows, 0)
                eta_seconds = int(remaining / speed) if speed > 0 else None

            progress = progress_window_start
            if total_rows > 0:
                progress = progress_window_start + int(
                    ((progress_window_end - progress_window_start) * min(processed_rows, total_rows)) / total_rows
                )
            progress = max(progress_window_start, min(progress_window_end, progress))
            progress_cb(
                progress=progress,
                message=message or f"Processing rows {processed_rows}/{total_rows} ({percent}%)...",
                processed_rows=processed_rows,
                total_rows=total_rows,
                eta_seconds=eta_seconds,
            )

        emit_progress(0, force=True, message="Starting row processing...")

        # 2) Upsert cells and populate technology-specific profile tables.
        for processed_rows, (_, row_data) in enumerate(df_clean.iterrows(), start=1):
            row_number, source_sheet = row_ref(row_data)
            cellname = get_text(row_data, CELLNAME_COL)
            if not cellname:
                emit_progress(processed_rows)
                continue

            try:
                with db.session.begin_nested():
                    existing_cell = Cell.query.filter_by(cellname=cellname).first()
                    row_is_existing = existing_cell is not None
                    if existing_cell:
                        cell = existing_cell
                    else:
                        cell = Cell(cellname=cellname)
                        db.session.add(cell)

                    incoming_tech = get_text(row_data, TECHNOLOGY_COL)
                    tech_norm = (incoming_tech or cell.technology or "").strip().upper()
                    if not tech_norm:
                        failed_rows.append({
                            "row_number": row_number,
                            "source_sheet": source_sheet,
                            "entity": "cell",
                            "item_code": cellname,
                            "cause": "Technology missing.",
                        })
                        continue

                    previous_tech = (cell.technology or "").strip().upper()
                    tech_changed = bool(previous_tech and previous_tech != tech_norm)
                    cell.technology = tech_norm

                    freq = get_text(row_data, FREQUENCY_COL)
                    if freq is not None:
                        cell.frequency = freq

                    antenna_tech = get_text(row_data, ANTENNA_TECH_COL)
                    if antenna_tech is not None:
                        cell.antenna_tech = antenna_tech

                    if TILT_MECH_COL in row_data and pd.notna(row_data.get(TILT_MECH_COL)):
                        cell.tilt_mechanical = row_data.get(TILT_MECH_COL)
                    if TILT_ELEC_COL in row_data and pd.notna(row_data.get(TILT_ELEC_COL)):
                        cell.tilt_electrical = row_data.get(TILT_ELEC_COL)

                    ant_model = get_text(row_data, ANTENNA_MODEL_COL)
                    if ant_model:
                        ant_obj = db.session.query(Antenna).filter_by(model=ant_model).first()
                        if ant_obj:
                            cell.antenna_id = ant_obj.id
                        else:
                            failed_antenna_dependencies += 1
                            failed_rows.append({
                                "row_number": row_number,
                                "source_sheet": source_sheet,
                                "entity": "cell",
                                "item_code": cellname,
                                "cause": f"Dependency missing: antenna='{ant_model}' not found.",
                            })

                    if cell.frequency:
                        # Resolve Sector from mapping rules (cell suffix + tech + band).
                        sector_id_value, _ = resolve_sector_id_for_cell(cellname, tech_norm, str(cell.frequency))
                        if sector_id_value is not None:
                            cell.sector_id = sector_id_value
                        else:
                            failed_sector_resolutions += 1
                            failed_rows.append({
                                "row_number": row_number,
                                "source_sheet": source_sheet,
                                "entity": "cell",
                                "item_code": cellname,
                                "cause": "Sector resolution failed (mapping/site/sector mismatch).",
                            })

                    if tech_changed:
                        # Prevent stale profile data when technology is changed.
                        cell.profile_2g = None
                        cell.profile_3g = None
                        cell.profile_4g = None
                        cell.profile_5g = None

                    if tech_norm == "2G":
                        if not cell.profile_2g:
                            cell.profile_2g = Cell2G()
                        p = cell.profile_2g
                        if has_value(row_data, "BSC"): p.bsc = get_text(row_data, "BSC")
                        if has_value(row_data, "LAC"): p.lac = get_text(row_data, "LAC")
                        if has_value(row_data, "RAC"): p.rac = get_text(row_data, "RAC")
                        if has_value(row_data, "BCCH"): p.bcch = to_int_or_none(row_data.get("BCCH"))
                        if has_value(row_data, "BSIC"): p.bsic = get_text(row_data, "BSIC")
                        if has_value(row_data, "CI"): p.ci = to_int_or_none(row_data.get("CI"))
                    elif tech_norm == "3G":
                        if not cell.profile_3g:
                            cell.profile_3g = Cell3G()
                        p = cell.profile_3g
                        if has_value(row_data, "RNC"): p.rnc = get_text(row_data, "RNC")
                        if has_value(row_data, "LAC"): p.lac = get_text(row_data, "LAC")
                        if has_value(row_data, "RAC"): p.rac = get_text(row_data, "RAC")
                        if has_value(row_data, "PSC"): p.psc = to_int_or_none(row_data.get("PSC"))
                        if has_value(row_data, "DLARFCN"): p.dlarfcn = get_text(row_data, "DLARFCN")
                        if has_value(row_data, "CI"): p.ci = to_int_or_none(row_data.get("CI"))
                    elif tech_norm == "4G":
                        if not cell.profile_4g:
                            cell.profile_4g = Cell4G()
                        p = cell.profile_4g
                        if has_value(row_data, "ENODEB"): p.enodeb = get_text(row_data, "ENODEB")
                        if has_value(row_data, "TAC"): p.tac = get_text(row_data, "TAC")
                        if has_value(row_data, "RSI"): p.rsi = get_text(row_data, "RSI")
                        if has_value(row_data, "PCI"): p.pci = to_int_or_none(row_data.get("PCI"))
                        if has_value(row_data, "EARFCN"): p.earfcn = get_text(row_data, "EARFCN")
                        if has_value(row_data, "CI"): p.ci = to_int_or_none(row_data.get("CI"))
                    elif tech_norm == "5G":
                        if not cell.profile_5g:
                            cell.profile_5g = Cell5G()
                        p = cell.profile_5g
                        if has_value(row_data, "GNODEB"): p.gnodeb = get_text(row_data, "GNODEB")
                        if has_value(row_data, "LAC"): p.lac = get_text(row_data, "LAC")
                        if has_value(row_data, "RSI"): p.rsi = get_text(row_data, "RSI")
                        if has_value(row_data, "PCI"): p.pci = to_int_or_none(row_data.get("PCI"))
                        if has_value(row_data, "ARFCN"): p.arfcn = get_text(row_data, "ARFCN")
                        if has_value(row_data, "CI"): p.ci = to_int_or_none(row_data.get("CI"))

                if row_is_existing:
                    updated += 1
                else:
                    added += 1
                pending_in_batch += 1
                if pending_in_batch >= batch_size:
                    db.session.commit()
                    pending_in_batch = 0
            except Exception as row_exc:
                db.session.rollback()
                failed_rows.append({
                    "row_number": row_number,
                    "source_sheet": source_sheet,
                    "entity": "cell",
                    "item_code": cellname,
                    "cause": f"Row processing error: {row_exc}",
                })
            emit_progress(processed_rows)

        db.session.commit()
        emit_progress(total_rows, force=True, message="Rows processed. Finalizing import...")

        if failed_rows:
            # Export non-blocking errors for post-import review.
            pd.DataFrame(failed_rows).to_excel(
                f"validation_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                index=False,
            )

        return (
            True,
            f"Cells import done: {added} added, {updated} updated, "
            f"{failed_antenna_dependencies} antenna misses, {failed_sector_resolutions} sector misses, "
            f"{ignored_preprocessing} rows ignored. Progressive commit batch={batch_size}.",
            {"failed_rows": failed_rows},
        )
    except Exception as e:
        db.session.rollback()
        return (False, f"Erreur DB: {str(e)}", {"failed_rows": failed_rows})

# ====================================================================
# Fonction de Traitement de Fichier Générique 
# ====================================================================

def process_file_data(file, entity, progress_cb=None):
    try:
        # Read uploaded bytes once and route parsing by extension/entity.
        stream = io.BytesIO(file.read())
        
        if file.filename.endswith('.csv'):
            try:
                df = pd.read_csv(stream, dtype=str)
            except UnicodeDecodeError:
                 stream.seek(0)
                 df = pd.read_csv(stream, dtype=str, encoding='latin-1')

        elif file.filename.endswith('.xlsx'):
            if entity == 'cells':
                # Cell import supports multi-sheet workbooks (one sheet per tech).
                workbook = pd.read_excel(stream, sheet_name=None)
                if not workbook:
                    return (False, "Workbook is empty.", {})
                frames = []
                for sheet_name, sheet_df in workbook.items():
                    if sheet_df is None or sheet_df.empty:
                        continue
                    local_df = sheet_df.copy()
                    local_df["__source_sheet"] = str(sheet_name)
                    local_df["__source_row"] = local_df.index + 2
                    local_df = _normalize_cell_columns(local_df)
                    inferred_tech = _infer_tech_from_sheet_name(sheet_name)
                    if inferred_tech and "TECHNOLOGY" not in local_df.columns:
                        local_df["TECHNOLOGY"] = inferred_tech
                    elif inferred_tech and "TECHNOLOGY" in local_df.columns:
                        local_df["TECHNOLOGY"] = local_df["TECHNOLOGY"].replace("", np.nan).fillna(inferred_tech)
                    frames.append(local_df)
                if not frames:
                    return (False, "No usable rows found in workbook sheets.", {})
                df = pd.concat(frames, ignore_index=True, sort=False)
            else:
                df = pd.read_excel(stream)
                # Convertir toutes les colonnes en string et nettoyer les espaces
                for col in df.columns:
                     if isinstance(col, str):
                         df.rename(columns={col: col.strip()}, inplace=True)

                     if col in df.columns:
                        try:
                            df[col] = df[col].astype(str).str.strip()
                        except:
                            pass
        else:
            error_msg = "Type de fichier non supporté. Veuillez utiliser un fichier .csv ou .xlsx."
            logger.error("Erreur de traitement pour %s: %s", entity, error_msg)
            return (False, error_msg, {})

        # Dispatch vers la fonction d'importation appropriée
        if entity == 'regions':
            return _coerce_import_result(import_regions(df))
        elif entity == 'wilayas':
            return _coerce_import_result(import_wilayas(df))
        elif entity == 'communes':
            return _coerce_import_result(import_communes(df))
        elif entity == 'antennas':
            return _coerce_import_result(import_antennas(df))
        elif entity == 'sites':
            return _coerce_import_result(import_sites(df))
        elif entity in ('suppliers', 'supplier', 'vendors', 'vendor'):
            return _coerce_import_result(import_suppliers(df))
        elif entity == 'sectors':
            return _coerce_import_result(import_sectors(df))
        elif entity == 'mapping':
            return _coerce_import_result(import_mapping(df))
        elif entity == 'cells': # Nouvelle Entité
            return _coerce_import_result(import_cells(df, progress_cb=progress_cb))
        
        else:
            error_msg = f"Entité non reconnue pour l'import: {entity}"
            logger.error("Erreur de traitement pour %s: %s", entity, error_msg)
            return (False, error_msg, {})

    except Exception as e:
        error_msg = f'Erreur de traitement du fichier pour l\'entité "{entity.upper()}". Détails: {str(e)}'
        logger.error("Erreur de traitement pour %s: %s", entity, error_msg)
        return (False, error_msg, {})


# ====================================================================
#  The Report Generator Method
# ====================================================================


def generate_validation_report(self, errors):
        """Saves validation issues to an Excel file for the user to review."""
        try:
            error_df = pd.DataFrame(errors)
            #report_name = "cell_import_validation_report.xlsx"
            
            # If you want to avoid overwriting, add a timestamp
            report_name = f"validation_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            
            error_df.to_excel(report_name, index=False)
            return report_name
        except Exception as e:
            logging.error(f"Could not save validation report: {e}")
            return None
# ====================================================================
# ROUTE PRINCIPALE DE L'IMPORTATION (Endpoint du formulaire)
# ====================================================================

@import_bp.route('/fpall/start', methods=['POST'])
@login_required
@csrf_protect
def start_fpall_import():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No file uploaded."}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({"success": False, "message": "Please select an FPall file."}), 400

    filename = file.filename
    if not filename.lower().endswith('.xlsx'):
        return jsonify({"success": False, "message": "FPall import accepts .xlsx only."}), 400

    payload = file.read()
    if not payload:
        return jsonify({"success": False, "message": "Uploaded file is empty."}), 400

    tmp = tempfile.NamedTemporaryFile(prefix="fpall_", suffix=".xlsx", delete=False)
    tmp.write(payload)
    tmp.flush()
    tmp.close()

    job_id = uuid.uuid4().hex
    _set_fpall_job(
        job_id,
        status="queued",
        progress=5,
        message="FPall import queued...",
        source_file=filename,
        created_at=datetime.utcnow().isoformat(),
        processed_rows=0,
        total_rows=0,
        eta_seconds=None,
        duration_seconds=0,
    )

    app_obj = current_app._get_current_object()
    t = threading.Thread(
        target=_run_fpall_job,
        args=(app_obj, job_id, tmp.name, filename),
        daemon=True,
    )
    t.start()

    return jsonify({
        "success": True,
        "job_id": job_id,
        "status_url": url_for('import_bp.fpall_import_status', job_id=job_id),
        "report_url": url_for('import_bp.fpall_import_report', job_id=job_id),
    }), 202


@import_bp.route('/fpall/status/<job_id>', methods=['GET'])
@login_required
def fpall_import_status(job_id):
    job = _get_fpall_job(job_id)
    if not job:
        return jsonify({"success": False, "message": "FPall job not found."}), 404

    started_at = job.get("started_at")
    finished_at = job.get("finished_at")
    duration_seconds = job.get("duration_seconds")
    if duration_seconds is None and started_at:
        try:
            dt_start = datetime.fromisoformat(str(started_at))
            dt_end = datetime.fromisoformat(str(finished_at)) if finished_at else datetime.utcnow()
            duration_seconds = round((dt_end - dt_start).total_seconds(), 2)
        except Exception:
            duration_seconds = None

    return jsonify({
        "success": True,
        "job_id": job_id,
        "status": job.get("status", "unknown"),
        "progress": int(job.get("progress", 0)),
        "message": job.get("message", ""),
        "processed_rows": int(job.get("processed_rows", 0) or 0),
        "total_rows": int(job.get("total_rows", 0) or 0),
        "eta_seconds": job.get("eta_seconds"),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "report_ready": bool(job.get("report_path")),
        "report_url": url_for('import_bp.fpall_import_report', job_id=job_id),
    }), 200


@import_bp.route('/fpall/report/<job_id>', methods=['GET'])
@login_required
def fpall_import_report(job_id):
    job = _get_fpall_job(job_id)
    report_path = job.get("report_path") if job else None
    if not report_path:
        return jsonify({"success": False, "message": "Report not ready."}), 404
    p = Path(report_path)
    if not p.exists():
        return jsonify({"success": False, "message": "Report file missing."}), 404

    return send_file(
        str(p),
        as_attachment=True,
        download_name=f"fpall_import_report_{job_id}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@import_bp.route('/report/latest/<entity>', methods=['GET'])
@login_required
def latest_entity_import_report(entity):
    key = (entity or "").strip().lower()
    if key not in {"sites", "sectors", "cells"}:
        return jsonify({"success": False, "message": "Unsupported entity for latest report."}), 400

    with _latest_import_reports_lock:
        report_path = _latest_import_reports.get(key)

    if not report_path:
        return jsonify({"success": False, "message": f"No report available yet for {key}."}), 404

    p = Path(report_path)
    if not p.exists():
        return jsonify({"success": False, "message": "Report file missing."}), 404

    return send_file(
        str(p),
        as_attachment=True,
        download_name=p.name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@import_bp.route('/report/list', methods=['GET'])
@login_required
@admin_required
def import_reports_list():
    report_type = (request.args.get("type") or "").strip().lower()
    date_from = (request.args.get("date_from") or "").strip()
    date_to = (request.args.get("date_to") or "").strip()

    rows = _load_reports_index()
    if report_type:
        rows = [r for r in rows if str(r.get("entity", "")).lower() == report_type]

    if date_from:
        rows = [r for r in rows if str(r.get("created_at", ""))[:10] >= date_from]
    if date_to:
        rows = [r for r in rows if str(r.get("created_at", ""))[:10] <= date_to]

    return jsonify({"success": True, "reports": rows}), 200


@import_bp.route('/report/download/<report_id>', methods=['GET'])
@login_required
@admin_required
def download_import_report(report_id):
    entry = _find_report_entry(report_id)
    if not entry:
        return jsonify({"success": False, "message": "Report not found."}), 404

    report_path = entry.get("report_path")
    if not report_path:
        return jsonify({"success": False, "message": "Report path is missing."}), 404

    p = Path(report_path)
    if not p.exists():
        return jsonify({"success": False, "message": "Report file missing on disk."}), 404

    return send_file(
        str(p),
        as_attachment=True,
        download_name=p.name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

@import_bp.route('/data/<entity>', methods=['POST'])
@login_required
@csrf_protect
def import_data(entity):
    # 1. Normalize the entity name
    # This handles the case where the entity comes as "cellules_reseau" from the UI
    raw_entity = entity.lower().strip()
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    # Map for logic processing (Translate UI names to backend keywords)
    logic_mapping = {
        'cellules_reseau': 'cells',
        'cellules_réseau': 'cells',
        'cellules': 'cells',
        'vendors': 'suppliers',
        'vendor': 'suppliers'
    }
    target_logic_entity = logic_mapping.get(raw_entity, raw_entity)

    # Map for redirection (Translate logic keywords to Blueprint endpoints)
    redirect_mapping = {
        'cells': 'list_bp.view_cells',
        'sites': 'list_bp.view_sites',
        'antennas': 'list_bp.view_antennas',
        'vendors': 'list_bp.view_vendors',
        'suppliers': 'list_bp.view_vendors',
        'communes': 'list_bp.view_communes',
        'wilayas': 'list_bp.view_wilayas',
        'regions': 'list_bp.view_regions'
    }

    # Basic file validation
    if 'file' not in request.files:
        message = 'Aucun fichier soumis.'
        _append_runtime_error_log(target_logic_entity, "import", message)
        if is_ajax:
            return jsonify({"success": False, "message": message}), 400
        flash(message, 'danger')
        return redirect(url_for('main.import_export'))

    file = request.files['file']
    source_filename = file.filename
    import_mode = (request.form.get('import_mode') or '').strip().lower()

    if file.filename == '':
        message = 'Veuillez selectionner un fichier a importer.'
        _append_runtime_error_log(target_logic_entity, "import", message)
        if is_ajax:
            return jsonify({"success": False, "message": message}), 400
        flash(message, 'warning')
        return redirect(url_for('main.import_export'))

    if file:
        # Pass the logic name (e.g., 'cells') to the processor
        success, message, details = process_file_data(file, target_logic_entity)

        report_url = None
        if target_logic_entity in {"sites", "sectors", "cells"}:
            try:
                _report_id, _report_path = _write_entity_import_report(
                    entity=target_logic_entity,
                    source_filename=source_filename,
                    success=success,
                    message=message,
                    details=details,
                    import_kind="fpall" if (target_logic_entity == "cells" and import_mode == "fpall") else "standard",
                )
                report_url = url_for("import_bp.latest_entity_import_report", entity=target_logic_entity)
            except Exception:
                logger.exception("Failed to generate entity import report for %s", target_logic_entity)

        if success:
            append_audit_event(
                "import",
                target_logic_entity,
                "SUCCESS",
                f"source={source_filename or ''}; mode={import_mode or 'standard'}",
            )
            if target_logic_entity == 'cells' and import_mode == 'fpall':
                message = f"FPall import completed. {message}"
            elif report_url and target_logic_entity in {"sites", "sectors", "cells"}:
                message = f"{message} | {target_logic_entity.capitalize()} report generated."

            endpoint = redirect_mapping.get(target_logic_entity)
            redirect_url = url_for(endpoint) if endpoint else url_for('main.import_export')

            if is_ajax:
                return jsonify({
                    "success": True,
                    "message": message,
                    "redirect_url": redirect_url,
                    "report_url": report_url,
                }), 200

            flash(message, 'success')
            return redirect(redirect_url)

        if is_ajax:
            append_audit_event(
                "import",
                target_logic_entity,
                "FAILED",
                f"{message} | source={source_filename or ''}; mode={import_mode or 'standard'}",
            )
            return jsonify({"success": False, "message": message, "report_url": report_url}), 400

        append_audit_event(
            "import",
            target_logic_entity,
            "FAILED",
            f"{message} | source={source_filename or ''}; mode={import_mode or 'standard'}",
        )
        _append_runtime_error_log(target_logic_entity, "import", message)
        flash(message, 'danger')
        return redirect(request.referrer or url_for('main.import_export'))

    if is_ajax:
        return jsonify({"success": False, "message": "Import request is invalid."}), 400
    return redirect(url_for('main.import_export'))
