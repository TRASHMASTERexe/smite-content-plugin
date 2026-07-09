from abc import ABC, abstractmethod

from core.event_bus import Event


class BaseProcessor(ABC):
    """
    Abstract base for all processors.

    Processors subscribe to raw input events and publish derived, structured events.
    They act as the intelligence layer — turning "text changed on screen" into
    "player got a kill".

    Implement setup() to register subscriptions and teardown() to remove them.
    """

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def setup(self):
        """Register subscriptions on the event bus."""
        ...

    @abstractmethod
    def teardown(self):
        """Unregister subscriptions from the event bus."""
        ...
