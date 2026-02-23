from flask import Blueprint, request, redirect, url_for, flash
import pandas as pd 
import io 
from sqlalchemy import select 
from datetime import datetime
import numpy as np 
import logging
import traceback
from app.security import login_required, csrf_protect
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
    
    required_cols = [SITE_CODE_COL, SITE_NAME_COL, COMMUNE_ID_COL, SUPPLIER_NAME_COL, LATITUDE_COL, LONGITUDE_COL]
    FLOAT_COLS = [LATITUDE_COL, LONGITUDE_COL, ALTITUDE_COL, SUPPORT_HEIGHT_COL]
    
    try:
        # Compatibilite avec anciens fichiers qui utilisaient "laltitude"
        if LATITUDE_COL not in df.columns and ALT_LATITUDE_COL in df.columns:
            df[LATITUDE_COL] = df[ALT_LATITUDE_COL]

        # --- PRÉ-TRAITEMENT DES DONNÉES ---\n
        for col in FLOAT_COLS:
            if col in df.columns:
                 df[col] = df[col].apply(lambda x: parse_float_or_nan(x))
                 df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Nettoyage des lignes et gestion des doublons sur la clé unique SITE_CODE
        df_clean = df.dropna(subset=required_cols).drop_duplicates(subset=[SITE_CODE_COL])
        df_clean = df_clean.reset_index(drop=True)

    except Exception as e:
        error_msg = f"Erreur lors du pré-traitement des données de sites : {type(e).__name__}. Détails: {str(e)}"
        logger.exception("Erreur de pré-traitement (Site Import)")
        return (False, error_msg)

    # --- TRAITEMENT DB ---
    try:
        for idx, row in df_clean.iterrows():
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
                continue
                
            # 1. Vérification de la dépendance Commune par ID
            commune_obj = db.session.execute(select(Commune).filter_by(id=commune_id_value)).scalar_one_or_none() 
            if commune_obj is None:
                failed_dependencies += 1
                continue 
                
            # 2. Vérification de la dépendance Supplier par NAME
            supplier_obj = db.session.execute(select(Supplier).filter_by(name=supplier_name)).scalar_one_or_none()
            if supplier_obj is None:
                failed_dependencies += 1
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
            site_to_save.altitude = float(altitude_value) if pd.notna(altitude_value) else None
            site_to_save.support_nature = support_nature_value
            site_to_save.support_type = support_type_value
            site_to_save.support_height = float(support_height_value) if pd.notna(support_height_value) else None
            site_to_save.comments = comments_value
            site_to_save.supplier_id = supplier_id_value
                
        db.session.commit()
        
        # --- CRÉATION DU MESSAGE DE SUCCÈS ---
        ignored_lines = len(df) - len(df_clean) 
        ignored_total = ignored_lines + failed_dependencies + row_errors
        
        msg = (f"Importation des sites réussie : {added} ajoutés, "
               f"{updated} mis à jour (par site_code). "
               f"Total ignoré : {ignored_total} ({failed_dependencies} dépendances manquantes)."
        )
        return (True, msg)
        
    except Exception as e:
        db.session.rollback()
        logger.exception("Erreur DB complète (Site Import)")
        error_msg = f"Erreur fatale lors de l'importation des sites : {type(e).__name__}. Détails: {str(e)}"
        return (False, error_msg)

def import_sectors(df):
    # Colonnes du fichier Excel/CSV
    SECTOR_CODE_COL = 'sectors'    
    SITE_CODE_COL = 'site'
    AZIMUTH_COL = 'Azimuth'
    HBA_COL = 'HBA'
    COMMENTS_COL = 'Comments'
    COVERAGE_GOAL_COL = 'Coverage Goal'
    
    added = 0
    updated = 0
    failed_dependencies = 0 
    row_errors = 0 
    
    # Colonnes requises (non nulles dans le modèle ou pour les dépendances)
    required_cols = [SECTOR_CODE_COL, SITE_CODE_COL, AZIMUTH_COL, HBA_COL]
    
    try:
        # Nettoyage des lignes et gestion des doublons sur la clé unique SECTOR_CODE
        df_clean = df.dropna(subset=required_cols).drop_duplicates(subset=[SECTOR_CODE_COL])
        df_clean = df_clean.reset_index(drop=True)
        ignored_preprocessing = len(df) - len(df_clean)

    except Exception as e:
        error_msg = f"Erreur lors du pré-traitement des données de secteurs : {type(e).__name__}. Détails: {str(e)}"
        logger.exception("Erreur de pré-traitement (Sector Import)")
        return (False, error_msg)

    try:
        for idx, row in df_clean.iterrows():
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
                continue
            
            # 1. Vérification de la dépendance Site par CODE (Site.code_site)
            site_obj = db.session.execute(select(Site).filter_by(code_site=site_code)).scalar_one_or_none() 
            if site_obj is None:
                logger.warning("Secteur ignoré: code=%s site=%s", sector_code, site_code)
                failed_dependencies += 1
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
        ignored_total = ignored_preprocessing + failed_dependencies + row_errors
        
        msg = (f"Importation des secteurs réussie : {added} ajoutés, "
               f"{updated} mis à jour (par code de secteur). "
               f"Total ignoré : {ignored_total} ({failed_dependencies} dépendances Site manquantes)."
        )
        return (True, msg)
        
    except Exception as e:
        db.session.rollback()
        logger.exception("Erreur DB complète (Sector Import)")
        error_msg = f"Erreur fatale lors de l'importation des secteurs : {type(e).__name__}. Détails: {str(e)}"
        return (False, error_msg)

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
        "antenna_tech": "ANTENNA_TECH",
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


