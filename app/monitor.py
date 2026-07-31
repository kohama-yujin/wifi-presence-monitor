import json
import logging
import threading
import time
from datetime import date, datetime, timedelta

from app.config import (
    CHECK_INTERVAL_SECONDS,
    GRADE_ORDER,
    MAX_TARGETS,
    STATE_DIR,
    normalize_grade,
    state_file_for,
)
from app.sound import play_arrival_sound

log = logging.getLogger("presence")

_lock = threading.Lock()
_targets: dict[str, dict] = {}
_day: str = date.today().isoformat()
_loop_started = False
_last_check_at: str | None = None
_next_check_at: str | None = None
_revision: int = 0


def _bump_revision_unlocked() -> None:
    """画面側に反映が必要な状態変化を通知する。"""
    global _revision
    _revision += 1


def _now() -> datetime:
    return datetime.now().astimezone()


def _today() -> str:
    return date.today().isoformat()


def _person_key(name: str, grade: str) -> str:
    return f"person:{grade}:{name}"


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
        "last_seen_at": t.get("last_seen_at"),
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


def _parse_dt(value: str | None, tz) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt


def _sync_credit_to(current: dict, until: datetime) -> None:
    """総在室を until 時点までに揃える（秒単位）。"""
    if not current["present"]:
        return
    last_dt = _parse_dt(current.get("last_credit_at"), until.tzinfo)
    if last_dt is None:
        current["last_credit_at"] = until.isoformat()
        return

    delta = (until - last_dt).total_seconds()
    if abs(delta) < 1e-6:
        return

    if delta > 0:
        current["total_present_seconds"] += int(delta)
        current["last_credit_at"] = until.isoformat()
        return

    # さかのぼり: 超過分を差し戻す
    over = int(round(-delta))
    if over > 0:
        current["total_present_seconds"] = max(
            0,
            current["total_present_seconds"] - over,
        )
    current["last_credit_at"] = until.isoformat()


def _mark_absent(current: dict, now: datetime, reason: str) -> None:
    """在室者から不在になったときの処理。"""
    leave_at = now

    arrived_dt = _parse_dt(current.get("arrived_at"), now.tzinfo)
    if arrived_dt is not None and leave_at < arrived_dt:
        leave_at = arrived_dt

    if current["present"]:
        _sync_credit_to(current, leave_at)
        current["left_at"] = leave_at.isoformat()
    current["present"] = False
    current["monitoring"] = False
    log.info("%s absent (%s) left_at=%s", current["name"], reason, current.get("left_at"))


def _mark_present(current: dict, now: datetime) -> None:
    """在室者になったときの処理。"""
    was_present = bool(current.get("present"))
    current["present"] = True
    current["left_at"] = None  # 再接続・復帰時は帰宅をクリア
    current["misses"] = 0
    current["last_seen_at"] = now.isoformat()
    current["monitoring"] = True
    if not was_present or not current.get("last_credit_at"):
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
    _bump_revision_unlocked()


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
        "last_seen_at": t.get("last_seen_at"),
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
    """在室状況を取得する（/status）。"""
    with _lock:
        _ensure_today_unlocked()
        last_check = _last_check_at
        next_check = _next_check_at
        revision = _revision
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
        "revision": revision,
        "last_check_at": last_check,
        "next_check_at": next_check,
        "check_interval_seconds": CHECK_INTERVAL_SECONDS,
        "count": len(targets),
        "max_targets": MAX_TARGETS,
        "grades": GRADE_ORDER,
        "by_grade": by_grade,
        "targets": targets,
        "mode": "connect_disconnect",
    }


