import logging
from typing import Callable, Dict, Tuple

from core.event_bus import bus, Event
from inputs.base_input import BaseInput

logger = logging.getLogger(__name__)

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False
    logger.warning("keyboard not installed — hotkeys disabled. Run: pip install keyboard")


class HotkeyInput(BaseInput):
    """
    Maps keyboard shortcuts to named game events on the event bus.

    Useful for manually triggering events during gameplay when screen OCR
    isn't reliable enough (e.g. confirming a kill, starting a challenge, etc.).

    bindings format:
        {"ctrl+k": ("manual.kill", {"reason": "hotkey"})}

    The keyboard library requires running as administrator on Windows to
    capture global hotkeys outside of the focused window.
    """

    def __init__(self, bindings: Dict[str, Tuple[str, dict]] = None):
        super().__init__("hotkey_input")
        # {"combo": ("event_type", {extra_data})}
        self.bindings: Dict[str, Tuple[str, dict]] = bindings or {}

    def add_binding(self, combo: str, event_type: str, data: dict = None):
        """Add a hotkey binding at runtime."""
        self.bindings[combo] = (event_type, data or {})
        if self._running and KEYBOARD_AVAILABLE:
            self._register(combo, event_type, data or {})

    def _register(self, combo: str, event_type: str, data: dict):
        def _handler():
            bus.publish(Event(type=event_type, data=dict(data), source=self.name))
            logger.info(f"Hotkey '{combo}' -> event '{event_type}'")

        keyboard.add_hotkey(combo, _handler)

    def start(self):
        if not KEYBOARD_AVAILABLE:
            logger.warning("HotkeyInput: keyboard library not available.")
            return
        for combo, (event_type, data) in self.bindings.items():
            self._register(combo, event_type, data)
        self._running = True
        logger.info(f"HotkeyInput started with {len(self.bindings)} binding(s): {list(self.bindings)}")

    def stop(self):
        if KEYBOARD_AVAILABLE:
            keyboard.unhook_all_hotkeys()
        self._running = False
        logger.info("HotkeyInput stopped.")
