# radio_manager/app/models.py
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db

user_wilaya = db.Table(
    "user_wilaya",
    db.Column("user_id", db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    db.Column("wilaya_id", db.Integer, db.ForeignKey("wilaya.id", ondelete="CASCADE"), primary_key=True),
)

user_commune = db.Table(
    "user_commune",
    db.Column("user_id", db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    db.Column("commune_id", db.Integer, db.ForeignKey("commune.id", ondelete="CASCADE"), primary_key=True),
)

user_site = db.Table(
    "user_site",
    db.Column("user_id", db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    db.Column("site_id", db.Integer, db.ForeignKey("site.id", ondelete="CASCADE"), primary_key=True),
)


class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    assigned_wilayas = db.relationship(
        "Wilaya",
        secondary=user_wilaya,
        lazy="select",
        backref=db.backref("assigned_users", lazy="dynamic"),
    )
    assigned_communes = db.relationship(
        "Commune",
        secondary=user_commune,
        lazy="select",
        backref=db.backref("assigned_users", lazy="dynamic"),
    )
    assigned_sites = db.relationship(
        "Site",
        secondary=user_site,
        lazy="select",
        backref=db.backref("assigned_users", lazy="dynamic"),
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin_user(self):
        return bool(self.is_admin or self.username.lower() == "admin")

# --- Localisation ---
class Region(db.Model):
    __tablename__ = 'region'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    wilayas = db.relationship('Wilaya', backref='region', cascade="all, delete-orphan", lazy=True)

class Wilaya(db.Model):
    __tablename__ = 'wilaya'
    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    name = db.Column(db.String(100), unique=True, nullable=False)
    region_id = db.Column(db.Integer, db.ForeignKey('region.id', ondelete='CASCADE'), nullable=False)
    communes = db.relationship('Commune', backref='wilaya', cascade="all, delete-orphan", lazy=True)

class Commune(db.Model):
    __tablename__ = 'commune'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    wilaya_id = db.Column(db.Integer, db.ForeignKey('wilaya.id', ondelete='CASCADE'), nullable=False)
    sites = db.relationship('Site', backref='commune', cascade="all, delete-orphan", lazy='dynamic')

# --- Fournisseur ---
class Supplier(db.Model):
    __tablename__ = 'supplier'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    sites = db.relationship('Site', backref='supplier', lazy='dynamic')

# --- Antenne ---
class Antenna(db.Model):
    __tablename__ = 'antenna'
    id = db.Column(db.Integer, primary_key=True)
    supplier = db.Column(db.String(100), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=True)
    port = db.Column(db.Integer, nullable=True)
    frequency = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(50), nullable=True)
    hbeamwidth = db.Column(db.Float, nullable=False)
    vbeamwidth = db.Column(db.Float, nullable=False)
    gain = db.Column(db.Float, nullable=False)
    cells = db.relationship('Cell', backref='antenna', lazy='dynamic')

# --- Site ---
class Site(db.Model):
    __tablename__ = 'site' # CHANGÉ ICI : 'sites' -> 'site'
    id = db.Column(db.Integer, primary_key=True)
    code_site = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    altitude = db.Column(db.Float, nullable=True)
    support_nature = db.Column(db.String(50), nullable=True)
    support_type = db.Column(db.String(50), nullable=True)
    support_height = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="On air", server_default="On air")
    comments = db.Column(db.Text, nullable=True)
    
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=True)
    commune_id = db.Column(db.Integer, db.ForeignKey('commune.id', ondelete='CASCADE'), nullable=False)
    
    sectors = db.relationship('Sector', backref='site', cascade="all, delete-orphan", lazy='dynamic')

# --- Sector ---
class Sector(db.Model):
    __tablename__ = 'sector'
    id = db.Column(db.Integer, primary_key=True)
    code_sector = db.Column(db.String(80), unique=True, nullable=False)
    azimuth = db.Column(db.Integer, nullable=False)
    hba = db.Column(db.Integer, nullable=False)
    coverage_goal = db.Column(db.String(50), nullable=True)
    
    site_id = db.Column(db.Integer, db.ForeignKey('site.id', ondelete='CASCADE'), nullable=False)
    cells = db.relationship('Cell', backref='sector', cascade="all, delete-orphan", lazy='dynamic')

# --- Cell ---
class Cell(db.Model):
    __tablename__ = 'cell'
    id = db.Column(db.Integer, primary_key=True)
    cellname = db.Column(db.String(150), unique=True, nullable=False)
    technology = db.Column(db.String(20), nullable=False)
    frequency = db.Column(db.String(50), nullable=True)
    antenna_tech = db.Column(db.String(50), nullable=True)
    tilt_mechanical = db.Column(db.Float, nullable=True)
    tilt_electrical = db.Column(db.Float, nullable=True)
    
    antenna_id = db.Column(db.Integer, db.ForeignKey('antenna.id'), nullable=True)
    sector_id = db.Column(db.Integer, db.ForeignKey('sector.id', ondelete='CASCADE'), nullable=True)
    profile_2g = db.relationship('Cell2G', back_populates='cell', uselist=False, cascade='all, delete-orphan')
    profile_3g = db.relationship('Cell3G', back_populates='cell', uselist=False, cascade='all, delete-orphan')
    profile_4g = db.relationship('Cell4G', back_populates='cell', uselist=False, cascade='all, delete-orphan')
    profile_5g = db.relationship('Cell5G', back_populates='cell', uselist=False, cascade='all, delete-orphan')


class Cell2G(db.Model):
    __tablename__ = 'cell_2g'
    id = db.Column(db.Integer, primary_key=True)
    cell_id = db.Column(db.Integer, db.ForeignKey('cell.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    bsc = db.Column(db.String(80), nullable=True)
    lac = db.Column(db.String(50), nullable=True)
    rac = db.Column(db.String(50), nullable=True)
    bcch = db.Column(db.Integer, nullable=True)
    bsic = db.Column(db.String(20), nullable=True)

    cell = db.relationship('Cell', back_populates='profile_2g')


class Cell3G(db.Model):
    __tablename__ = 'cell_3g'
    id = db.Column(db.Integer, primary_key=True)
    cell_id = db.Column(db.Integer, db.ForeignKey('cell.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    lac = db.Column(db.String(50), nullable=True)
    rac = db.Column(db.String(50), nullable=True)
    psc = db.Column(db.Integer, nullable=True)
    rnc = db.Column(db.String(80), nullable=True)
    dlarfcn = db.Column(db.String(50), nullable=True)

    cell = db.relationship('Cell', back_populates='profile_3g')


class Cell4G(db.Model):
    __tablename__ = 'cell_4g'
    id = db.Column(db.Integer, primary_key=True)
    cell_id = db.Column(db.Integer, db.ForeignKey('cell.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    enodeb = db.Column(db.String(80), nullable=True)
    tac = db.Column(db.String(50), nullable=True)
    rsi = db.Column(db.String(50), nullable=True)
    pci = db.Column(db.Integer, nullable=True)
    earfcn = db.Column(db.String(50), nullable=True)

    cell = db.relationship('Cell', back_populates='profile_4g')


class Cell5G(db.Model):
    __tablename__ = 'cell_5g'
    id = db.Column(db.Integer, primary_key=True)
    cell_id = db.Column(db.Integer, db.ForeignKey('cell.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    gnodeb = db.Column(db.String(80), nullable=True)
    lac = db.Column(db.String(50), nullable=True)
    rsi = db.Column(db.String(50), nullable=True)
    pci = db.Column(db.Integer, nullable=True)
    arfcn = db.Column(db.String(50), nullable=True)

    cell = db.relationship('Cell', back_populates='profile_5g')

# --- Mapping ---
class Mapping(db.Model):
    __tablename__ = 'mapping'
    id = db.Column(db.Integer, primary_key=True)
    map_id = db.Column(db.String(100), unique=True, nullable=False)
    cell_code = db.Column(db.String(50), nullable=False)
    antenna_tech = db.Column(db.String(50), nullable=False)
    band = db.Column(db.String(50), nullable=False)
    sector_code = db.Column(db.String(50), nullable=False)
    technology = db.Column(db.String(20), nullable=False)