def list_history_dates() -> list[str]:
    """data/presence にある過去日の一覧（当日は含めない）。新しい順。"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    today = _today()
    dates: list[str] = []
    for path in STATE_DIR.glob("*.json"):
        day = path.stem
        if day == today:
            continue
        try:
            date.fromisoformat(day)
        except ValueError:
            continue
        dates.append(day)
    dates.sort(reverse=True)
    return dates


def get_history(day: str) -> dict | None:
    """指定日の在室記録をファイルから返す。当日・不正・未存在なら None。"""
    today = _today()
    try:
        date.fromisoformat(day)
    except ValueError:
        return None
    if day == today:
        return None

    path = state_file_for(day)
    if not path.exists():
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("failed to load history %s", path)
        return None

    loaded = raw.get("targets") or {}
    targets = [
        _public(_hydrate_target(key, t))
        for key, t in loaded.items()
        if bool(t.get("confirmed", True))
    ]
    targets.sort(key=lambda t: t["arrived_at"] or "")

    by_grade = {g: [] for g in GRADE_ORDER}
    for t in targets:
        grade = t["grade"] if t["grade"] in by_grade else "other"
        by_grade[grade].append(t)

    return {
        "date": day,
        "check_interval_seconds": CHECK_INTERVAL_SECONDS,
        "count": len(targets),
        "grades": GRADE_ORDER,
        "by_grade": by_grade,
        "targets": targets,
        "mode": "connect_disconnect",
    }


def _ensure_loop() -> None:
    """在室時間の加算ループを開始する。"""
    global _loop_started
    if _loop_started:
        return
    _loop_started = True
    threading.Thread(target=_loop, daemon=True).start()


def _credit_if_due(current: dict, now: datetime) -> None:
    """在室時間を加算する（不足分を秒単位で）。"""
    _sync_credit_to(current, now)


def _loop() -> None:
    """在室時間の加算と画面更新用 revision の更新。"""
    global _last_check_at, _next_check_at
    log.info("credit loop started")
    while True:
        with _lock:
            _ensure_today_unlocked()
            now = _now()
            for t in _targets.values():
                if t["present"]:
                    _credit_if_due(t, now)
            if any(t["present"] for t in _targets.values()):
                _save_unlocked()
            _last_check_at = now.isoformat()
            _next_check_at = (
                now + timedelta(seconds=CHECK_INTERVAL_SECONDS)
            ).isoformat()
            _bump_revision_unlocked()

        time.sleep(CHECK_INTERVAL_SECONDS)


def resume_monitoring() -> None:
    """起動時に在室者がいれば加算ループを開始する。"""
    with _lock:
        has = any(t.get("present") for t in _targets.values())
    if has:
        _ensure_loop()


def start_monitoring(
    name: str,
    grade: str,
    ip: str | None = None,
) -> bool | str:
    """
    在室開始（POST /wifi_connected）。
    name + grade で当日レコードを更新する。
    上限超過なら 'full'。
    """
    global _last_check_at
    grade_n = normalize_grade(grade)
    key = _person_key(name, grade_n)
    now = _now()

    with _lock:
        _last_check_at = now.isoformat()
        _ensure_today_unlocked()

        existing_keys = [
            k
            for k, t in _targets.items()
            if (t["name"] == name and t["grade"] == grade_n)
            or t.get("key") == key
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
            if ip:
                prev["ip"] = ip
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
                "mac": None,
                "monitoring": True,
                "misses": 0,
                "present": True,
                "arrived_at": now.isoformat(),
                "left_at": None,
                "total_present_seconds": 0,
                "last_credit_at": now.isoformat(),
                "last_seen_at": now.isoformat(),
                "confirmed": True,
            }

        _save_unlocked()
        _bump_revision_unlocked()

    log.info("%s (%s) connected ip=%s", name, grade_n, ip or "-")
    _ensure_loop()
    if is_new or was_absent:
        play_arrival_sound()
    return True


def stop_monitoring(name: str, grade: str) -> bool | str:
    """
    不在トリガー（POST /wifi_disconnected）。
    name + grade で当日レコードを探し、在室なら不在にする。
    見つからなければ 'missing'。既に不在なら 'already_absent'。
    """
    grade_n = normalize_grade(grade)
    now = _now()

    with _lock:
        _ensure_today_unlocked()
        current = None
        for t in _targets.values():
            if t["name"] == name and t["grade"] == grade_n and t.get("confirmed"):
                current = t
                break

        if current is None:
            log.info("%s (%s) disconnect ignored (not found)", name, grade_n)
            return "missing"

        if not current["present"]:
            log.info("%s (%s) disconnect ignored (already absent)", name, grade_n)
            return "already_absent"

        _mark_absent(current, now, "wifi_disconnected")
        _save_unlocked()
        _bump_revision_unlocked()

    return True
