import threading
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class Event:
    type: str
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""


class EventBus:
    """
    Central pub/sub event bus. Inputs publish events; processors and outputs subscribe.

    Subscribe with "*" to receive all events (useful for logging/debugging).
    All handlers are called synchronously in the publishing thread — keep them fast.
    """

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, handler: Callable[["Event"], None]):
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: Callable[["Event"], None]):
        with self._lock:
            handlers = self._handlers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    def has_subscribers(self, event_type: str) -> bool:
        with self._lock:
            return bool(self._handlers.get(event_type))

    def publish(self, event: "Event"):
        with self._lock:
            handlers = (
                list(self._handlers.get(event.type, []))
                + list(self._handlers.get("*", []))
            )
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Handler {handler.__qualname__} failed on '{event.type}': {e}")


# Global singleton — import and use directly
bus = EventBus()
