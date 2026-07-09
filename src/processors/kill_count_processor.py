import re
import logging

from core.event_bus import bus, Event
from core.game_state import state
from processors.base_processor import BaseProcessor

logger = logging.getLogger(__name__)

_NUMBER_RE = re.compile(r"\d+")


def _parse_stat(text: str):
    """Extract the first integer ≤99 from an OCR string, or None."""
    for m in _NUMBER_RE.finditer(text):
        v = int(m.group())
        if v <= 99:
            return v
    return None


class KillCountProcessor(BaseProcessor):
    """
    Watches the player_kills OCR region and fires game.kill when the count increases.
    Resets its baseline when the count returns to 0 (new game).

    Subscribes to:  screen.player_kills
    Publishes:      game.kill
    """

    def __init__(self, player_name: str = ""):
        super().__init__("kill_count_processor")
        self.player_name = player_name
        self._last: int = -1

    def setup(self):
        bus.subscribe("screen.player_kills", self._on_kills)
        logger.info("KillCountProcessor subscribed to screen.player_kills")

    def teardown(self):
        bus.unsubscribe("screen.player_kills", self._on_kills)

    def _on_kills(self, event: Event):
        v = _parse_stat(event.data.get("text", ""))
        if v is None:
            return

        if self._last == -1:
            self._last = v
            logger.info(f"KillCountProcessor baseline: {v}")
            return

        if v == 0 and self._last > 0:
            logger.info("Kill count reset to 0 — new game, resetting baseline")
            self._last = -1
            state.player.kills = 0
            return

        if v > self._last:
            for _ in range(v - self._last):
                state.player.kills += 1
                bus.publish(Event("game.kill",
                    {"killer": self.player_name, "victim": "", "manual": False, "source": "ocr"},
                    self.name))
            logger.info(f"Kill(s): {self._last}→{v}")
            self._last = v
