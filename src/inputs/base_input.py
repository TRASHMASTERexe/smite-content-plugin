import threading
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseInput(ABC):
    """
    Abstract base for all input sources.

    Inputs run in background daemon threads and publish Events to the bus.
    Implement _loop() with your capture logic and call _run_in_thread(_loop) in start().
    """

    def __init__(self, name: str):
        self.name = name
        self._running = False
        self._thread: threading.Thread = None

    @abstractmethod
    def start(self):
        """Begin capturing and publishing events."""
        ...

    @abstractmethod
    def stop(self):
        """Signal the input to stop."""
        ...

    def _run_in_thread(self, target):
        self._thread = threading.Thread(
            target=target, name=f"input-{self.name}", daemon=True
        )
        self._running = True
        self._thread.start()

    def join(self, timeout: float = None):
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
