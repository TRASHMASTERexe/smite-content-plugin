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
from plugins.death_sounds_plugin import DeathSoundsPlugin
from plugins.universal_hotkey_plugin import UniversalHotkeysPlugin


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
    logger.info(
        "Plugin toggles: death_sounds=%s, universal_hotkeys=%s",
        death_enabled,
        hotkeys_enabled,
    )

    plugins = []
    if death_enabled:
        plugins.append(DeathSoundsPlugin())
    if hotkeys_enabled:
        plugins.append(UniversalHotkeysPlugin())

    logger.info("Loaded plugins: %s", [plugin.name for plugin in plugins])

    def shutdown(sig, frame):
        logger.info("Shutting down...")
        for plugin in plugins:
            plugin.stop()
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
