#route/list_data.py

from flask import Blueprint, render_template
from sqlalchemy import select
import logging
from app.security import get_accessible_commune_ids, get_accessible_site_ids, login_required

# --- IMPORTS CRITIQUES : Ajustez si nécessaire ---
try:
    from app import db 
    from app.models import Region, Wilaya, Commune, Site, Antenna, Supplier, Sector, Mapping, Cell
except ImportError:
    # Définir des classes factices si l'environnement Flask/SQLAlchemy n'est pas complet
    class DummyDB:
        def session(self): return self
        def execute(self, statement): return self 
        def scalars(self): return []
        def all(self): return []
    db = DummyDB()
    class Region: pass
    class Wilaya: pass
    class Commune: pass
    class Site: pass
    class Antenna: pass
    class Supplier: pass
    class Sector: pass
    class Mapping: pass
    class Cell: pass
# --- FIN DES IMPORTS ---

list_bp = Blueprint('list_bp', __name__)
logger = logging.getLogger(__name__)

# ====================================================================
# FONCTIONS D'AFFICHAGE (LISTING)
# ====================================================================

def list_sites():
    """
    Liste tous les sites avec les informations associées (Commune, Wilaya, Region, Supplier).
    """
    try:
        # Construction de la requête avec les jointures nécessaires (Commune, Wilaya, Region, Supplier)
        statement = select(
            Site,
            Commune.name.label('commune_name'),
            Wilaya.name.label('wilaya_name'),
            Region.name.label('region_name'),
            Supplier.name.label('supplier_name')
        ) \
        .join(Commune, Site.commune_id == Commune.id) \
        .join(Wilaya, Commune.wilaya_id == Wilaya.id) \
        .join(Region, Wilaya.region_id == Region.id) \
        .outerjoin(Supplier, Site.supplier_id == Supplier.id) \
        .order_by(Site.code_site)
        
        accessible_sites = get_accessible_site_ids()
        if accessible_sites is not None:
            if not accessible_sites:
                return []
            statement = statement.filter(Site.id.in_(list(accessible_sites)))

        sites_data = db.session.execute(statement).all()
        
        sites = []
        for site, commune_name, wilaya_name, region_name, supplier_name in sites_data:
            sites.append({
                'id': site.id,
                'code_site': site.code_site,
                'name': site.name,
                'latitude': site.latitude,
                'longitude': site.longitude,
                'altitude': site.altitude,
                'support_nature': site.support_nature,
                'support_type': site.support_type,
                'support_height': site.support_height,
                'status': site.status,
                'supplier_name': supplier_name,
                'commune_name': commune_name,
                'wilaya_name': wilaya_name,
                'region_name': region_name,
                'address': site.address,
                'comments': site.comments,
            })
        return sites
    except Exception:
        logger.exception("Erreur lors de la récupération des sites")
        return []

def list_sectors():
    """
    Liste tous les secteurs avec le Code Site associé.
    """
    try:
        statement = select(
            Sector,
            Site.code_site.label('site_code')
        ).join(Site, Sector.site_id == Site.id).order_by(Sector.code_sector)

        accessible_sites = get_accessible_site_ids()
        if accessible_sites is not None:
            if not accessible_sites:
                return []
            statement = statement.filter(Site.id.in_(list(accessible_sites)))
        
        sectors_data = db.session.execute(statement).all()
        
        sectors = []
        for sector, site_code in sectors_data:
            sectors.append({
                'id': sector.id,
                'code_sector': sector.code_sector,
                'azimuth': sector.azimuth,
                'hba': sector.hba,
                'coverage_goal': sector.coverage_goal,
                'site_code': site_code
            })
        return sectors
    except Exception:
        logger.exception("Erreur secteurs")
        return []

