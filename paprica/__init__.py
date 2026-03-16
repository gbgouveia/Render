import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth

load_dotenv()

app = Flask(__name__)

# ==============================
# DATABASE
# ==============================

database_url = os.environ.get("DATABASE_URL")

if not database_url:
    raise RuntimeError("DATABASE_URL não foi definida no ambiente.")

# Corrige prefixo antigo
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ==============================
# SECRET KEY
# ==============================

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "chave-dev-apenas-local")

# ==============================
# UPLOADS
# ==============================

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ==============================
# EXTENSIONS
# ==============================

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "page_login"

oauth = OAuth(app)

# ==============================
# GOOGLE LOGIN
# ==============================

oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# ==============================
# LOGIN MANAGER
# ==============================

from paprica.models import User

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==============================
# BLUEPRINTS
# ==============================

from paprica.admin_rotes import admin
app.register_blueprint(admin)

from paprica import routes