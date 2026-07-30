import logging
import threading
from pathlib import Path

from app.config import ARRIVAL_SOUND_ENABLED, ARRIVAL_SOUND_FILE

log = logging.getLogger("presence")


def play_arrival_sound() -> None:
    """到着チャイムを非同期再生する（サーバ側）。"""
    if not ARRIVAL_SOUND_ENABLED:
        return
    threading.Thread(target=_play, daemon=True).start()


def _play() -> None:
    try:
        import winsound
    except ImportError:
        log.warning("winsound unavailable; arrival sound skipped")
        return

    try:
        path = Path(ARRIVAL_SOUND_FILE)
        if path.is_file():
            winsound.PlaySound(
                str(path),
                winsound.SND_FILENAME | winsound.SND_ASYNC,
            )
        else:
            winsound.PlaySound(
                "SystemAsterisk",
                winsound.SND_ALIAS | winsound.SND_ASYNC,
            )
    except Exception:
        log.exception("failed to play arrival sound")
