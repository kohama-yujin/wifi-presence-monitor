import json
import logging
import threading
import time
from datetime import date, datetime

from app.arp import arp_request
from app.config import (
    CHECK_INTERVAL_SECONDS,
    GRADE_ORDER,
    MAX_TARGETS,
    MISS_THRESHOLD_COUNT,
    PRESENCE_CREDIT_SECONDS,
    STATE_DIR,
    is_excluded_mac,
    normalize_grade,
    normalize_mac,
    state_file_for,
)
from app.sound import play_arrival_sound

log = logging.getLogger("presence")

_lock = threading.Lock()
_targets: dict[str, dict] = {}
_day: str = date.today().isoformat()
_loop_started = False


def _now() -> datetime:
    return datetime.now().astimezone()


def _today() -> str:
    return date.today().isoformat()


def _make_key(ip: str, mac: str | None) -> str:
    if mac:
        return f"mac:{normalize_mac(mac)}"
    return f"ip:{ip}"


def _public(t: dict) -> dict:
    """監視状況を公開用に変換する。"""
    return {
        "name": t["name"],
        "grade": t["grade"],
        "ip": t["ip"],
        "mac": t["mac"],
        "present": t["present"],
        "monitoring": t["monitoring"],
        "misses": t["misses"],
        "arrived_at": t["arrived_at"],
        "left_at": t.get("left_at"),
        "total_present_seconds": t["total_present_seconds"],
    }


def _target_payload(t: dict) -> dict:
    """監視状態をファイルに保存するためのペイロードを作成する。"""
    return {
        "key": t["key"],
        "name": t["name"],
        "grade": t["grade"],
        "ip": t["ip"],
        "mac": t["mac"],
        "present": t["present"],
        "monitoring": t["monitoring"],
        "misses": t["misses"],
        "arrived_at": t["arrived_at"],
        "left_at": t.get("left_at"),
        "total_present_seconds": t["total_present_seconds"],
        "last_credit_at": t["last_credit_at"],
        "confirmed": bool(t.get("confirmed", True)),
    }


