import logging
import random
from pathlib import Path

from core.event_bus import bus, Event
from core import config, timer
from inputs.screen_reader import ScreenReader
from outputs.obs_output import OBSOutput
from plugins.base_plugin import BasePlugin
from processors.kill_count_processor import KillCountProcessor

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac"}


class BloodScreenKillStreakPlugin(BasePlugin):
    """
    Plays Increases oppacity of image in obs whenever you get a kill in Smite 2 
    which will gradually degrade back to 0 over time.

    Detection method: monitors the kill count display in the player score HUD region.
    KillCountProcessor watches for the kill count increasing and fires game.kill —
    this plugin reacts to that event.

    A per-plugin cooldown (default 15s) prevents double-firing if the kill feed
    *also* fires game.death for the same death.

    OBS Image Name: Rage Outline
    OBS image Scene: Smite Plugin Resources

    Config (config/default.yaml):
        death_sounds:
          volume: 1.0
    """

    name = "blood_screen_kill_streak"

    def _build(self):
        
        self.screen   = ScreenReader()
        self.detector = KillCountProcessor()
        self.output    = OBSOutput()

        self._image_name = config.get("blood_screen_kill_streak.image_name")
        self._filter_name = config.get("blood_screen_kill_streak.filter_name")
        self._image_opacity = 0
        self._increase_to_occour = 0
        self.is_decaying = False

        self.inputs     = [self.screen]
        self.processors = [self.detector]
        self.outputs    = [self.output]

    def on_start(self):
        bus.subscribe("game.kill", self._on_kill)

        self.output.set_filter_opacity(self._image_name, 0, self._filter_name)

        logger.info(
            f"BloodScreenKillStreakPlugin ready — image: '{self._image_name}', filter: '{self._filter_name}'"
        )
        

    def on_stop(self):
        bus.unsubscribe("game.kill", self._on_kill)
        self.output.set_filter_opacity(self._image_name, 0, self._filter_name)

    # -------------------------------------------------------------------------

    def _on_kill(self, event: Event):
        logger.info("Kill event received")
        self.is_decaying = False

        self._increase_to_occour += .2
        timer.call_repeating(0.025, self.fade_in)

        logger.info(f"Kill streak detected — image opacity increasing")

    def start_fade_out(self):
        self.is_decaying = True
        timer.call_repeating(0.1, self.fade_image_out)

    def fade_in(self):
        logger.info("Fading in blood screen effect")
        timer.debounce("start_fade_key", 5, self.start_fade_out)
        if self._increase_to_occour > 0:
            logger.info(f"Increase to occur: {self._increase_to_occour}, current image opacity: {self._image_opacity}")
            self._increase_to_occour -= 0.05
            self._image_opacity += 0.05
            self.output.set_filter_opacity(self._image_name, self._image_opacity, self._filter_name)
            return True
        else:
            logger.info("No more increase to occur — fading in complete")
            return False

    def fade_image_out(self):
        if self._image_opacity > 0:
            self._image_opacity -= 0.05
            if self._image_opacity < 0:
                self._image_opacity = 0

            self.output.set_filter_opacity(self._image_name, self._image_opacity, self._filter_name)

        if self._image_opacity == 0 or not self.is_decaying:
            return False
        else:
            return True