def import_cells(df):
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
    validation_errors = []

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

    try:
        # 1) Preprocess the dataframe and validate mandatory key columns.
        df = _normalize_cell_columns(df)
        if TILT_MECH_COL in df.columns:
            df[TILT_MECH_COL] = pd.to_numeric(df[TILT_MECH_COL], errors="coerce")
        if TILT_ELEC_COL in df.columns:
            df[TILT_ELEC_COL] = pd.to_numeric(df[TILT_ELEC_COL], errors="coerce")

        if CELLNAME_COL not in df.columns:
            return (False, "CELLNAME column is required for cell import.")

        df_clean = df.dropna(subset=[CELLNAME_COL]).drop_duplicates(subset=[CELLNAME_COL])
        df_clean = df_clean.reset_index(drop=True)
        ignored_preprocessing = len(df) - len(df_clean)
    except Exception as e:
        return (False, f"Erreur pre-traitement: {str(e)}")

    try:
        # 2) Upsert cells and populate technology-specific profile tables.
        for _, row in df_clean.iterrows():
            cellname = get_text(row, CELLNAME_COL)
            if not cellname:
                continue

            existing_cell = Cell.query.filter_by(cellname=cellname).first()
            if existing_cell:
                cell = existing_cell
                updated += 1
            else:
                cell = Cell(cellname=cellname)
                db.session.add(cell)
                added += 1

            incoming_tech = get_text(row, TECHNOLOGY_COL)
            tech_norm = (incoming_tech or cell.technology or "").strip().upper()
            if not tech_norm:
                validation_errors.append({"Cell": cellname, "Issue": "Technology missing"})
                continue

            previous_tech = (cell.technology or "").strip().upper()
            tech_changed = bool(previous_tech and previous_tech != tech_norm)
            cell.technology = tech_norm

            freq = get_text(row, FREQUENCY_COL)
            if freq is not None:
                cell.frequency = freq

            antenna_tech = get_text(row, ANTENNA_TECH_COL)
            if antenna_tech is not None:
                cell.antenna_tech = antenna_tech

            if TILT_MECH_COL in row and pd.notna(row.get(TILT_MECH_COL)):
                cell.tilt_mechanical = row.get(TILT_MECH_COL)
            if TILT_ELEC_COL in row and pd.notna(row.get(TILT_ELEC_COL)):
                cell.tilt_electrical = row.get(TILT_ELEC_COL)

            ant_model = get_text(row, ANTENNA_MODEL_COL)
            if ant_model:
                ant_obj = db.session.query(Antenna).filter_by(model=ant_model).first()
                if ant_obj:
                    cell.antenna_id = ant_obj.id
                else:
                    failed_antenna_dependencies += 1
                    validation_errors.append({"Cell": cellname, "Issue": f"Antenna {ant_model} not found"})

            if cell.frequency:
                # Resolve Sector from mapping rules (cell suffix + tech + band).
                sector_id_value, _ = resolve_sector_id_for_cell(cellname, tech_norm, str(cell.frequency))
                if sector_id_value is not None:
                    cell.sector_id = sector_id_value
                else:
                    failed_sector_resolutions += 1
                    validation_errors.append({"Cell": cellname, "Issue": "Sector resolution failed"})

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
                if has_value(row, "BSC"): p.bsc = get_text(row, "BSC")
                if has_value(row, "LAC"): p.lac = get_text(row, "LAC")
                if has_value(row, "RAC"): p.rac = get_text(row, "RAC")
                if has_value(row, "BCCH"): p.bcch = to_int_or_none(row.get("BCCH"))
                if has_value(row, "BSIC"): p.bsic = get_text(row, "BSIC")
            elif tech_norm == "3G":
                if not cell.profile_3g:
                    cell.profile_3g = Cell3G()
                p = cell.profile_3g
                if has_value(row, "RNC"): p.rnc = get_text(row, "RNC")
                if has_value(row, "LAC"): p.lac = get_text(row, "LAC")
                if has_value(row, "RAC"): p.rac = get_text(row, "RAC")
                if has_value(row, "PSC"): p.psc = to_int_or_none(row.get("PSC"))
                if has_value(row, "DLARFCN"): p.dlarfcn = get_text(row, "DLARFCN")
            elif tech_norm == "4G":
                if not cell.profile_4g:
                    cell.profile_4g = Cell4G()
                p = cell.profile_4g
                if has_value(row, "ENODEB"): p.enodeb = get_text(row, "ENODEB")
                if has_value(row, "TAC"): p.tac = get_text(row, "TAC")
                if has_value(row, "RSI"): p.rsi = get_text(row, "RSI")
                if has_value(row, "PCI"): p.pci = to_int_or_none(row.get("PCI"))
                if has_value(row, "EARFCN"): p.earfcn = get_text(row, "EARFCN")
            elif tech_norm == "5G":
                if not cell.profile_5g:
                    cell.profile_5g = Cell5G()
                p = cell.profile_5g
                if has_value(row, "GNODEB"): p.gnodeb = get_text(row, "GNODEB")
                if has_value(row, "LAC"): p.lac = get_text(row, "LAC")
                if has_value(row, "RSI"): p.rsi = get_text(row, "RSI")
                if has_value(row, "PCI"): p.pci = to_int_or_none(row.get("PCI"))
                if has_value(row, "ARFCN"): p.arfcn = get_text(row, "ARFCN")

        db.session.commit()

        if validation_errors:
            # Export non-blocking errors for post-import review.
            pd.DataFrame(validation_errors).to_excel(
                f"validation_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                index=False,
            )

        return (
            True,
            f"Cells import done: {added} added, {updated} updated, "
            f"{failed_antenna_dependencies} antenna misses, {failed_sector_resolutions} sector misses, "
            f"{ignored_preprocessing} rows ignored.",
        )
    except Exception as e:
        db.session.rollback()
        return (False, f"Erreur DB: {str(e)}")

