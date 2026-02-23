from app import db
from app.models import Site
from sqlalchemy import inspect
 
 # 1. Créer l'inspecteur à partir du moteur de la DB
inspector = inspect(db.engine)
table_name = Site.__tablename__ # Récupère le nom de table (généralement 'site')
 
print(f"--- Colonnes de la table '{table_name}' dans la DB ---")
try:
     # 2. Utiliser l'inspecteur pour obtenir les colonnes de la table
     columns = inspector.get_columns(table_name)
     
     for column in columns:
         # Note: 'unique' n'est pas toujours exposé par get_columns, 
         # mais l'existence et le nom/type sont cruciaux.
         print(f"{column['name']:<20} | {column['type']} | nullable={column['nullable']}")
 
except Exception as e:
     print(f"Erreur : La table '{table_name}' n'existe probablement pas ou : {e}")
