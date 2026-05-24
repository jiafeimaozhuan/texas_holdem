from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from texas_holdem_trainer.domain.cards import Card, Deck


class Street(str, Enum):
    WAITING = "waiting"
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"
    COMPLETE = "complete"


@dataclass
class PlayerState:
    seat: int
    name: str
    stack: int
    is_human: bool = False
    hole_cards: list[Card] = field(default_factory=list)
    folded: bool = False
    all_in: bool = False
    street_bet: int = 0
    total_committed: int = 0
    acted_this_street: bool = False
    # Street bet level this player matched or set with their last action.
    last_acted_street_bet: int = 0

    def commit_chips(self, amount: int) -> int:
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise TypeError("amount must be an integer")
        if amount < 0:
            raise ValueError("amount must be non-negative")

        committed = min(amount, self.stack)
        self.stack -= committed
        self.street_bet += committed
        self.total_committed += committed
        if self.stack == 0:
            self.all_in = True
        return committed


@dataclass
class GameState:
    table_id: str
    players: list[PlayerState]
    dealer_seat: int
    small_blind: int
    big_blind: int
    street: Street = Street.WAITING
    board: list[Card] = field(default_factory=list)
    pot: int = 0
    deck: Deck | None = None
    current_actor_seat: int | None = None
    current_bet: int = 0
    min_raise: int = 0
    hand_number: int = 0
    seed: int | None = None
    hand_history: list[dict] = field(default_factory=list)

    def players_in_hand(self) -> list[PlayerState]:
        return [
            player
            for player in self.players
            if not player.folded and (player.stack > 0 or player.all_in)
        ]
