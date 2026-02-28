#route/list_data.py

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import select, or_, asc, desc, cast, String
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import joinedload
import logging
from app.security import admin_required, get_accessible_commune_ids, get_accessible_site_ids, login_required

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

def list_sites(dq_filter=''):
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

        if dq_filter == 'without_sectors':
            # Keep only correction scope: sites that still have no sector linked.
            statement = (
                statement
                .outerjoin(Sector, Sector.site_id == Site.id)
                .filter(Sector.id.is_(None))
            )
        elif dq_filter == 'without_vendor':
            statement = statement.filter(Site.supplier_id.is_(None))
        
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

def list_sectors(without_cells=False):
    """
    Liste tous les secteurs avec le Code Site associé.
    """
    try:
        statement = select(
            Sector,
            Site.code_site.label('site_code')
        ).join(Site, Sector.site_id == Site.id).order_by(Sector.code_sector)
        if without_cells:
            statement = (
                statement
                .outerjoin(Cell, Cell.sector_id == Sector.id)
                .filter(Cell.id.is_(None))
            )

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
        # Eager-load related objects to avoid N+1 queries on tech profiles.
        query = (
            db.session.query(Cell)
            .options(
                joinedload(Cell.antenna),
                joinedload(Cell.sector),
                joinedload(Cell.profile_2g),
                joinedload(Cell.profile_3g),
                joinedload(Cell.profile_4g),
                joinedload(Cell.profile_5g),
            )
        )

        accessible_sites = get_accessible_site_ids()
        if accessible_sites is not None:
            if not accessible_sites:
                return []
            query = (
                query
                .outerjoin(Sector, Cell.sector_id == Sector.id)
                .outerjoin(Site, Sector.site_id == Site.id)
                .filter(Site.id.in_(list(accessible_sites)))
            )

        results = query.order_by(Cell.cellname.asc()).all()

        data = []
        for cell in results:
            ant_model = cell.antenna.model if cell.antenna else None
            sec_name = cell.sector.code_sector if cell.sector else None
            tech = (cell.technology or "").strip().upper()
            tech_settings = "N/A"
            if tech == "2G" and cell.profile_2g:
                tech_settings = (
                    f"BSC={cell.profile_2g.bsc or '-'} / "
                    f"LAC={cell.profile_2g.lac or '-'} / "
                    f"RAC={cell.profile_2g.rac or '-'} / "
                    f"BSIC={cell.profile_2g.bsic or '-'} / "
                    f"BCCH={cell.profile_2g.bcch or '-'} / "
                    f"CI={cell.profile_2g.ci or '-'}"
                )
            elif tech == "3G" and cell.profile_3g:
                tech_settings = (
                    f"RNC={cell.profile_3g.rnc or '-'} / "
                    f"LAC={cell.profile_3g.lac or '-'} / "
                    f"RAC={cell.profile_3g.rac or '-'} / "
                    f"PSC={cell.profile_3g.psc or '-'} / "
                    f"DLARFCN={cell.profile_3g.dlarfcn or '-'} / "
                    f"CI={cell.profile_3g.ci or '-'}"
                )
            elif tech == "4G" and cell.profile_4g:
                tech_settings = (
                    f"eNodeB={cell.profile_4g.enodeb or '-'} / "
                    f"TAC={cell.profile_4g.tac or '-'} / "
                    f"RSI={cell.profile_4g.rsi or '-'} / "
                    f"PCI={cell.profile_4g.pci or '-'} / "
                    f"EARFCN={cell.profile_4g.earfcn or '-'} / "
                    f"CI={cell.profile_4g.ci or '-'}"
                )
            elif tech == "5G" and cell.profile_5g:
                tech_settings = (
                    f"GNODEB={cell.profile_5g.gnodeb or '-'} / "
                    f"LAC={cell.profile_5g.lac or '-'} / "
                    f"RSI={cell.profile_5g.rsi or '-'} / "
                    f"PCI={cell.profile_5g.pci or '-'} / "
                    f"ARFCN={cell.profile_5g.arfcn or '-'} / "
                    f"CI={cell.profile_5g.ci or '-'}"
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
    dq_filter = (request.args.get("dq_filter") or "").strip().lower()
    if dq_filter not in {"without_sectors", "without_vendor"}:
        without_sectors = str(request.args.get("without_sectors", "")).strip().lower() in {"1", "true", "yes", "on"}
        dq_filter = "without_sectors" if without_sectors else ""
    sites = list_sites(dq_filter=dq_filter)

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
        dq_filter=dq_filter,
        colonnes=column_headers,
        donnees=data_for_table,
    )

