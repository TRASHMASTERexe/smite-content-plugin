from abc import ABC, abstractmethod


class BaseOutput(ABC):
    """
    Abstract base for all output handlers.

    Outputs subscribe to structured game events and produce external effects:
    sounds, OBS changes, file writes, HTTP calls, etc.

    setup() is called before the plugin starts.
    teardown() is called when the plugin stops.
    """

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def setup(self):
        """Initialise resources (connections, file handles, etc.)."""
        ...

    @abstractmethod
    def teardown(self):
        """Clean up resources."""
        ...
