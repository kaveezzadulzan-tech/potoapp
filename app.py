from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os

db = SQLAlchemy()

# ── Build the app at module level so gunicorn can find it as app:app ──────────
app = Flask(__name__)
CORS(app)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fieldcam-dev-secret')

# Render gives DATABASE_URL starting with postgres:// — SQLAlchemy needs postgresql://
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///fieldcam.db')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

db.init_app(app)

from routes import register_routes   # noqa: E402 — must come after db init
register_routes(app)

with app.app_context():
    db.create_all()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=True, host='0.0.0.0', port=port)
