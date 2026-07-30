from flask import Blueprint, jsonify, request

from app.config import ROUTER_NAME
from app.monitor import get_status, start_monitoring

api_bp = Blueprint("api", __name__)


@api_bp.get("/")
def index():
    return "running"


@api_bp.get("/status")
def status():
    return jsonify(get_status())


@api_bp.post("/wifi_connected")
def wifi_connected():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    grade = data.get("grade")
    mac = data.get("mac")

    if not name or not grade:
        return jsonify({
            "ok": False,
            "error": True,
            "message": "name と grade は必須です",
        }), 400

    result = start_monitoring(name, grade, request.remote_addr, mac)
    if result is False:
        return jsonify({
            "ok": True,
            "ignored": True,
            "message": f"{ROUTER_NAME}のルーターに接続してください",
        }), 200
    if result == "full":
        return jsonify({
            "ok": False,
            "error": True,
            "message": "同時接続数の上限に達しています",
        }), 429
    if result == "pending":
        return jsonify({
            "ok": True,
            "message": "確認中です",
        }), 200
    return jsonify({
        "ok": True,
        "message": "受け付けました",
    }), 200
