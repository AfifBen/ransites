#routes/helpers.py

from flask import Blueprint, jsonify
from app import db
from app.models import Site, Sector, Supplier, Region, Wilaya, Commune, Antenna
from app.security import get_accessible_commune_ids, get_accessible_site_ids, login_required

helper_bp = Blueprint('helpers', __name__)

@helper_bp.route('/get_communes/<wilaya_name>')
def get_communes(wilaya_name):
    # Utile si vous voulez faire des listes liées plus tard
    wilaya = Wilaya.query.filter_by(name=wilaya_name).first()
    if wilaya:
        communes = Commune.query.filter_by(wilaya_id=wilaya.id).order_by(Commune.name).all()
        return jsonify([c.name for c in communes])
    return jsonify([])

@helper_bp.route('/get_sites_all')
@login_required
def get_sites_all():
    query = Site.query.join(Commune, Site.commune_id == Commune.id)
    accessible_sites = get_accessible_site_ids()
    if accessible_sites is not None:
        if not accessible_sites:
            return jsonify([])
        query = query.filter(Site.id.in_(list(accessible_sites)))
    sites = query.with_entities(Site.id, Site.code_site, Site.name, Site.commune_id, Commune.wilaya_id).all()
    # On renvoie une liste d'objets avec id et name
    
    return jsonify([
        {
            "id": s.id,
            "name": s.code_site,
            "label": f"{s.code_site} - {s.name or ''}".strip(" -"),
            "commune_id": s.commune_id,
            "wilaya_id": s.wilaya_id,
        }
        for s in sites
    ])

@helper_bp.route('/get_suppliers')
def get_suppliers():
    suppliers = Supplier.query.all()
    # On renvoie une liste d'objets avec id et name
    return jsonify([{"id": s.id, "name": s.name} for s in suppliers])

@helper_bp.route('/get_communes_by_wilaya_code/<code>')
def get_communes_by_wilaya_code(code):
    try:
        # On convertit le code (ex: "28") en entier pour chercher l'ID
        wilaya_id = int(code)
        wilaya = db.session.get(Wilaya, wilaya_id)
        if not wilaya:
            return jsonify([])
        
        return jsonify([{"id": c.id, "name": c.name} for c in wilaya.communes])
    except ValueError:
        return jsonify([])

@helper_bp.route('/get_communes_all')
@login_required
def get_communes_all():
    query = Commune.query
    accessible_communes = get_accessible_commune_ids()
    if accessible_communes is not None:
        if not accessible_communes:
            return jsonify([])
        query = query.filter(Commune.id.in_(list(accessible_communes)))
    communes = query.with_entities(Commune.id, Commune.name, Commune.wilaya_id).all()
    return jsonify([{"id": c.id, "name": c.name, "wilaya_id": c.wilaya_id} for c in communes])

@helper_bp.route('/get_sectors_all')
def get_sectors_all():
    query = Sector.query
    accessible_sites = get_accessible_site_ids()
    if accessible_sites is not None:
        if not accessible_sites:
            return jsonify([])
        query = query.filter(Sector.site_id.in_(list(accessible_sites)))
    sectors = query.all()
    return jsonify([{"id": s.id, "name": f"{s.code_sector}"} for s in sectors])

@helper_bp.route('/get_regions')
def get_regions():
    regions = Region.query.all()
    return jsonify([{"id": r.id, "name": r.name} for r in regions])

@helper_bp.route('/get_wilayas')
def get_wilayas():
    wilayas = Wilaya.query.all()
    return jsonify([{"id": w.id, "name": f"{w.id} - {w.name}", "label": w.name} for w in wilayas])

@helper_bp.route('/get_antennas_all')
def get_antennas_all():
    antennas = Antenna.query.all()
    return jsonify([{"id": a.id, "name": f"{a.model} ({a.frequency})"} for a in antennas])