@list_bp.route('/sectors', methods=['GET'])
@login_required
def view_sectors():
    dq_filter = (request.args.get("dq_filter") or "").strip().lower()
    sectors = list_sectors(without_cells=(dq_filter == "without_cells"))
    
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
                           entity_type='sectors',
                           dq_filter=dq_filter,
                           colonnes=column_headers,
                           donnees=data_for_table)

@list_bp.route('/cells')
@login_required
def view_cells():
    dq_filter = (request.args.get("dq_filter") or "").strip().lower()
    if dq_filter not in {"without_sector", "without_antenna"}:
        dq_filter = ""
    # Cells page is rendered empty and filled by server-side DataTables AJAX.
    headers = ['ID', 'Cell Name', 'Tech', 'Freq', 'Antenna', 'Sector', 'M-Tilt', 'E-Tilt', 'Tech Settings']
    return render_template('tables/model_viewer.html',
                           id_table='cellsTable',
                           titre='Cells',
                           entity_type='cells',
                           dq_filter=dq_filter,
                           colonnes=headers,
                           donnees=[])



def _build_cell_tech_settings(cell):
    tech = (cell.technology or '').strip().upper()
    if tech == '2G' and cell.profile_2g:
        return (
            f"BSC={cell.profile_2g.bsc or '-'} / "
            f"LAC={cell.profile_2g.lac or '-'} / "
            f"RAC={cell.profile_2g.rac or '-'} / "
            f"BSIC={cell.profile_2g.bsic or '-'} / "
            f"BCCH={cell.profile_2g.bcch or '-'} / "
            f"CI={cell.profile_2g.ci or '-'}"
        )
    if tech == '3G' and cell.profile_3g:
        return (
            f"RNC={cell.profile_3g.rnc or '-'} / "
            f"LAC={cell.profile_3g.lac or '-'} / "
            f"RAC={cell.profile_3g.rac or '-'} / "
            f"PSC={cell.profile_3g.psc or '-'} / "
            f"DLARFCN={cell.profile_3g.dlarfcn or '-'} / "
            f"CI={cell.profile_3g.ci or '-'}"
        )
    if tech == '4G' and cell.profile_4g:
        return (
            f"eNodeB={cell.profile_4g.enodeb or '-'} / "
            f"TAC={cell.profile_4g.tac or '-'} / "
            f"RSI={cell.profile_4g.rsi or '-'} / "
            f"PCI={cell.profile_4g.pci or '-'} / "
            f"EARFCN={cell.profile_4g.earfcn or '-'} / "
            f"CI={cell.profile_4g.ci or '-'}"
        )
    if tech == '5G' and cell.profile_5g:
        return (
            f"GNODEB={cell.profile_5g.gnodeb or '-'} / "
            f"LAC={cell.profile_5g.lac or '-'} / "
            f"RSI={cell.profile_5g.rsi or '-'} / "
            f"PCI={cell.profile_5g.pci or '-'} / "
            f"ARFCN={cell.profile_5g.arfcn or '-'} / "
            f"CI={cell.profile_5g.ci or '-'}"
        )
    return 'N/A'


