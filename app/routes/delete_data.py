import logging

from flask import Blueprint, request, jsonify
from app import db
from app.models import Site, Cell, Antenna, Sector, Mapping
from app.security import append_audit_event, csrf_protect, get_accessible_site_ids, is_admin_user, login_required

delete_bp = Blueprint('delete_bp', __name__)
logger = logging.getLogger(__name__)

# Le dictionnaire reste correct, assurez-vous que les clés correspondent 
# à ce que vous envoyez depuis le JavaScript
MODEL_MAP = {
    'site': Site,      # Changé en singulier pour correspondre à votre logique
    'sites': Site,     # On garde le pluriel au cas où pour la compatibilité
    'cell': Cell,
    'cells': Cell,
    'antenna': Antenna,
    'antennas': Antenna,
    'sector': Sector,
    'sectors': Sector,
    'mapping': Mapping
}


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

@delete_bp.route('/delete_items/<entity>', methods=['POST'])
@login_required
@csrf_protect
def delete_items(entity):
    data = request.get_json()
    ids = data.get('ids', [])
    
    if not ids:
        return jsonify({'success': False, 'message': 'Aucun élément sélectionné.'}), 400

    model = MODEL_MAP.get(entity.lower())
    if not model:
        return jsonify({'success': False, 'message': f"L'entité '{entity}' n'est pas reconnue."}), 400

    try:
        # On récupère les instances pour que SQLAlchemy puisse gérer la cascade
        items_to_delete = model.query.filter(model.id.in_(ids)).all()
        
        if not items_to_delete:
             return jsonify({'success': False, 'message': 'Éléments introuvables en base.'}), 404

        if any(not _item_allowed(item) for item in items_to_delete):
            return jsonify({'success': False, 'message': "Acces refuse sur un ou plusieurs elements."}), 403

        for item in items_to_delete:
            db.session.delete(item)
        
        db.session.commit()
        append_audit_event("delete", entity, "SUCCESS", f"{len(items_to_delete)} items")
        
        return jsonify({
            'success': True, 
            'message': f'{len(items_to_delete)} élément(s) supprimé(s) (ainsi que leurs dépendances).'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.exception("Erreur suppression")
        append_audit_event("delete", entity, "FAILED", str(e))
        return jsonify({'success': False, 'message': "Erreur lors de la suppression en cascade."}), 500
