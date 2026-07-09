import logging
import threading
from pathlib import Path

from core import config
from outputs.base_output import BaseOutput

logger = logging.getLogger(__name__)

try:
    import pygame
    pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
    PYGAME_AVAILABLE = True
except Exception as e:
    PYGAME_AVAILABLE = False
    logger.warning(f"pygame unavailable — audio output disabled: {e}")


class AudioOutput(BaseOutput):
    """
    Plays audio files asynchronously through a configurable output device.

    To capture audio in OBS:
      1. Install VB-Audio Virtual Cable (free): https://vb-audio.com/Cable
      2. Set audio.device in config/default.yaml to created input device name (e.g. "CABLE Input (VB-Audio Virtual Cable)")
      3. In OBS: add Audio Input Capture source → select "CABLE Output"

    Config (config/default.yaml):
        audio:
          sounds_dir: "resources/sounds"
          device: null          # null = system default; set to device name for OBS routing
          master_volume: 1.0    # global multiplier applied on top of per-sound volume
    """

    def __init__(self, sounds_dir: str = None):
        super().__init__("audio_output")
        self.sounds_dir    = Path(sounds_dir or config.get("audio.sounds_dir", "sounds"))
        self._device       = config.get("audio.device", None)        # None = default device
        self._master_vol   = float(config.get("audio.master_volume", 1.0))

    def setup(self):
        if not PYGAME_AVAILABLE:
            logger.warning("AudioOutput: pygame not available.")
            return
        
        try:
            self.setup_audio_mixer()

            logger.info(f"  sounds_dir:    {self.sounds_dir.resolve()}")
            logger.info(f"  master_volume: {self._master_vol}")
        except Exception as e:
            logger.error(f"AudioOutput setup failed: {e}")

    def setup_audio_mixer(self):
        if self._device:
            try:
                pygame.mixer.init(devicename=self._device)
                logger.info(f"AudioOutput ready → device: '{self._device}'")
            except Exception as e:
                logger.warning(f"AudioOutput: could not open device '{self._device}': {e}")
                logger.warning("AudioOutput: falling back to system default device.")

        if not pygame.mixer.get_init():
            pygame.mixer.init()
            logger.info("AudioOutput ready → device: system default")

    def teardown(self):
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.quit()
            except Exception:
                pass

    def set_master_volume(self, volume: float):
        """Adjust master volume at runtime (0.0-1.0)."""
        self._master_vol = max(0.0, min(1.0, volume))
        logger.info(f"AudioOutput master volume → {self._master_vol:.2f}")

    def play(self, filename: str):
        """
        Play a sound file. filename is relative to sounds_dir.
        """
        if not PYGAME_AVAILABLE:
            logger.debug(f"AudioOutput: skipped play('{filename}') — pygame unavailable.")
            return

        path = self.sounds_dir / filename
        if not path.exists():
            logger.warning(f"AudioOutput: sound file not found: {path}")
            return

        def _play():
            try:
                sound = pygame.mixer.Sound(str(path))
                sound.set_volume(self._master_vol)
                sound.play()
            except Exception as e:
                logger.error(f"AudioOutput play('{filename}'): {e}")

        threading.Thread(target=_play, daemon=True, name=f"audio-{filename}").start()
