# routes/add_data.py
import logging
import json
from urllib.request import urlopen
from urllib.parse import urlencode

from flask import Blueprint, request, redirect, flash
from app import db
from app.models import Antenna, Site, Sector, Supplier, Region, Wilaya, Commune, Cell, Cell2G, Cell3G, Cell4G, Cell5G, User
from app.security import append_audit_event, csrf_protect, get_accessible_commune_ids, get_accessible_site_ids, is_admin_user, login_required

add_data_bp = Blueprint('add_data', __name__)
logger = logging.getLogger(__name__)

# EXACT same mapping as edit_data.py for architectural consistency
MODEL_MAP = {
    "site": Site,
    "sites": Site,
    "sector": Sector,
    "sectors": Sector,
    "cell": Cell,
    "cells": Cell,
    "region": Region,
    "regions": Region,
    "wilaya": Wilaya,
    "wilayas": Wilaya,
    "commune": Commune,
    "communes": Commune,
    "antenna": Antenna,
    "antennas": Antenna,
    "vendor": Supplier,
    "vendors": Supplier,
    "supplier": Supplier,
    "user": User,
    "users": User,
}


def _to_int_or_none(raw):
    # Convert free-text form values to integer when possible.
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
    # Lightweight public elevation lookup; returns None on network/API errors.
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
    # Compute altitude from coordinates only when altitude is not provided.
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
    # Auto-resolve sector from mapping using cellname + technology + frequency.
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


def _sync_cell_profile(cell, form_data):
    # Only one tech profile should exist for a cell at a time.
    tech = (getattr(cell, "technology", "") or "").strip().upper()

    if tech == "2G":
        cell.profile_3g = None
        cell.profile_4g = None
        cell.profile_5g = None
        p = cell.profile_2g or Cell2G()
        p.bsc = (form_data.get("bsc") or "").strip() or None
        p.lac = (form_data.get("lac_2g") or "").strip() or None
        p.rac = (form_data.get("rac_2g") or "").strip() or None
        p.bcch = _to_int_or_none(form_data.get("bcch"))
        p.bsic = (form_data.get("bsic") or "").strip() or None
        p.ci = _to_int_or_none(form_data.get("ci_2g"))
        cell.profile_2g = p
    elif tech == "3G":
        cell.profile_2g = None
        cell.profile_4g = None
        cell.profile_5g = None
        p = cell.profile_3g or Cell3G()
        p.lac = (form_data.get("lac_3g") or "").strip() or None
        p.rac = (form_data.get("rac_3g") or "").strip() or None
        p.psc = _to_int_or_none(form_data.get("psc"))
        p.rnc = (form_data.get("rnc") or "").strip() or None
        p.dlarfcn = (form_data.get("dlarfcn") or "").strip() or None
        p.ci = _to_int_or_none(form_data.get("ci_3g"))
        cell.profile_3g = p
    elif tech == "4G":
        cell.profile_2g = None
        cell.profile_3g = None
        cell.profile_5g = None
        p = cell.profile_4g or Cell4G()
        p.enodeb = (form_data.get("enodeb") or "").strip() or None
        p.tac = (form_data.get("tac") or "").strip() or None
        p.rsi = (form_data.get("rsi_4g") or "").strip() or None
        p.pci = _to_int_or_none(form_data.get("pci_4g"))
        p.earfcn = (form_data.get("earfcn") or "").strip() or None
        p.ci = _to_int_or_none(form_data.get("ci_4g"))
        cell.profile_4g = p
    elif tech == "5G":
        cell.profile_2g = None
        cell.profile_3g = None
        cell.profile_4g = None
        p = cell.profile_5g or Cell5G()
        p.gnodeb = (form_data.get("gnodeb") or "").strip() or None
        p.lac = (form_data.get("lac_5g") or "").strip() or None
        p.rsi = (form_data.get("rsi_5g") or "").strip() or None
        p.pci = _to_int_or_none(form_data.get("pci_5g"))
        p.arfcn = (form_data.get("arfcn") or "").strip() or None
        p.ci = _to_int_or_none(form_data.get("ci_5g"))
        cell.profile_5g = p


def _ensure_add_permission(model_class, form_data):
    # Enforce non-admin perimeter rules before insert.
    if is_admin_user():
        return True, ""

    if model_class is User:
        return False, "Acces reserve a l'administrateur pour cette entite."

    if model_class not in (Site, Sector, Cell):
        return False, "Acces reserve a l'administrateur pour cette entite."

        accessible_communes = get_accessible_commune_ids()
        if accessible_communes is None:
            return True, ""

    if model_class is Site:
        # Site creation is bound to accessible communes.
        commune_id = form_data.get("commune_id")
        try:
            commune_id = int(commune_id)
        except (TypeError, ValueError):
            return False, "Commune invalide."
        return (commune_id in accessible_communes), "Cette commune n'est pas dans votre perimetre."

    if model_class is Sector:
        # Sector creation must target an accessible site.
        site_id = form_data.get("site_id")
        try:
            site_id = int(site_id)
        except (TypeError, ValueError):
            return False, "Site invalide."
        site = db.session.get(Site, site_id)
        if not site:
            return False, "Site introuvable."
        accessible_sites = get_accessible_site_ids()
        if accessible_sites is None:
            return True, ""
        return (site.id in accessible_sites), "Ce site n'est pas dans votre perimetre."

    if model_class is Cell:
        # Cell creation inherits access rights from parent sector/site.
        sector_id = form_data.get("sector_id")
        if not sector_id:
            # Sector can now be auto-resolved from mapping after insert payload parsing.
            return True, ""
        try:
            sector_id = int(sector_id)
        except (TypeError, ValueError):
            return False, "Secteur invalide."
        sector = db.session.get(Sector, sector_id)
        if not sector or not sector.site:
            return False, "Secteur introuvable."
        accessible_sites = get_accessible_site_ids()
        if accessible_sites is None:
            return True, ""
        return (sector.site.id in accessible_sites), "Ce secteur n'est pas dans votre perimetre."

    return False, "Acces refuse."

