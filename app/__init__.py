from flask import Flask

import app.config  # noqa: F401 — logging setup
from app.monitor import load_state, resume_monitoring
from app.routes import api_bp, client_bp


def create_app() -> Flask:
    application = Flask(__name__)
    application.register_blueprint(api_bp)
    application.register_blueprint(client_bp)
    load_state()
    resume_monitoring()
    return application
