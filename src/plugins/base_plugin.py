import logging
from abc import ABC, abstractmethod
from typing import List

from inputs.base_input import BaseInput
from processors.base_processor import BaseProcessor
from outputs.base_output import BaseOutput

logger = logging.getLogger(__name__)


class BasePlugin(ABC):
    """
    A Plugin is a self-contained content feature.

    It bundles:
        inputs      — what to watch (screen regions, hotkeys, etc.)
        processors  — how to interpret what was seen
        outputs     — what to do about it (sounds, OBS changes, file writes)

    To create a new plugin, subclass BasePlugin and implement _build():

        class MyPlugin(BasePlugin):
            name = "my_plugin"

            def _build(self):
                self.inputs     = [HotkeyInput({...})]
                self.processors = [EventDetector("MyName")]
                self.outputs    = [AudioOutput(), OBSOutput()]

            def on_start(self):
                bus.subscribe("game.kill", self._on_kill)

            def _on_kill(self, event):
                self.outputs[0].play("kill.wav")

    Startup order:  outputs.setup → processors.setup → inputs.start → on_start()
    Shutdown order: on_stop() → inputs.stop → processors.teardown → outputs.teardown
    """

    name: str = "unnamed_plugin"

    def __init__(self):
        self.inputs:     List[BaseInput]     = []
        self.processors: List[BaseProcessor] = []
        self.outputs:    List[BaseOutput]    = []
        self._build()

    @abstractmethod
    def _build(self):
        """Populate self.inputs, self.processors, and self.outputs."""
        ...

    def start(self):
        logger.info(f"[{self.name}] Starting...")
        for output in self.outputs:
            output.setup()
        for processor in self.processors:
            processor.setup()
        for inp in self.inputs:
            inp.start()
        self.on_start()
        logger.info(f"[{self.name}] Running.")

    def stop(self):
        self.on_stop()
        for inp in self.inputs:
            inp.stop()
        for processor in self.processors:
            processor.teardown()
        for output in self.outputs:
            output.teardown()
        logger.info(f"[{self.name}] Stopped.")

    def on_start(self):
        """Optional lifecycle hook — called after all components are started."""
        pass

    def on_stop(self):
        """Optional lifecycle hook — called before components are torn down."""
        pass
