import threading
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class PlayerState:
    name: str = ""
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    gold: int = 0
    level: int = 1
    hp_percent: float = 1.0
    mana_percent: float = 1.0


@dataclass
class GameState:
    """
    Shared, thread-safe game state updated by processors.

    Use state.update(field=value) to mutate safely from any thread.
    Plugins/outputs can read fields directly — reads are not locked
    since Python attribute access on dataclasses is effectively atomic
    for simple types.
    """

    in_game: bool = False
    game_timer: str = "00:00"
    player: PlayerState = field(default_factory=PlayerState)
    enemy_team: Dict[str, PlayerState] = field(default_factory=dict)

    _lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def update(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)

    def reset(self):
        with self._lock:
            self.in_game = False
            self.game_timer = "00:00"
            self.player = PlayerState()
            self.enemy_team = {}


# Global singleton
state = GameState()