def _save_unlocked() -> None:
    """監視状態をファイルに保存する。"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = state_file_for(_day)
    payload = {
        "date": _day,
        "targets": {k: _target_payload(t) for k, t in _targets.items()},
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _mark_absent(current: dict, now: datetime, reason: str) -> None:
    """在室者から不在になったときの処理。"""
    if current["present"]:
        _credit_if_due(current, now)
        current["left_at"] = now.isoformat()
    current["present"] = False
    log.info("%s absent (%s)", current["name"], reason)


def _mark_present(current: dict, now: datetime) -> None:
    """在室者になったときの処理。"""
    current["present"] = True
    current["left_at"] = None  # 再接続・復帰時は帰宅をクリア
    current["misses"] = 0
    if not current.get("last_credit_at"):
        current["last_credit_at"] = now.isoformat()


def _reset_day_unlocked() -> None:
    """日付が変わったらメモリ上の当日枠だけ切り替える（過去日ファイルは残す）。"""
    global _day
    if _targets:
        _save_unlocked()
    _day = _today()
    _targets.clear()
    log.info("day rolled over -> %s (memory reset, history kept)", _day)
    _save_unlocked()


def _ensure_today_unlocked() -> None:
    """当日の状態を確認して、必要ならリセットする。"""
    if _day != _today():
        _reset_day_unlocked()


def _hydrate_target(key: str, t: dict) -> dict:
    """監視状態をメモリに復元する。"""
    return {
        "key": t.get("key") or key,
        "name": t.get("name") or "unknown",
        "grade": normalize_grade(t.get("grade")),
        "ip": t.get("ip"),
        "mac": t.get("mac"),
        "present": bool(t.get("present")),
        "monitoring": bool(t.get("monitoring", True)),
        "misses": int(t.get("misses") or 0),
        "arrived_at": t.get("arrived_at"),
        "left_at": t.get("left_at"),
        "total_present_seconds": int(t.get("total_present_seconds") or 0),
        "last_credit_at": t.get("last_credit_at"),
        "confirmed": bool(t.get("confirmed", True)),
    }


def load_state() -> None:
    """監視状態をファイルから読み込む。"""
    global _day
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    today = _today()
    path = state_file_for(today)

    # 旧ルートの presence_state.json があれば当日分として取り込む
    legacy = STATE_DIR.parent.parent / "presence_state.json"
    if not path.exists() and legacy.exists():
        try:
            raw = json.loads(legacy.read_text(encoding="utf-8"))
            if raw.get("date") == today:
                path.write_text(
                    json.dumps(raw, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                log.info("migrated legacy presence_state.json -> %s", path)
        except (OSError, json.JSONDecodeError):
            log.exception("failed to migrate legacy state")

    if not path.exists():
        _day = today
        return

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("failed to load %s", path)
        _day = today
        return

    with _lock:
        _day = today
        loaded = raw.get("targets") or {}
        _targets.clear()
        for key, t in loaded.items():
            _targets[key] = _hydrate_target(key, t)
    log.info("loaded %s targets from %s", len(_targets), path.name)


def get_status() -> dict:
    """
    監視状況を取得する。
    /status で返されるJSONの形式。
    """
    with _lock:
        _ensure_today_unlocked()
        targets = [
            _public(t)
            for t in _targets.values()
            if t.get("confirmed")
        ]
        # 当日の到着順
        targets.sort(key=lambda t: t["arrived_at"] or "")

    by_grade = {g: [] for g in GRADE_ORDER}
    for t in targets:
        grade = t["grade"] if t["grade"] in by_grade else "other"
        by_grade[grade].append(t)

    return {
        "date": _today(),
        "check_interval_seconds": CHECK_INTERVAL_SECONDS,
        "presence_credit_seconds": PRESENCE_CREDIT_SECONDS,
        "count": len(targets),
        "max_targets": MAX_TARGETS,
        "grades": GRADE_ORDER,
        "by_grade": by_grade,
        "targets": targets,
    }


def _ensure_loop() -> None:
    """監視ループを開始する。"""
    global _loop_started
    if _loop_started:
        return
    _loop_started = True
    threading.Thread(target=_loop, daemon=True).start()


def _credit_if_due(current: dict, now: datetime) -> None:
    """在室時間を加算する。"""
    if not current["present"]:
        return
    last = current.get("last_credit_at")
    if not last:
        current["last_credit_at"] = now.isoformat()
        return
    try:
        last_dt = datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=now.tzinfo)
    except ValueError:
        current["last_credit_at"] = now.isoformat()
        return

    elapsed = (now - last_dt).total_seconds()
    credits = int(elapsed // PRESENCE_CREDIT_SECONDS)
    if credits <= 0:
        return
    current["total_present_seconds"] += credits * PRESENCE_CREDIT_SECONDS
    advanced = last_dt.timestamp() + credits * PRESENCE_CREDIT_SECONDS
    current["last_credit_at"] = datetime.fromtimestamp(
        advanced, tz=last_dt.tzinfo
    ).isoformat()


def _arp_apply_result(key: str, ip: str, mac: str | None) -> None:
    """ARPの結果を適用する。"""
    now = _now()
    chime = False
    with _lock:
        _ensure_today_unlocked()
        current = _targets.get(key)
        if current is None:
            return
        if current["ip"] != ip:
            return

        name = current["name"]
        expected = current["mac"]

        if mac is None:
            current["misses"] += 1
            if current["misses"] >= MISS_THRESHOLD_COUNT:
                _mark_absent(current, now, "no ARP reply")
            else:
                log.info(
                    "%s miss %s/%s (no ARP reply)",
                    name,
                    current["misses"],
                    MISS_THRESHOLD_COUNT,
                )
        elif is_excluded_mac(mac):
            if current.get("confirmed"):
                # 正しい接続で一度確定した当日記録は残す
                current["monitoring"] = False
                if current["present"]:
                    _mark_absent(current, now, "excluded mac (keep record)")
                log.info(
                    "%s excluded mac=%s (record kept)",
                    name,
                    mac,
                )
            else:
                # 未確定の仮登録だけ破棄（表には出していない）
                log.info("%s discarded pending excluded mac=%s", name, mac)
                _targets.pop(key, None)
        elif expected is None:
            was_confirmed = bool(current.get("confirmed"))
            current["mac"] = mac
            current["confirmed"] = True
            _mark_present(current, now)
            new_key = _make_key(ip, mac)
            current["key"] = new_key
            if new_key != key:
                _targets.pop(key, None)
                _targets[new_key] = current
            log.info("%s learned mac=%s", name, mac)
            _credit_if_due(current, now)
            chime = not was_confirmed
        elif mac == expected:
            was_confirmed = bool(current.get("confirmed"))
            was_present = bool(current["present"])
            if not current.get("confirmed"):
                current["confirmed"] = True
            if not current["present"]:
                _mark_present(current, now)
                log.info("%s returned", name)
                chime = True
            else:
                current["misses"] = 0
                log.info("%s present mac=%s", name, mac)
                chime = not was_confirmed
            _credit_if_due(current, now)
        else:
            chime = False
            current["misses"] += 1
            if current["misses"] >= MISS_THRESHOLD_COUNT:
                _mark_absent(current, now, "mac mismatch")
            else:
                log.info(
                    "%s miss %s/%s expected=%s got=%s",
                    name,
                    current["misses"],
                    MISS_THRESHOLD_COUNT,
                    expected,
                    mac,
                )

        # 不在でもリストから消さない
        _save_unlocked()

    if chime:
        play_arrival_sound()


def _loop() -> None:
    """監視ループを実行する。"""
    log.info("monitor loop started")
    while True:
        with _lock:
            _ensure_today_unlocked()
            # 在室者の時間加算（ARP 有無に関わらず）
            now = _now()
            for t in _targets.values():
                if t["present"]:
                    _credit_if_due(t, now)
            if any(t["present"] for t in _targets.values()):
                _save_unlocked()
            # 監視対象のIPアドレスのリストを作成する
            snapshot = [
                (t["key"], t["ip"])
                for t in _targets.values()
                if t["monitoring"] and t["ip"]
            ]

        for key, ip in snapshot:
            # ARPを送信して、指定したIPのMACアドレスを取得する。取得できない場合はNoneを返す。
            try:
                mac = arp_request(ip)
            except Exception:
                log.exception("ARP request failed ip=%s", ip)
                mac = None
            _arp_apply_result(key, ip, mac)

        time.sleep(CHECK_INTERVAL_SECONDS)


def resume_monitoring() -> None:
    """起動時に保存済みターゲットがあれば監視ループを開始する。"""
    with _lock:
        has = any(t.get("monitoring") and t.get("ip") for t in _targets.values())
    if has:
        _ensure_loop()


def start_monitoring(
    name: str,
    grade: str,
    ip: str,
    mac: str | None = None,
) -> bool | str:
    """監視開始・当日レコード更新。除外 MAC なら False。上限超過なら 'full'。"""
    mac_n = normalize_mac(mac) if mac else None
    if is_excluded_mac(mac_n):
        log.info("%s ignored excluded mac=%s", name, mac_n)
        return False

    # body に MAC が無い場合は ARP で先に確認し、除外なら表に出さず拒否する
    if not mac_n:
        try:
            learned = arp_request(ip)
        except Exception:
            log.exception("ARP probe failed on connect ip=%s", ip)
            learned = None
        if learned:
            if is_excluded_mac(learned):
                log.info("%s ignored excluded mac=%s (arp on connect)", name, learned)
                return False
            mac_n = learned

    grade_n = normalize_grade(grade)
    key = _make_key(ip, mac_n)
    now = _now()
    confirmed = mac_n is not None

    with _lock:
        _ensure_today_unlocked()

        existing_keys = [
            k
            for k, t in _targets.items()
            if (mac_n and t["mac"] == mac_n)
            or t["ip"] == ip
            or (t["name"] == name and t["grade"] == grade_n)
        ]
        is_update = bool(existing_keys)

        visible_count = sum(1 for t in _targets.values() if t.get("confirmed"))
        if not is_update and visible_count >= MAX_TARGETS:
            log.warning("max targets reached (%s), reject %s", MAX_TARGETS, name)
            return "full"

        prev = None
        for old in existing_keys:
            prev = _targets.pop(old, prev)

        was_absent = bool(prev) and not prev.get("present")
        is_new = prev is None

        if prev:
            prev["key"] = key
            prev["name"] = name
            prev["grade"] = grade_n
            prev["ip"] = ip
            if mac_n:
                prev["mac"] = mac_n
            prev["monitoring"] = True
            if confirmed:
                prev["confirmed"] = True
            if not prev.get("arrived_at"):
                prev["arrived_at"] = now.isoformat()
            _mark_present(prev, now)
            _targets[key] = prev
        else:
            _targets[key] = {
                "key": key,
                "name": name,
                "grade": grade_n,
                "ip": ip,
                "mac": mac_n,
                "monitoring": True,
                "misses": 0,
                "present": True,
                "arrived_at": now.isoformat(),
                "left_at": None,
                "total_present_seconds": 0,
                "last_credit_at": now.isoformat(),
                "confirmed": confirmed,
            }

        _save_unlocked()

    log.info(
        "%s (%s) connected ip=%s mac=%s confirmed=%s",
        name,
        grade_n,
        ip,
        mac_n or "(pending ARP)",
        confirmed,
    )
    _ensure_loop()
    # 新規到着、または不在からの再到着（確定時のみ）
    if confirmed and (is_new or was_absent):
        play_arrival_sound()
    return "pending" if not confirmed else True
