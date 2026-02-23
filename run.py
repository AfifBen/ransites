# radio_manager/run.py

import os
from dotenv import load_dotenv

# Charge les variables d'environnement (comme FLASK_APP)
load_dotenv() 

# Importe la fonction d'usine de l'application
from app import create_app, db
from app.models import Site, Sector, Cell, Supplier, Commune, Wilaya, Region, Antenna, Mapping, User # Optionnel, pour le shell

# Crée l'application
app = create_app()

# Permet d'utiliser 'flask shell' avec les modèles pré-chargés
@app.shell_context_processor
def make_shell_context():
    # Ajoutez tous vos modèles ici pour les tests rapides dans la console
    return {
        'db': db, 
        'Site': Site, 
        'Sector': Sector, 
        'Cell': Cell, 
        'Supplier': Supplier,
        'Commune': Commune,
        'Wilaya': Wilaya,
        'Region': Region,
        'Antenna': Antenna,
        'Mapping': Mapping,
        'User': User
    }

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', '0').lower() in ('1', 'true', 'yes', 'on')
    app.run(debug=debug_mode)
