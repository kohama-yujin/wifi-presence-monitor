import json
import logging
from pathlib import Path

CHECK_INTERVAL_SECONDS = 300
PRESENCE_CREDIT_SECONDS = 300
ARP_TIMEOUT_SECONDS = 2
MISS_THRESHOLD_COUNT = 2
MAX_TARGETS = 20
# 除外 MAC 通知時に案内するルーター名
ROUTER_NAME = "C3-503"

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_MACS_FILE = ROOT / "excluded_macs.json"
# 日付ごとの在室状態を蓄積するフォルダ
STATE_DIR = ROOT / "data" / "presence"
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
