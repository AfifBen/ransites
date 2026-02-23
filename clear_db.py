# Fichier: clear_db.py

# ====================================================================
# Ajuster les imports
# ====================================================================
# Exemple:
from app import create_app
from app.models import db 
from app.models import (
    Cell, Sector, Site, 
    Commune, Wilaya, Region, 
    Supplier, Antenna, Mapping
)
# ====================================================================

# Définition de l'ordre de SUPPRESSION (inverse des dépendances)
TABLES_TO_CLEAR = [
    #Cell,           # Dépend de Sector, Antenna (À supprimer en premier)
    #Sector,         # Dépend de Site
    #Site,           # Dépend de Commune, Supplier
    Commune,        # Dépend de Wilaya
    Wilaya,         # Dépend de Region
   # Region,         # Indépendante
    #Supplier,       # Indépendante
    #Antenna,        # Indépendante
    #Mapping,        # Indépendante
]

# Initialisation de l'application Flask
app = create_app()

def clear_all_tables():
    """Vide toutes les tables de la base de données dans l'ordre inverse de dépendance."""
    
    print("="*50)
    print("🚀 Début du vidage des tables de la base de données...")
    print("="*50)
    
    with app.app_context():
        try:
            for Model in TABLES_TO_CLEAR:
                table_name = Model.__tablename__
                print(f"Effacement de la table '{table_name}'...")
                
                # Utilisation de db.session.query(Model).delete() pour une suppression rapide
                # synchronize_session='fetch' est utilisé pour s'assurer que les enregistrements sont bien supprimés
                # sans avoir à les charger en mémoire au préalable.
                rows_deleted = db.session.query(Model).delete(synchronize_session='fetch')
                print(f"   -> {rows_deleted} lignes effacées.")
                
            db.session.commit()
            print("\n" + "="*50)
            print("✅ Opération de vidage terminée et transaction validée avec succès.")
            print("="*50)
            
        except Exception as e:
            db.session.rollback()
            print("\n" + "="*50)
            print(f"❌ Erreur critique lors du vidage des tables. Transaction annulée : {e}")
            print("="*50)

if __name__ == '__main__':
    clear_all_tables()