@add_data_bp.route('/add_item/<entity>', methods=['POST'])
@login_required
@csrf_protect
def add_item(entity):
    """Crée un objet SQLAlchemy de manière générique, comme update_item."""
    model_class = MODEL_MAP.get(entity.lower())
    
    if not model_class:
        flash(f"Entité '{entity}' non reconnue", "danger")
        return redirect(request.referrer)

    try:
        # 1. Instancier le modèle dynamiquement
        new_item = model_class()
        
        # 2. Récupérer les données du formulaire
        form_data = request.form.to_dict()

        allowed, reason = _ensure_add_permission(model_class, form_data)
        if not allowed:
            flash(reason, "danger")
            return redirect(request.referrer)

        # 3. Même logique que edit_data.py : boucle sur les colonnes
        for key, value in form_data.items():
            if hasattr(new_item, key):
                # Gestion des valeurs vides (None pour la DB)
                setattr(new_item, key, value if value != "" else None)

        if model_class is Site:
            _auto_fill_site_altitude(new_item)

        if model_class is User:
            # User insert uses dedicated validation and scope assignment.
            username = (form_data.get("username") or "").strip()
            password = form_data.get("password") or ""
            if not username:
                raise ValueError("Username obligatoire.")
            if User.query.filter_by(username=username).first():
                raise ValueError("Username deja utilise.")
            if len(password) < 6:
                raise ValueError("Le mot de passe doit contenir au moins 6 caracteres.")

            new_item.username = username
            new_item.is_admin = str(form_data.get("is_admin", "")).lower() in {"on", "true", "1", "yes"}
            new_item.is_active = str(form_data.get("is_active", "")).lower() in {"on", "true", "1", "yes"}
            new_item.set_password(password)

            wilaya_ids = [int(v) for v in request.form.getlist("wilaya_ids") if str(v).isdigit()]
            region_ids = [int(v) for v in request.form.getlist("region_ids") if str(v).isdigit()]
            commune_ids = [int(v) for v in request.form.getlist("commune_ids") if str(v).isdigit()]
            site_ids = [int(v) for v in request.form.getlist("site_ids") if str(v).isdigit()]

            new_item.assigned_regions = Region.query.filter(Region.id.in_(region_ids)).all() if region_ids else []
            new_item.assigned_wilayas = Wilaya.query.filter(Wilaya.id.in_(wilaya_ids)).all() if wilaya_ids else []
            new_item.assigned_communes = Commune.query.filter(Commune.id.in_(commune_ids)).all() if commune_ids else []
            new_item.assigned_sites = Site.query.filter(Site.id.in_(site_ids)).all() if site_ids else []

        if model_class is Cell:
            # Keep tech-specific fields in child profile tables.
            new_item.technology = (new_item.technology or "").strip().upper()
            _sync_cell_profile(new_item, form_data)
            auto_found = _auto_assign_cell_sector(new_item)
            if not auto_found and not new_item.sector_id:
                raise ValueError("Sector auto-resolution failed for this cell (check mapping/sector/site).")

            if not is_admin_user():
                accessible_sites = get_accessible_site_ids()
                if accessible_sites is not None:
                    sec = db.session.get(Sector, new_item.sector_id) if new_item.sector_id else None
                    if not sec or not sec.site_id or sec.site_id not in accessible_sites:
                        raise ValueError("Cell resolved outside your scope.")

        db.session.add(new_item)
        db.session.flush()

        # If a site is created, optionally create linked sectors from dynamic form rows.
        if model_class is Site:
            raw_count = form_data.get("sector_count", "0")
            try:
                sector_count = max(0, int(raw_count))
            except ValueError:
                sector_count = 0

            for i in range(1, sector_count + 1):
                code_sector = (form_data.get(f"sector_{i}_code_sector") or "").strip()
                azimuth_raw = (form_data.get(f"sector_{i}_azimuth") or "").strip()
                hba_raw = (form_data.get(f"sector_{i}_hba") or "").strip()
                coverage_goal = (form_data.get(f"sector_{i}_coverage_goal") or "").strip() or None

                if not code_sector and not azimuth_raw and not hba_raw:
                    continue

                if not code_sector or not azimuth_raw or not hba_raw:
                    raise ValueError(f"Secteur {i}: code, azimuth et hba sont obligatoires.")

                try:
                    azimuth = int(float(azimuth_raw))
                    hba = int(float(hba_raw))
                except ValueError as exc:
                    raise ValueError(f"Secteur {i}: azimuth/hba doivent etre numeriques.") from exc

                if azimuth < 0 or azimuth > 360:
                    raise ValueError(f"Secteur {i}: azimuth doit etre entre 0 et 360.")

                db.session.add(
                    Sector(
                        code_sector=code_sector,
                        azimuth=azimuth,
                        hba=hba,
                        coverage_goal=coverage_goal,
                        site_id=new_item.id,
                    )
                )

        db.session.commit()
        append_audit_event("create", entity, "SUCCESS", f"{entity} created")
        flash(f"{entity.capitalize()} ajouté avec succès !", "success")
        
    except Exception as e:
        db.session.rollback()
        logger.exception("ADD ERROR")
        append_audit_event("create", entity, "FAILED", str(e))
        flash(f"Erreur lors de l'ajout : {str(e)}", "danger")
    
    return redirect(request.referrer)
