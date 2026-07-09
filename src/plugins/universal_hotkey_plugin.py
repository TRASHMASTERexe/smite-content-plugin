import logging

from core import config
from inputs.hotkey_input import HotkeyInput
from plugins.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

class UniversalHotkeysPlugin(BasePlugin):
    """
    Maps all universally used hotkeys

    Config (config/default.yaml):
        hotkeys:
            ocr_toggle: "ctrl+shift+o"
    """

    name = "universal_hotkeys"

    def _build(self):
        self.ocr_toggle_key = config.get("hotkeys.ocr_toggle", "ctrl+shift+o")
        self.hotkeys = HotkeyInput({self.ocr_toggle_key: ("system.ocr_toggle", {})})

        self.inputs = [self.hotkeys]

    def on_start(self):
        logger.info("UniversalHotkeysPlugin starting (ocr_toggle=%s)", self.ocr_toggle_key)

    def on_stop(self):
        logger.info("UniversalHotkeysPlugin stopping...")

