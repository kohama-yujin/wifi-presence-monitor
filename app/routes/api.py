import hmac
from functools import wraps

from flask import Blueprint, jsonify, request

from app.config import load_api_key, load_public_tunnel_url
from app.monitor import (
    get_history,
    get_status,
    list_history_dates,
    start_monitoring,
    stop_monitoring,
)

api_bp = Blueprint("api", __name__)


def _extract_api_key(data: dict | None) -> str | None:
    """JSON 本文・ヘッダから API キーを取り出す。"""
    if data and isinstance(data.get("api_key"), str) and data["api_key"].strip():
        return data["api_key"].strip()

    header = request.headers.get("X-Api-Key")
    if header and header.strip():
        return header.strip()

    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return token
    return None


def require_api_key(view):
    """POST 用: 共有 API キーを検証する。"""

    @wraps(view)
    def wrapped(*args, **kwargs):
        expected = load_api_key()
        if not expected:
            return jsonify({
                "ok": False,
                "error": True,
                "message": "api_key.json が未設定です（api_key.example.json をコピーして設定）",
            }), 503

        data = request.get_json(silent=True)
        provided = _extract_api_key(data if isinstance(data, dict) else None)
        if (
            not provided
            or len(provided) != len(expected)
            or not hmac.compare_digest(provided, expected)
        ):
            return jsonify({
                "ok": False,
                "error": True,
                "message": "APIキーが無効です",
            }), 401
        return view(*args, **kwargs)

    return wrapped


@api_bp.get("/health")
def health():
    return "running"


@api_bp.get("/status")
def status():
    return jsonify(get_status())


@api_bp.get("/history/dates")
def history_dates():
    return jsonify({"dates": list_history_dates()})


@api_bp.get("/history/<day>")
def history_day(day: str):
    data = get_history(day)
    if data is None:
        return jsonify({
            "ok": False,
            "error": True,
            "message": "指定日の記録がありません（当日は履歴対象外です）",
        }), 404
    return jsonify(data)


@api_bp.post("/wifi_connected")
@require_api_key
def wifi_connected():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    grade = data.get("grade")

    if not name or not grade:
        return jsonify({
            "ok": False,
            "error": True,
            "message": "name と grade は必須です",
        }), 400

    result = start_monitoring(name, grade)
    if result == "full":
        return jsonify({
            "ok": False,
            "error": True,
            "message": "同時接続数の上限に達しています",
            "public_url": load_public_tunnel_url(),
        }), 429
    return jsonify({
        "ok": True,
        "message": "受け付けました",
        "public_url": load_public_tunnel_url(),
    }), 200


@api_bp.post("/wifi_disconnected")
@require_api_key
def wifi_disconnected():
    """Wi‑Fi 切断時の不在トリガー。"""
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    grade = data.get("grade")

    if not name or not grade:
        return jsonify({
            "ok": False,
            "error": True,
            "message": "name と grade は必須です",
        }), 400

    result = stop_monitoring(name, grade)
    if result == "missing":
        return jsonify({
            "ok": True,
            "ignored": True,
            "message": "当日の在室記録が見つかりません",
        }), 200
    if result == "already_absent":
        return jsonify({
            "ok": True,
            "ignored": True,
            "message": "すでに不在です",
        }), 200
    return jsonify({
        "ok": True,
        "message": "不在にしました",
    }), 200


@api_bp.post("/test_post")
@require_api_key
def test_post():
    """トンネル／ショートカット確認用。在室登録はしない。"""
    data = request.get_json(silent=True)
    return jsonify({
        "ok": True,
        "message": "POSTを受け取りました（テスト）",
        "remote_addr": request.remote_addr,
        "json": data,
    }), 200