@list_bp.route('/cells/data', methods=['GET'])
@login_required
def cells_data():
    try:
        draw = int(request.args.get('draw', 1))
        start = max(int(request.args.get('start', 0)), 0)
        length = int(request.args.get('length', 50))
        length = 50 if length <= 0 else min(length, 200)
        search_value = (request.args.get('search[value]', '') or '').strip()
        dq_filter = (request.args.get('dq_filter') or '').strip().lower()
        order_col = int(request.args.get('order[0][column]', 2))
        order_dir = (request.args.get('order[0][dir]', 'asc') or 'asc').lower()

        query = (
            db.session.query(Cell)
            .options(
                joinedload(Cell.antenna),
                joinedload(Cell.sector),
                joinedload(Cell.profile_2g),
                joinedload(Cell.profile_3g),
                joinedload(Cell.profile_4g),
                joinedload(Cell.profile_5g),
            )
            .outerjoin(Antenna, Cell.antenna_id == Antenna.id)
            .outerjoin(Sector, Cell.sector_id == Sector.id)
            .outerjoin(Site, Sector.site_id == Site.id)
        )

        accessible_sites = get_accessible_site_ids()
        if accessible_sites is not None:
            if not accessible_sites:
                return jsonify({'draw': draw, 'recordsTotal': 0, 'recordsFiltered': 0, 'data': []})
            query = query.filter(Site.id.in_(list(accessible_sites)))

        if dq_filter == 'without_sector':
            query = query.filter(Cell.sector_id.is_(None))
        elif dq_filter == 'without_antenna':
            query = query.filter(Cell.antenna_id.is_(None))

        records_total = query.count()

        if search_value:
            like = f"%{search_value}%"
            query = query.filter(
                or_(
                    cast(Cell.id, String).ilike(like),
                    Cell.cellname.ilike(like),
                    Cell.technology.ilike(like),
                    Cell.frequency.ilike(like),
                    Antenna.model.ilike(like),
                    Sector.code_sector.ilike(like),
                )
            )

        records_filtered = query.count()

        order_map = {
            1: Cell.id,
            2: Cell.cellname,
            3: Cell.technology,
            4: Cell.frequency,
            5: Antenna.model,
            6: Sector.code_sector,
            7: Cell.tilt_mechanical,
            8: Cell.tilt_electrical,
        }
        order_expr = order_map.get(order_col, Cell.cellname)
        query = query.order_by(desc(order_expr) if order_dir == 'desc' else asc(order_expr))

        rows = query.offset(start).limit(length).all()

        data = []
        for cell in rows:
            data.append([
                '',  # Placeholder for checkbox column (DataTables col 0)
                str(cell.id),
                cell.cellname or '',
                cell.technology or '',
                cell.frequency or '',
                (cell.antenna.model if cell.antenna else 'N/A'),
                (cell.sector.code_sector if cell.sector else 'N/A'),
                '' if cell.tilt_mechanical is None else str(cell.tilt_mechanical),
                '' if cell.tilt_electrical is None else str(cell.tilt_electrical),
                _build_cell_tech_settings(cell),
            ])

        return jsonify({'draw': draw, 'recordsTotal': records_total, 'recordsFiltered': records_filtered, 'data': data})
    except Exception:
        logger.exception('Erreur cells_data')
        return jsonify({'draw': int(request.args.get('draw', 1)), 'recordsTotal': 0, 'recordsFiltered': 0, 'data': []}), 500


@list_bp.route('/wilayas')
@login_required
@admin_required
def view_wilayas():
    data = list_wilayas()
    column_keys = ['id', 'name', 'region_name']
    headers = ['Code Wilaya', 'Nom Wilaya', 'Région']
    
    rows = [[str(item.get(k) or '') for k in column_keys] for item in data]
    return render_template('tables/model_viewer.html', id_table='wilayasTable', 
                           titre='Wilayas', colonnes=headers, donnees=rows)

@list_bp.route('/communes')
@login_required
@admin_required
def view_communes():
    data = list_communes()
    column_keys = ['id', 'name', 'wilaya_name']
    headers = ['ID', 'Nom Commune', 'Wilaya']
    
    rows = [[str(item.get(k) or '') for k in column_keys] for item in data]
    return render_template('tables/model_viewer.html', id_table='communesTable', 
                           titre='Communes', colonnes=headers, donnees=rows)

@list_bp.route('/antennas')
@login_required
@admin_required
def view_antennas():
    items = Antenna.query.all()
    headers = ['id','Name','Frequency', 'Model', 'V-Tilt', 'H-Tilt', 'gain']
    rows = [[str(a.id),str(a.name), a.frequency, a.model, str(a.vbeamwidth), str(a.hbeamwidth), str(a.gain)] for a in items]
    
    return render_template('tables/model_viewer.html', id_table='antennasTable', 
                           titre='Antennas', colonnes=headers, donnees=rows)

@list_bp.route('/vendors')
@login_required
@admin_required
def view_vendors():
    items = Supplier.query.all()
    headers = ['ID', 'Nom du Vendor']
    rows = [[str(s.id), s.name] for s in items]
    
    return render_template('tables/model_viewer.html', id_table='vendorsTable', 
                           titre='Vendors', colonnes=headers, donnees=rows)

@list_bp.route('/regions')
@login_required
@admin_required
def view_regions():
    items = Region.query.all()
    headers = ['ID', 'Nom de la Région']
    rows = [[str(r.id), r.name] for r in items]
    
    return render_template('tables/model_viewer.html', id_table='regionsTable', 
                           titre='Regions', colonnes=headers, donnees=rows)
