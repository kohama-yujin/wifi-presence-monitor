import json
import logging
from pathlib import Path

CHECK_INTERVAL_SECONDS = 60
MAX_TARGETS = 20

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_MACS_FILE = ROOT / "excluded_macs.json"
API_KEY_FILE = ROOT / "api_key.json"
# 日付ごとの在室状態を蓄積するフォルダ
STATE_DIR = ROOT / "data" / "presence"
# cloudflared Quick Tunnel の公開 URL（起動スクリプトが書き込む）
TUNNEL_URL_FILE = ROOT / "data" / "tunnel_url.txt"
# 到着チャイム（WAV が無ければ Windows の SystemAsterisk）
ARRIVAL_SOUND_ENABLED = True
ARRIVAL_SOUND_FILE = ROOT / "sounds" / "arrive.wav"

# 表示順（これ以外は other）
GRADE_ORDER = ["Teacher", "M2", "M1", "B4", "other"]
KNOWN_GRADES = {"Teacher", "M2", "M1", "B4"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def state_file_for(day: str) -> Path:
    return STATE_DIR / f"{day}.json"


def normalize_mac(mac: str) -> str:
    return mac.replace("-", ":").lower().strip()


def normalize_grade(grade: str | None) -> str:
    g = (grade or "").strip()
    if g.lower() == "teacher":
        return "Teacher"
    gu = g.upper()
    if gu in ("M2", "M1", "B4"):
        return gu
    return "other"


def load_excluded_macs() -> set[str]:
    """MACアドレスの除外リストを読み込む。"""
    if not EXCLUDED_MACS_FILE.exists():
        return set()
    with EXCLUDED_MACS_FILE.open(encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        raise ValueError("excluded_macs.json must be a JSON array of MAC strings")
    return {normalize_mac(m) for m in raw if m}


def is_excluded_mac(mac: str | None) -> bool:
    """指定したMACアドレスが除外リストに含まれているかどうかを返す。"""
    if not mac:
        return False
    return normalize_mac(mac) in load_excluded_macs()


def load_public_tunnel_url() -> str | None:
    """
    Quick Tunnel の公開 URL を data/tunnel_url.txt から読む。
    未作成・空・不正なら None。
    """
    if not TUNNEL_URL_FILE.exists():
        return None
    try:
        # PowerShell Set-Content -Encoding utf8 は BOM 付きのため utf-8-sig で読む
        text = TUNNEL_URL_FILE.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return None
    if not text:
        return None
    url = text.split()[0].strip()
    if not url.startswith("https://"):
        return None
    return url


def load_api_key() -> str | None:
    """
    共有 API キーを api_key.json から読み込む。
    未設定・空なら None。
    """
    if not API_KEY_FILE.exists():
        return None
    try:
        with API_KEY_FILE.open(encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    key = raw.get("api_key")
    if not isinstance(key, str):
        return None
    key = key.strip()
    return key or None
