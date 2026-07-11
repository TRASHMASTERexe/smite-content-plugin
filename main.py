import logging
import os
import signal
import sys
import time
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# Add src/ to path so all module imports work without package prefixes
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from core import config
from core import timer
from plugins.death_sounds_plugin import DeathSoundsPlugin
from plugins.universal_hotkey_plugin import UniversalHotkeysPlugin
from plugins.blood_screen_kill_streak_plugin import BloodScreenKillStreakPlugin


def _plugin_enabled(name: str) -> bool:
    """Check config/plugins.yaml written by the Debug UI. Defaults to enabled."""
    plugins_file = Path(__file__).parent / "config" / "plugins.yaml"
    if plugins_file.exists():
        with open(plugins_file) as f:
            states = yaml.safe_load(f) or {}
        return states.get(name, True)
    return True


def setup_logging(level: str = "INFO"):
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger("obsws").setLevel(logging.WARNING)
    log_dir = os.path.join(os.path.dirname(__file__), "resources", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "app.log")

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(fmt)

    # File handler — overwrites each run so it's always the latest session
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.addHandler(console)
    root.addHandler(file_handler)

    logging.getLogger("main").info(f"Logging to {log_file}")


def main():
    config.load()
    setup_logging(config.get("logging.level", "INFO"))

    logger = logging.getLogger("main")
    logger.info("Smite Plugin Base starting...")

    # -------------------------------------------------------------------------
    # Register your plugins here.
    # Each plugin is an independent feature — add as many as you need.
    # -------------------------------------------------------------------------
    death_enabled = _plugin_enabled("death_sounds")
    hotkeys_enabled = _plugin_enabled("universal_hotkeys")
    blood_screen_enabled = _plugin_enabled("blood_screen_kill_streak")
    logger.info(
        "Plugin toggles: death_sounds=%s, universal_hotkeys=%s, blood_screen_kill_streak=%s",
        death_enabled,
        hotkeys_enabled,
        blood_screen_enabled,
    )

    plugins = []
    if death_enabled:
        plugins.append(DeathSoundsPlugin())
    if hotkeys_enabled:
        plugins.append(UniversalHotkeysPlugin())
    if blood_screen_enabled:
        plugins.append(BloodScreenKillStreakPlugin())

    logger.info("Loaded plugins: %s", [plugin.name for plugin in plugins])

    def shutdown(sig, frame):
        logger.info("Shutting down...")
        for plugin in plugins:
            plugin.stop()
        timer.stop(cancel_pending=True)
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for plugin in plugins:
        plugin.start()

    logger.info("Running. Press Ctrl+C to stop.")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
