import os
import unittest

from flask_login import login_user, logout_user

from app import create_app, db
from app.models import Region, Wilaya, Commune, Site, User
from app.security import get_accessible_commune_ids, get_accessible_site_ids


class ScopeAccessTests(unittest.TestCase):
    def setUp(self):
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        self.app = create_app()
        self.app.config["TESTING"] = True
        with self.app.app_context():
            db.create_all()
            self._seed_data()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def _seed_data(self):
        # Regions and wilayas
        east = Region(name="east")
        west = Region(name="west")
        db.session.add_all([east, west])
        db.session.flush()

        mila = Wilaya(id=43, name="MILA", region_id=east.id)
        msila = Wilaya(id=28, name="MSILA", region_id=east.id)
        khenchela = Wilaya(id=40, name="KHENCHELA", region_id=east.id)
        oran = Wilaya(id=31, name="ORAN", region_id=west.id)
        db.session.add_all([mila, msila, khenchela, oran])
        db.session.flush()

        # Communes
        c_mila = Commune(id=4301, name="MILA", wilaya_id=mila.id)
        c_msila = Commune(id=2801, name="MSILA", wilaya_id=msila.id)
        c_khenchela = Commune(id=4001, name="KHENCHELA", wilaya_id=khenchela.id)
        c_oran = Commune(id=3101, name="ORAN", wilaya_id=oran.id)
        db.session.add_all([c_mila, c_msila, c_khenchela, c_oran])
        db.session.flush()

        # Sites
        s1 = Site(code_site="C43MILA001", name="Mila Site", commune_id=c_mila.id, latitude=35.0, longitude=6.0)
        s2 = Site(code_site="C28MSILA001", name="Msila Site", commune_id=c_msila.id, latitude=35.7, longitude=4.5)
        s3 = Site(code_site="C40KHEN001", name="Khenchela Site", commune_id=c_khenchela.id, latitude=35.4, longitude=7.1)
        s4 = Site(code_site="C31ORAN001", name="Oran Site", commune_id=c_oran.id, latitude=35.7, longitude=-0.6)
        db.session.add_all([s1, s2, s3, s4])

        # Users
        admin = User(username="admin", is_admin=True, is_active=True)
        admin.set_password("adminpass")
        eng = User(username="eng", is_admin=False, is_active=True)
        eng.set_password("pass1234")

        eng.assigned_wilayas = [mila, msila, khenchela]
        eng.assigned_regions = [east]
        db.session.add_all([admin, eng])
        db.session.commit()

        self.admin_id = admin.id
        self.eng_id = eng.id

    def _login(self, user_id):
        app_ctx = self.app.app_context()
        app_ctx.push()
        user = db.session.get(User, user_id)
        req_ctx = self.app.test_request_context("/")
        req_ctx.push()
        login_user(user)
        return app_ctx, req_ctx

    def test_admin_sees_all_sites(self):
        app_ctx, req_ctx = self._login(self.admin_id)
        try:
            accessible = get_accessible_site_ids()
            self.assertIsNone(accessible)
        finally:
            logout_user()
            req_ctx.pop()
            app_ctx.pop()

    def test_engineer_scope_wilaya_only(self):
        app_ctx, req_ctx = self._login(self.eng_id)
        try:
            accessible = get_accessible_site_ids()
            self.assertIsNotNone(accessible)
            # Should include Mila/Msila/Khenchela sites, but not Oran.
            site_codes = {s.code_site for s in Site.query.filter(Site.id.in_(list(accessible))).all()}
            self.assertIn("C43MILA001", site_codes)
            self.assertIn("C28MSILA001", site_codes)
            self.assertIn("C40KHEN001", site_codes)
            self.assertNotIn("C31ORAN001", site_codes)
        finally:
            logout_user()
            req_ctx.pop()
            app_ctx.pop()

    def test_commune_ids_follow_wilaya_scope(self):
        app_ctx, req_ctx = self._login(self.eng_id)
        try:
            commune_ids = get_accessible_commune_ids()
            self.assertIsNotNone(commune_ids)
            self.assertIn(4301, commune_ids)
            self.assertIn(2801, commune_ids)
            self.assertIn(4001, commune_ids)
            self.assertNotIn(3101, commune_ids)
        finally:
            logout_user()
            req_ctx.pop()
            app_ctx.pop()


if __name__ == "__main__":
    unittest.main()