# ====================================================================
# Fonction de Traitement de Fichier Générique 
# ====================================================================

def process_file_data(file, entity):
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
                    return (False, "Workbook is empty.")
                frames = []
                for sheet_name, sheet_df in workbook.items():
                    if sheet_df is None or sheet_df.empty:
                        continue
                    local_df = _normalize_cell_columns(sheet_df.copy())
                    inferred_tech = _infer_tech_from_sheet_name(sheet_name)
                    if inferred_tech and "TECHNOLOGY" not in local_df.columns:
                        local_df["TECHNOLOGY"] = inferred_tech
                    elif inferred_tech and "TECHNOLOGY" in local_df.columns:
                        local_df["TECHNOLOGY"] = local_df["TECHNOLOGY"].replace("", np.nan).fillna(inferred_tech)
                    frames.append(local_df)
                if not frames:
                    return (False, "No usable rows found in workbook sheets.")
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
            return (False, error_msg)

        # Dispatch vers la fonction d'importation appropriée
        if entity == 'regions':
            return import_regions(df)
        elif entity == 'wilayas':
            return import_wilayas(df)
        elif entity == 'communes':
            return import_communes(df)
        elif entity == 'antennas':
            return import_antennas(df)
        elif entity == 'sites':
            return import_sites(df)
        elif entity in ('suppliers', 'supplier', 'vendors', 'vendor'):
            return import_suppliers(df)
        elif entity == 'sectors':
            return import_sectors(df)
        elif entity == 'mapping':
            return import_mapping(df)
        elif entity == 'cells': # Nouvelle Entité
            return import_cells(df)
        
        else:
            error_msg = f"Entité non reconnue pour l'import: {entity}"
            logger.error("Erreur de traitement pour %s: %s", entity, error_msg)
            return (False, error_msg)

    except Exception as e:
        error_msg = f'Erreur de traitement du fichier pour l\'entité "{entity.upper()}". Détails: {str(e)}'
        logger.error("Erreur de traitement pour %s: %s", entity, error_msg)
        return (False, error_msg)


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

@import_bp.route('/data/<entity>', methods=['POST'])
@login_required
@csrf_protect
def import_data(entity):
    # 1. Normalize the entity name
    # This handles the case where the entity comes as "cellules_réseau" from the UI
    raw_entity = entity.lower().strip()
    
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
        flash('Aucun fichier soumis.', 'danger')
        return redirect(url_for('main.import_export')) 

    file = request.files['file']
    
    if file.filename == '':
        flash('Veuillez sélectionner un fichier à importer.', 'warning')
        return redirect(url_for('main.import_export'))

    if file:
        # Pass the logic name (e.g., 'cells') to the processor
        success, message = process_file_data(file, target_logic_entity)
        
        if success:
            flash(message, 'success')
            # 2. SUCCESS REDIRECTION: Go to the list view table
            endpoint = redirect_mapping.get(target_logic_entity)
            if endpoint:
                return redirect(url_for(endpoint))
            return redirect(url_for('main.import_export'))
        else:
            flash(message, 'danger')
            # 3. FAILURE REDIRECTION: Stay on the same page to see the error
            return redirect(request.referrer or url_for('main.import_export'))

    return redirect(url_for('main.import_export'))
