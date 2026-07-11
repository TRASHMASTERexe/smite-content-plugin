import heapq
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass(order=True)
class _ScheduledTask:
    run_at: float
    sequence: int
    token: "_CancelToken" = field(compare=False)
    callback: Callable[..., Any] = field(compare=False)
    args: tuple[Any, ...] = field(compare=False, default_factory=tuple)
    kwargs: Dict[str, Any] = field(compare=False, default_factory=dict)
    interval: Optional[float] = field(compare=False, default=None)
    stop_on_false: bool = field(compare=False, default=True)


class _CancelToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


class TimerHandle:
    """
    Handle returned by TimerService scheduling methods.

    Use cancel() to stop future execution.
    """

    def __init__(self, token: _CancelToken):
        self._token = token

    def cancel(self):
        self._token.cancel()

    def is_cancelled(self) -> bool:
        return self._token.is_cancelled()


class TimerService:
    """
    Threaded scheduler for one-shot, repeating, and debounced callbacks.

    Designed for plugin use-cases like:
      - call this once after inactivity (debounce)
      - run this every N seconds until callback returns False
      - schedule one-shot delayed work
    """

    def __init__(self, tick_resolution: float = 0.05):
        self.tick_resolution = tick_resolution
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._tasks: list[_ScheduledTask] = []
        self._sequence = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._debounce_tokens: Dict[str, _CancelToken] = {}

    def start(self):
        with self._condition:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._run_loop,
                name="core-timer-service",
                daemon=True,
            )
            self._thread.start()

    def stop(self, cancel_pending: bool = True, timeout: float = 1.0):
        with self._condition:
            if not self._running:
                return

            self._running = False
            if cancel_pending:
                for task in self._tasks:
                    task.token.cancel()
                self._tasks.clear()
                for token in self._debounce_tokens.values():
                    token.cancel()
                self._debounce_tokens.clear()

            self._condition.notify_all()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def call_later(self, delay_seconds: float, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> TimerHandle:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be >= 0")
        token = _CancelToken()
        self._schedule(
            run_at=time.monotonic() + delay_seconds,
            token=token,
            callback=callback,
            args=args,
            kwargs=kwargs,
            interval=None,
            stop_on_false=True,
        )
        return TimerHandle(token)

    def call_repeating(
        self,
        interval_seconds: float,
        callback: Callable[..., Any],
        *args: Any,
        immediate: bool = False,
        stop_on_false: bool = True,
        **kwargs: Any,
    ) -> TimerHandle:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")

        token = _CancelToken()
        run_at = time.monotonic() if immediate else (time.monotonic() + interval_seconds)
        self._schedule(
            run_at=run_at,
            token=token,
            callback=callback,
            args=args,
            kwargs=kwargs,
            interval=interval_seconds,
            stop_on_false=stop_on_false,
        )
        return TimerHandle(token)

    def debounce(self, key: str, wait_seconds: float, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> TimerHandle:
        """
        Schedule callback to run after a quiet period.

        Calling debounce with the same key before wait_seconds expires resets the timer.
        """
        if wait_seconds < 0:
            raise ValueError("wait_seconds must be >= 0")

        token = _CancelToken()
        with self._condition:
            previous = self._debounce_tokens.get(key)
            if previous:
                previous.cancel()
            self._debounce_tokens[key] = token

        def _debounced_wrapper():
            if token.is_cancelled():
                return

            with self._condition:
                current = self._debounce_tokens.get(key)
                if current is token:
                    self._debounce_tokens.pop(key, None)
                else:
                    return

            callback(*args, **kwargs)

        self._schedule(
            run_at=time.monotonic() + wait_seconds,
            token=token,
            callback=_debounced_wrapper,
            args=(),
            kwargs={},
            interval=None,
            stop_on_false=True,
        )
        return TimerHandle(token)

    def cancel_debounce(self, key: str):
        with self._condition:
            token = self._debounce_tokens.pop(key, None)
            if token:
                token.cancel()

    def _schedule(
        self,
        run_at: float,
        token: _CancelToken,
        callback: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: Dict[str, Any],
        interval: Optional[float],
        stop_on_false: bool,
    ):
        self.start()
        with self._condition:
            self._sequence += 1
            heapq.heappush(
                self._tasks,
                _ScheduledTask(
                    run_at=run_at,
                    sequence=self._sequence,
                    token=token,
                    callback=callback,
                    args=args,
                    kwargs=kwargs,
                    interval=interval,
                    stop_on_false=stop_on_false,
                ),
            )
            self._condition.notify_all()

    def _run_loop(self):
        while True:
            task = self._next_task()
            if task is None:
                return

            if task.token.is_cancelled():
                continue

            continue_repeating = True
            try:
                result = task.callback(*task.args, **task.kwargs)
                if task.interval is not None and task.stop_on_false and result is False:
                    continue_repeating = False
            except Exception as exc:
                logger.exception("Timer callback failed: %s", exc)
                continue_repeating = False

            if task.interval is not None and continue_repeating and not task.token.is_cancelled():
                self._schedule(
                    run_at=time.monotonic() + task.interval,
                    token=task.token,
                    callback=task.callback,
                    args=task.args,
                    kwargs=task.kwargs,
                    interval=task.interval,
                    stop_on_false=task.stop_on_false,
                )

    def _next_task(self) -> Optional[_ScheduledTask]:
        with self._condition:
            while self._running:
                now = time.monotonic()

                if self._tasks:
                    next_task = self._tasks[0]
                    if next_task.run_at <= now:
                        return heapq.heappop(self._tasks)

                    wait_seconds = max(0.0, min(next_task.run_at - now, self.tick_resolution))
                    self._condition.wait(timeout=wait_seconds)
                else:
                    self._condition.wait(timeout=self.tick_resolution)

            return None


# Global scheduler singleton for app-wide use.
timer = TimerService()