def list_cells():
    """
    Liste toutes les cellules avec les infos Antenna et Sector.
    """
    try:
        # On utilise une jointure pour récupérer les noms au lieu des simples IDs
        query = db.session.query(
            Cell, 
            Antenna.model.label('antenna_model'),
            Sector.code_sector.label('sector_name')
        ).outerjoin(Antenna, Cell.antenna_id == Antenna.id)\
         .outerjoin(Sector, Cell.sector_id == Sector.id)\
         .outerjoin(Site, Sector.site_id == Site.id)

        accessible_sites = get_accessible_site_ids()
        if accessible_sites is not None:
            if not accessible_sites:
                return []
            query = query.filter(Site.id.in_(list(accessible_sites)))

        results = query.all()

        data = []
        for cell, ant_model, sec_name in results:
            tech = (cell.technology or "").strip().upper()
            tech_settings = "N/A"
            if tech == "2G" and cell.profile_2g:
                tech_settings = (
                    f"BSC={cell.profile_2g.bsc or '-'} / "
                    f"LAC={cell.profile_2g.lac or '-'} / "
                    f"RAC={cell.profile_2g.rac or '-'} / "
                    f"BSIC={cell.profile_2g.bsic or '-'} / "
                    f"BCCH={cell.profile_2g.bcch or '-'}"
                )
            elif tech == "3G" and cell.profile_3g:
                tech_settings = (
                    f"RNC={cell.profile_3g.rnc or '-'} / "
                    f"LAC={cell.profile_3g.lac or '-'} / "
                    f"RAC={cell.profile_3g.rac or '-'} / "
                    f"PSC={cell.profile_3g.psc or '-'} / "
                    f"DLARFCN={cell.profile_3g.dlarfcn or '-'}"
                )
            elif tech == "4G" and cell.profile_4g:
                tech_settings = (
                    f"eNodeB={cell.profile_4g.enodeb or '-'} / "
                    f"TAC={cell.profile_4g.tac or '-'} / "
                    f"RSI={cell.profile_4g.rsi or '-'} / "
                    f"PCI={cell.profile_4g.pci or '-'} / "
                    f"EARFCN={cell.profile_4g.earfcn or '-'}"
                )
            elif tech == "5G" and cell.profile_5g:
                tech_settings = (
                    f"GNODEB={cell.profile_5g.gnodeb or '-'} / "
                    f"LAC={cell.profile_5g.lac or '-'} / "
                    f"RSI={cell.profile_5g.rsi or '-'} / "
                    f"PCI={cell.profile_5g.pci or '-'} / "
                    f"ARFCN={cell.profile_5g.arfcn or '-'}"
                )

            data.append({
                'id': cell.id,
                'cellname': cell.cellname,
                'technology': cell.technology,
                'frequency': cell.frequency,
                'antenna': ant_model or 'N/A',
                'sector': sec_name or 'N/A',
                'tilt_mech': cell.tilt_mechanical,
                'tilt_elec': cell.tilt_electrical,
                'tech_settings': tech_settings,
            })
        return data
    except Exception:
        logger.exception("Erreur list_cells")
        return []

def list_wilayas():
    try:
        statement = select(Wilaya, Region.name).join(Region, Wilaya.region_id == Region.id).order_by(Wilaya.id)
        accessible_communes = get_accessible_commune_ids()
        if accessible_communes is not None:
            if not accessible_communes:
                return []
            statement = statement.join(Commune, Commune.wilaya_id == Wilaya.id).filter(Commune.id.in_(list(accessible_communes))).distinct()
        results = db.session.execute(statement).all()
        return [{'id': w.id, 'name': w.name, 'region_name': r_name} for w, r_name in results]
    except: return []

def list_communes():
    try:
        statement = select(Commune, Wilaya.name).join(Wilaya, Commune.wilaya_id == Wilaya.id)
        accessible_communes = get_accessible_commune_ids()
        if accessible_communes is not None:
            if not accessible_communes:
                return []
            statement = statement.filter(Commune.id.in_(list(accessible_communes)))
        results = db.session.execute(statement).all()
        return [{'id': c.id, 'name': c.name, 'wilaya_name': w_name} for c, w_name in results]
    except: return []


# ====================================================================
# ROUTES
# ====================================================================

# route/list_data.py (Partial Update)

@list_bp.route('/sites', methods=['GET'])
@login_required
def view_sites():
    sites = list_sites()

    # Keep ID internally (used by edit/delete logic) but hide it in DataTable.
    column_keys = [
        'id',
        'code_site',
        'name',
        'supplier_name',
        'latitude',
        'longitude',
        'altitude',
        'support_nature',
        'support_height',
        'commune_name',
        'status',
    ]

    data_for_table = []
    for site in sites:
        row = []
        for key in column_keys:
            value = site.get(key)
            row.append(str(value) if value is not None else '')
        data_for_table.append(row)

    column_headers = [
        'ID',
        'Site Code',
        'Site Name',
        'Vendor',
        'Latitude',
        'Longitude',
        'Altitude',
        'Support Nature',
        'Support Height',
        'Commune',
        'Status',
    ]

    return render_template(
        'tables/model_viewer.html',
        id_table='sitesTable',
        titre='Sites',
        entity_type='sites',
        colonnes=column_headers,
        donnees=data_for_table,
    )

