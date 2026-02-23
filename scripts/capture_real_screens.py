import threading
import time
import sys
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ASSETS = ROOT / 'presentation_assets'
ASSETS.mkdir(parents=True, exist_ok=True)


def ensure_presenter_user():
    from app import create_app, db
    from app.models import User

    app = create_app()
    with app.app_context():
        user = User.query.filter_by(username='presenter').first()
        if not user:
            user = User(username='presenter', is_admin=True, is_active=True)
            user.set_password('Ransites2026!')
            db.session.add(user)
            db.session.commit()
        else:
            user.is_active = True
            user.is_admin = True
            user.set_password('Ransites2026!')
            db.session.commit()


class ServerThread(threading.Thread):
    def __init__(self, app, host='127.0.0.1', port=5055):
        super().__init__(daemon=True)
        self.srv = make_server(host, port, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        self.srv.serve_forever()

    def shutdown(self):
        self.srv.shutdown()


def build_driver():
    options = webdriver.EdgeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--log-level=3')
    try:
        return webdriver.Edge(options=options)
    except Exception:
        copt = webdriver.ChromeOptions()
        copt.add_argument('--headless=new')
        copt.add_argument('--window-size=1920,1080')
        copt.add_argument('--disable-gpu')
        copt.add_argument('--log-level=3')
        return webdriver.Chrome(options=copt)


def login(driver, base_url):
    driver.get(base_url + '/login')
    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.NAME, 'username')))
    driver.find_element(By.NAME, 'username').clear()
    driver.find_element(By.NAME, 'username').send_keys('presenter')
    driver.find_element(By.NAME, 'password').clear()
    driver.find_element(By.NAME, 'password').send_keys('Ransites2026!')
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    wait.until(EC.url_contains('/dashboard'))


def shot(driver, path):
    driver.save_screenshot(str(path))


def capture():
    ensure_presenter_user()

    from app import create_app
    app = create_app()
    server = ServerThread(app)
    server.start()
    time.sleep(1.0)

    base = 'http://127.0.0.1:5055'
    driver = build_driver()
    wait = WebDriverWait(driver, 25)

    try:
        login(driver, base)

        driver.get(base + '/dashboard')
        wait.until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        time.sleep(1.2)
        shot(driver, ASSETS / 'real_dashboard.png')

        driver.get(base + '/sites')
        wait.until(EC.presence_of_element_located((By.ID, 'sitesTable')))
        time.sleep(1.8)
        shot(driver, ASSETS / 'real_sites_table.png')

        first_row_cb = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '#sitesTable tbody tr td .row-checkbox')))
        first_row_cb.click()
        time.sleep(0.6)
        profile_btn = wait.until(EC.element_to_be_clickable((By.ID, 'siteProfileBtn')))
        profile_btn.click()
        wait.until(EC.visibility_of_element_located((By.ID, 'siteProfileModal')))
        wait.until(EC.visibility_of_element_located((By.ID, 'siteProfileContent')))
        time.sleep(1.4)
        shot(driver, ASSETS / 'real_site_profile.png')

        driver.get(base + '/import_export')
        wait.until(EC.presence_of_element_located((By.TAG_NAME, 'form')))
        time.sleep(1.0)
        shot(driver, ASSETS / 'real_import_export.png')

        print('OK')
    finally:
        driver.quit()
        server.shutdown()


if __name__ == '__main__':
    capture()
