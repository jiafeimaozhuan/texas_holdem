from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum, IntEnum


class Suit(str, Enum):
    CLUBS = "c"
    DIAMONDS = "d"
    HEARTS = "h"
    SPADES = "s"


class Rank(IntEnum):
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14


@dataclass(frozen=True, slots=True)
class Card:
    rank: Rank
    suit: Suit


@dataclass(slots=True)
class Deck:
    cards: list[Card]

    @classmethod
    def new_shuffled(cls, seed: int | None = None) -> Deck:
        cards = [Card(rank=rank, suit=suit) for suit in Suit for rank in Rank]
        random.Random(seed).shuffle(cards)
        return cls(cards=cards)

    def deal(self, count: int) -> list[Card]:
        if not isinstance(count, int) or isinstance(count, bool):
            raise TypeError("count must be an integer")
        if count < 0:
            raise ValueError("count must be non-negative")
        if count > len(self.cards):
            raise ValueError("cannot deal more cards than remain in the deck")

        dealt = self.cards[:count]
        del self.cards[:count]
        return dealt
