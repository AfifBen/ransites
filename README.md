+# RANSites
+
+RANSites is a web platform for RAN data governance and planning.  
+It centralizes telecom radio data (Sites, Sectors, Cells, Mapping), improves data quality, and provides operational exports (Allplan, KML) with role-based access control.
+
+## Overview
+
+RAN teams often work with fragmented spreadsheets and manual consolidations.  
+RANSites provides a single source of truth to:
+
+- manage site/sector/cell inventory
+- enforce consistent import templates
+- validate mapping and technical data quality
+- generate planning outputs (Allplan, KML)
+- control data visibility by geography (Wilaya/Commune/Site)
+
+## Key Features
+
+- Unified data model: `Sites`, `Sectors`, `Cells`, `Mapping`, `Antennas`, `Suppliers`, geo references
+- Role-based authentication and scoped access (admin/engineer)
+- Dynamic Add/Edit forms with validations
+- Import/Export workspace with downloadable templates
+- Allplan export workflow
+- KML export for sites and sectors (with sector beams)
+- Site Profile modal:
+  - site technical details
+  - technology badges and KPI cards
+  - nearest 5 sites with distance
+  - interactive map with adjacent links and sector beams
+- Dashboard for operational visibility and data quality indicators
+
+## Tech Stack
+
+- Backend: Flask, SQLAlchemy, Flask-Migrate, Flask-Login
+- Frontend: Jinja2, Bootstrap 5, DataTables, Leaflet
+- Data: SQLite (default)
+- Automation scripts: Python (`scripts/`)
+
+## Project Structure
+
+```text
+app/
+  routes/        # business endpoints (auth, import, list, main, etc.)
+  templates/     # Jinja templates and UI components
+  static/        # CSS, JS, i18n, assets
+  models.py      # SQLAlchemy models
+migrations/      # Alembic migrations
+scripts/         # utilities (screenshots, ppt generation)
+instance/        # local runtime DB (ignored in git)
+```
+
+## Getting Started
+
+### 1. Create and activate virtual environment
+
+```bash
+python -m venv venv
+venv\Scripts\activate
+```
+
+### 2. Install dependencies
+
+```bash
+pip install -r requirements.txt
+```
+
+If `requirements.txt` is not present yet, install core packages:
+
+```bash
+pip install flask flask-sqlalchemy flask-migrate flask-login python-dotenv pandas openpyxl
+```
+
+### 3. Configure environment
+
+Create `.env` with at least:
+
+```env
+FLASK_APP=run.py
+SECRET_KEY=change-me
+DATABASE_URL=sqlite:///radio.db
+```
+
+### 4. Database migration
+
+```bash
+flask db upgrade
+```
+
+### 5. Create admin user
+
+```bash
+flask create-user --username admin --admin
+```
+
+### 6. Run
+
+```bash
+python run.py
+```
+
+Then open: `http://127.0.0.1:5000`
+
+## Operational Notes
+
+- Import templates are available in **Data Import / Export**.
+- `cells` import supports multi-sheet Excel workbooks (2G/3G/4G/5G).
+- Validation issues are exported as `validation_*.xlsx` when needed.
+- Local DB and generated outputs are excluded from Git tracking.
+
+## Roadmap
+
+- V1 (current): RAN data governance + planning operations
+- V2 (target): full site lifecycle workflow from **D1 to On Air** with cross-department interaction:
+  - RAN
+  - Acquisition
+  - Construction
+
+## License
+
+Internal project (update as needed for your organization policy).
+
