from pathlib import Path

from flask import Blueprint, send_from_directory

CLIENT_DIR = Path(__file__).resolve().parents[2] / "client"

client_bp = Blueprint("client", __name__)


@client_bp.get("/client")
@client_bp.get("/client/")
def client_page():
    return send_from_directory(CLIENT_DIR, "index.html")


@client_bp.get("/client/<path:filename>")
def client_assets(filename: str):
    return send_from_directory(CLIENT_DIR, filename)
