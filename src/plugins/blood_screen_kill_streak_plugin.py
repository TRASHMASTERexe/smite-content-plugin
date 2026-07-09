import logging
import random
from pathlib import Path

from core.event_bus import bus, Event
from core import config
from inputs.screen_reader import ScreenReader
from outputs.obs_output import OBSOutput
from plugins.base_plugin import BasePlugin
from processors.kill_count_processor import KillCountProcessor

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac"}


class BloodScreenKillStreakPlugin(BasePlugin):
    """
    Plays a random sound from sounds/death_sounds/ whenever you die in Smite 2.

    Detection method: monitors the KDA display in the player score HUD region.
    KDAProcessor watches for the death count increasing and fires game.death —
    this plugin reacts to that event. Much more reliable than the death overlay
    OCR since the score bar is always rendered clearly.

    A per-plugin cooldown (default 15s) prevents double-firing if the kill feed
    *also* fires game.death for the same death.

    Sound folder: sounds/death_sounds/
    Drop any .wav / .mp3 / .ogg / .flac files in there and they'll be picked up
    automatically — no code changes needed.

    Config (config/default.yaml):
        death_sounds:
          volume: 1.0
    """

    name = "blood_screen_kill_streak"

    def _build(self):

        self.screen   = ScreenReader()
        self.detector = KillCountProcessor()
        self.output    = OBSOutput()

        self.inputs     = [self.screen]
        self.processors = [self.detector]
        self.outputs    = [self.output]

    def on_start(self):
        bus.subscribe("game.kill", self._on_kill)
        self._sounds_dir.mkdir(parents=True, exist_ok=True)
        self.sounds = self._available_sounds()
        logger.info(
            f"BloodScreenKillStreakPlugin ready — {len(self.sounds)} sound(s) in '{self._sounds_dir}'"
        )
        
        if not self.sounds:
            logger.warning(
                f"No sounds found in '{self._sounds_dir}'. "
                "Add .wav/.mp3/.ogg/.flac files to that folder."
            )

    def on_stop(self):
        bus.unsubscribe("game.kill", self._on_kill)

    # -------------------------------------------------------------------------

    def _on_kill(self, event: Event):
        if not self.sounds:
            logger.warning("BloodScreenKillStreakPlugin: no sounds available to play.")
            return

        chosen = random.choice(self.sounds)
        logger.info(f"Kill streak detected — playing: {chosen.name}")
        self.output.play(f"blood_screen_kill_streak/{chosen.name}")

    def _available_sounds(self):
        if not self._sounds_dir.exists():
            return []
        return [
            f for f in self._sounds_dir.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
