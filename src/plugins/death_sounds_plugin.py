import logging
import random
from pathlib import Path

from core.event_bus import bus, Event
from core import config
from inputs.screen_reader import ScreenReader
from processors.death_count_processor import DeathCountProcessor
from outputs.audio_output import AudioOutput
from plugins.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac"}


class DeathSoundsPlugin(BasePlugin):
    """
    Plays a random sound from sounds/death_sounds/ whenever you die in Smite 2.

    Detection method: monitors the death count displaed in the player score HUD region.
    DeathCountProcessor watches for the death count increasing and fires game.death —
    this plugin reacts to that event.

    Sound folder: sounds/death_sounds/
    Drop any .wav / .mp3 / .ogg / .flac files in there and they'll be picked up
    automatically — no code changes needed.

    Config (config/default.yaml):
        death_sounds:
          volume: 1.0
    """

    name = "death_sounds"

    def _build(self):

        self._sounds_dir = Path(config.get("audio.sounds_dir", "sounds")) / "death_sounds"
        self._volume     = config.get("death_sounds.volume", 1.0)

        self.screen   = ScreenReader()
        self.detector = DeathCountProcessor()
        self.audio    = AudioOutput()

        self.inputs     = [self.screen]
        self.processors = [self.detector]
        self.outputs    = [self.audio]

    def on_start(self):
        bus.subscribe("game.death", self._on_death)
        self._sounds_dir.mkdir(parents=True, exist_ok=True)
        self.sounds = self._available_sounds()
        logger.info(
            f"DeathSoundsPlugin ready — {len(self.sounds)} sound(s) in '{self._sounds_dir}'"
        )
        
        if not self.sounds:
            logger.warning(
                f"No sounds found in '{self._sounds_dir}'. "
                "Add .wav/.mp3/.ogg/.flac files to that folder."
            )

    def on_stop(self):
        bus.unsubscribe("game.death", self._on_death)

    # -------------------------------------------------------------------------

    def _on_death(self, event: Event):
        if not self.sounds:
            logger.warning("DeathSoundsPlugin: no sounds available to play.")
            return

        chosen = random.choice(self.sounds)
        logger.info(f"Death detected — playing: {chosen.name}")
        self.audio.play(f"death_sounds/{chosen.name}")

    def _available_sounds(self):
        if not self._sounds_dir.exists():
            return []
        return [
            f for f in self._sounds_dir.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
