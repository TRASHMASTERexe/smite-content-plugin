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


class DeathCountProcessor(BaseProcessor):
    """
    Watches the player_deaths OCR region and fires game.death when the count increases.
    Resets its baseline when the count returns to 0 (new game).

    Subscribes to:  screen.player_deaths
    Publishes:      game.death
    """

    def __init__(self):
        super().__init__("death_count_processor")
        self._last: int = -1
        self._last_5: list[int] = [0, 0, 0, 0, 0]

    def setup(self):
        bus.subscribe("screen.player_deaths", self._on_deaths)
        logger.info("DeathCountProcessor subscribed to screen.player_deaths")

    def teardown(self):
        bus.unsubscribe("screen.player_deaths", self._on_deaths)

    def _on_deaths(self, event: Event):
        v = _parse_stat(event.data.get("text", ""))
        if v is None:
            return
        
        if self._last == -1 and all(x == 0 for x in self._last_5):
            self._last = v
            if self._last > 0:
                self._last_5 = [v, v, v, v, v]
            logger.info(f"DeathCountProcessor baseline: {v}")
            return
        
        self._last_5.pop(0)
        self._last_5.append(v)

        most_appearences = max(set(self._last_5), key=self._last_5.count)
        number_appearences = self._last_5.count(most_appearences)

        if number_appearences >= 3:
            if most_appearences == 0 and self._last > 0:
                logger.info("Death count reset to 0 — new game, resetting baseline")
                self._last = 0
                state.player.deaths = 0
                return

            if most_appearences < self._last + 3 and most_appearences > self._last:
                for _ in range(most_appearences - self._last):
                    state.player.deaths += 1
                    bus.publish(Event("game.death",
                        {"victim": "player", "manual": False, "source": "ocr"},
                        self.name))
                logger.info(f"Death(s): {self._last}→{most_appearences}")
                self._last = most_appearences