@list_bp.route('/sectors', methods=['GET'])
@login_required
def view_sectors():
    sectors = list_sectors()
    
    # Clés du dictionnaire à mapper
    column_keys = ['id', 'code_sector', 'site_code', 'azimuth', 'hba', 'coverage_goal']
    
    data_for_table = []
    for sector in sectors:
        row = []
        for key in column_keys:
            if key == 'actions':
                action_html = f"""
                    <div class="d-flex justify-content-center">
                        <button class="btn btn-warning btn-sm me-1" title="Modifier" 
                                data-bs-toggle="modal" data-bs-target="#editSectorModal" 
                                data-sector-id="{sector['id']}">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-danger btn-sm" title="Supprimer" 
                                onclick="confirmDelete('{sector['id']}', '{sector['code_sector']}', 'sector')">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                """
                row.append(action_html)
            else:
                value = sector.get(key)
                row.append(str(value) if value is not None else '')
        data_for_table.append(row)

    column_headers = ['ID', 'Code Secteur', 'Site Parent', 'Azimuth', 'HBA', 'Objectif Couverture']

    return render_template('tables/model_viewer.html', # Template spécifique ou générique
                           id_table='sectorsTable',
                           titre='Sectors',
                           colonnes=column_headers,
                           donnees=data_for_table)

@list_bp.route('/cells')
@login_required
def view_cells():
    data = list_cells()
    
    # Définition des entêtes pour le tableau HTML
    headers = ['ID', 'Cell Name', 'Tech', 'Freq', 'Antenna', 'Sector', 'M-Tilt', 'E-Tilt', 'Tech Settings']
    column_keys = ['id', 'cellname', 'technology', 'frequency', 'antenna', 'sector', 'tilt_mech', 'tilt_elec', 'tech_settings']
    
    # Transformation des dictionnaires en listes pour le template
    rows = [[str(item.get(k) or '') for k in column_keys] for item in data]
    
    return render_template('tables/model_viewer.html', 
                           id_table='cellsTable', 
                           titre='Cells', 
                           colonnes=headers, 
                           donnees=rows)

@list_bp.route('/wilayas')
@login_required
def view_wilayas():
    data = list_wilayas()
    column_keys = ['id', 'name', 'region_name']
    headers = ['Code Wilaya', 'Nom Wilaya', 'Région']
    
    rows = [[str(item.get(k) or '') for k in column_keys] for item in data]
    return render_template('tables/model_viewer.html', id_table='wilayasTable', 
                           titre='Wilayas', colonnes=headers, donnees=rows)

@list_bp.route('/communes')
@login_required
def view_communes():
    data = list_communes()
    column_keys = ['id', 'name', 'wilaya_name']
    headers = ['ID', 'Nom Commune', 'Wilaya']
    
    rows = [[str(item.get(k) or '') for k in column_keys] for item in data]
    return render_template('tables/model_viewer.html', id_table='communesTable', 
                           titre='Communes', colonnes=headers, donnees=rows)

@list_bp.route('/antennas')
@login_required
def view_antennas():
    items = Antenna.query.all()
    headers = ['id','Name','Frequency', 'Model', 'V-Tilt', 'H-Tilt', 'gain']
    rows = [[str(a.id),str(a.name), a.frequency, a.model, str(a.vbeamwidth), str(a.hbeamwidth), str(a.gain)] for a in items]
    
    return render_template('tables/model_viewer.html', id_table='antennasTable', 
                           titre='Antennas', colonnes=headers, donnees=rows)

@list_bp.route('/vendors')
@login_required
def view_vendors():
    items = Supplier.query.all()
    headers = ['ID', 'Nom du Vendor']
    rows = [[str(s.id), s.name] for s in items]
    
    return render_template('tables/model_viewer.html', id_table='vendorsTable', 
                           titre='Vendors', colonnes=headers, donnees=rows)

@list_bp.route('/regions')
@login_required
def view_regions():
    items = Region.query.all()
    headers = ['ID', 'Nom de la Région']
    rows = [[str(r.id), r.name] for r in items]
    
    return render_template('tables/model_viewer.html', id_table='regionsTable', 
                           titre='Regions', colonnes=headers, donnees=rows)
