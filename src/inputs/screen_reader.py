import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from core.event_bus import bus, Event
from core import config
from inputs.base_input import BaseInput

logger = logging.getLogger(__name__)

try:
    import mss

    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False
    logger.warning("mss not installed — screen capture disabled. Run: pip install mss")

try:
    import easyocr

    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    logger.warning("easyocr not installed — OCR disabled. Run: pip install easyocr")

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("numpy not installed — OCR capture disabled. Run: pip install numpy")

try:
    import cv2

    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("opencv-python not installed — image pre-processing disabled.")


@dataclass(frozen=True)
class RegionConfig:
    """
    Defines a named screen region to capture and the event type to emit.

    bbox:     (left, top, width, height) in screen pixels.
    interval: Optional per-region capture interval in seconds.
              Falls back to ScreenReader's global interval if None.
    """

    name: str
    bbox: tuple[int, int, int, int]
    event_type: str
    interval: Optional[float] = None

    @property
    def monitor(self) -> dict[str, int]:
        left, top, width, height = self.bbox
        return {"left": left, "top": top, "width": width, "height": height}


# Default HUD regions tuned for Smite 2 at 1920x1080.
DEFAULT_REGIONS_1080P: list[RegionConfig] = [
    RegionConfig("player_kills",   (820,  1197, 50,  64),  "screen.player_kills"),
    RegionConfig("player_deaths",  (877,  1197, 50,  64),  "screen.player_deaths"),
    RegionConfig("player_assists", (934,  1197, 50,  64),  "screen.player_assists"),
    RegionConfig("game_timer",     (880,  15,   160, 45),  "screen.timer"),
]


def _make_region_config(name: str, raw: dict[str, Any]) -> RegionConfig:
    bbox = tuple(raw["bbox"])
    return RegionConfig(
        name=name,
        bbox=bbox,
        event_type=raw["event_type"],
        interval=raw.get("interval"),
    )


def _load_regions() -> list[RegionConfig]:
    """Use saved regions from the debug UI if available, else fall back to defaults."""
    regions_file = Path(__file__).parent.parent.parent / "config" / "regions.yaml"
    if regions_file.exists():
        with open(regions_file) as f:
            data = yaml.safe_load(f) or {}
        if data:
            logger.info(f"Loaded {len(data)} custom region(s) from config/regions.yaml")
            return [_make_region_config(name, values) for name, values in data.items()]
    return DEFAULT_REGIONS_1080P


class ScreenReader(BaseInput):
    """
    Periodically captures defined screen regions, runs OCR, and publishes events
    whenever text in a region changes.

    Published events:
        type  — region.event_type  (e.g. "screen.kill_feed")
        data  — {"text": "<ocr_result>", "region": "<region_name>"}

    Usage:
        reader = ScreenReader(interval=1.0)
        reader.start()
    """

    def __init__(self, interval: float = None, regions: list[RegionConfig] = None):
        super().__init__("screen_reader")
        self.interval = interval or config.get("screen.capture_interval", 1.0)
        self.regions = regions or _load_regions()
        self._reader = None
        self._prev_texts: dict = {}
        self._last_capture: dict[str, float] = {region.name: 0.0 for region in self.regions}
        self._paused: bool = False
        bus.subscribe("system.ocr_toggle", self._on_ocr_toggle)

    def _on_ocr_toggle(self, event: Event):
        self._paused = not self._paused
        state = "PAUSED" if self._paused else "RESUMED"
        logger.info(f"ScreenReader {state} via hotkey")

    def _init_ocr(self):
        if EASYOCR_AVAILABLE:
            logger.info("Initialising EasyOCR (first run may download models)...")
            self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            logger.info("EasyOCR ready.")

    def _ready(self) -> bool:
        return MSS_AVAILABLE and NUMPY_AVAILABLE and self._reader is not None

    # Event types that are digit-only — use restricted allowlist and always publish
    _DIGIT_EVENTS = {"screen.player_kills", "screen.player_deaths", "screen.player_assists"}

    @classmethod
    def _is_digit_event(cls, event_type: str) -> bool:
        return event_type in cls._DIGIT_EVENTS

    def _preprocess(self, img_array: Any, upscale: bool = False) -> Any:
        """Greyscale + threshold. Upscales small digit regions aggressively."""
        if not CV2_AVAILABLE:
            return img_array
        grey = cv2.cvtColor(img_array, cv2.COLOR_BGRA2GRAY)

        if upscale:
            h, w = grey.shape[:2]
            # Always upscale digit regions to at least 80px tall for reliable OCR
            scale = max(80 / h, 80 / w, 4.0)
            grey = cv2.resize(grey, (int(w * scale), int(h * scale)),
                              interpolation=cv2.INTER_LANCZOS4)

        # OTSU auto-picks the best threshold — works well for HUD text with
        # a clear bimodal histogram (bright digits on dark background)
        _, thresh = cv2.threshold(grey, 127, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thresh

    def _region_interval(self, region: RegionConfig) -> float:
        return region.interval if region.interval is not None else self.interval

    def _should_capture_region(self, region: RegionConfig, now: float) -> bool:
        if not bus.has_subscribers(region.event_type):
            return False
        return (now - self._last_capture.get(region.name, 0.0)) >= self._region_interval(region)

    def _capture_region(self, sct: Any, region: RegionConfig) -> Optional[str]:
        if not self._ready():
            return None

        screenshot = sct.grab(region.monitor)
        img = np.array(screenshot)
        is_digit = self._is_digit_event(region.event_type)
        img = self._preprocess(img, upscale=is_digit)

        if is_digit:
            result = self._reader.readtext(img, text_threshold=0.5, low_text=0.4, allowlist="0123456789", detail=1)
        else:
            result = self._reader.readtext(img)

        return " ".join(r[1] for r in result).strip()

    def _publish_region_text(self, region: RegionConfig, text: str):
        is_digit = self._is_digit_event(region.event_type)
        previous = self._prev_texts.get(region.name)
        if not is_digit and text == previous:
            return

        self._prev_texts[region.name] = text
        bus.publish(
            Event(
                type=region.event_type,
                data={"text": text, "region": region.name},
                source=self.name,
            )
        )

    def _capture_and_publish_region(self, sct: Any, region: RegionConfig, now: float):
        text = self._capture_region(sct, region)
        self._last_capture[region.name] = now
        # logger.debug(f"OCR [{region.name}]: '{text[:80] if text else '(empty)'}'")
        if text:
            self._publish_region_text(region, text)

    def _process_regions(self, sct: Any):
        now = time.monotonic()
        for region in self.regions:
            if not self._should_capture_region(region, now):
                continue

            try:
                self._capture_and_publish_region(sct, region, now)
            except Exception as e:
                logger.error(f"ScreenReader error on region '{region.name}': {e}")

    def _loop(self):
        self._init_ocr()
        if not self._ready():
            logger.warning("ScreenReader prerequisites missing — loop is idle.")
            return

        with mss.mss() as sct:
            while self._running:
                if self._paused:
                    time.sleep(0.1)
                    continue

                self._process_regions(sct)

                time.sleep(0.05)  # tight loop; actual rate controlled per-region above

    def start(self):
        self._run_in_thread(self._loop)
        logger.info(f"ScreenReader started (global_interval={self.interval}s, regions={len(self.regions)})")

    def stop(self):
        self._running = False
        bus.unsubscribe("system.ocr_toggle", self._on_ocr_toggle)
        logger.info("ScreenReader stopped.")
