from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import IntEnum
from itertools import combinations
from typing import Sequence

from texas_holdem_trainer.domain.cards import Card


class HandCategory(IntEnum):
    HIGH_CARD = 1
    PAIR = 2
    TWO_PAIR = 3
    THREE_OF_A_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_A_KIND = 8
    STRAIGHT_FLUSH = 9


@dataclass(frozen=True, order=True)
class HandRank:
    category: HandCategory
    tiebreakers: tuple[int, ...]


def evaluate_best(cards: Sequence[Card]) -> HandRank:
    """Return the best five-card rank from 5 to 7 cards."""
    if not 5 <= len(cards) <= 7:
        raise ValueError("evaluate_best requires between 5 and 7 cards")

    return max(_evaluate_five(hand) for hand in combinations(cards, 5))


def _evaluate_five(cards: tuple[Card, ...]) -> HandRank:
    ranks = sorted((int(card.rank) for card in cards), reverse=True)
    counts = Counter(ranks)
    grouped_ranks = sorted(counts, key=lambda rank: (counts[rank], rank), reverse=True)
    flush = len({card.suit for card in cards}) == 1
    straight_high = _straight_high(ranks)

    if flush and straight_high is not None:
        return HandRank(HandCategory.STRAIGHT_FLUSH, (straight_high,))

    if 4 in counts.values():
        quad_rank = grouped_ranks[0]
        kicker = max(rank for rank in ranks if rank != quad_rank)
        return HandRank(HandCategory.FOUR_OF_A_KIND, (quad_rank, kicker))

    if sorted(counts.values(), reverse=True) == [3, 2]:
        trip_rank = grouped_ranks[0]
        pair_rank = grouped_ranks[1]
        return HandRank(HandCategory.FULL_HOUSE, (trip_rank, pair_rank))

    if flush:
        return HandRank(HandCategory.FLUSH, tuple(ranks))

    if straight_high is not None:
        return HandRank(HandCategory.STRAIGHT, (straight_high,))

    if 3 in counts.values():
        trip_rank = grouped_ranks[0]
        kickers = tuple(rank for rank in ranks if rank != trip_rank)
        return HandRank(HandCategory.THREE_OF_A_KIND, (trip_rank, *kickers))

    pair_ranks = [rank for rank, count in counts.items() if count == 2]
    if len(pair_ranks) == 2:
        high_pair, low_pair = sorted(pair_ranks, reverse=True)
        kicker = max(rank for rank in ranks if rank not in pair_ranks)
        return HandRank(HandCategory.TWO_PAIR, (high_pair, low_pair, kicker))

    if len(pair_ranks) == 1:
        pair_rank = pair_ranks[0]
        kickers = tuple(rank for rank in ranks if rank != pair_rank)
        return HandRank(HandCategory.PAIR, (pair_rank, *kickers))

    return HandRank(HandCategory.HIGH_CARD, tuple(ranks))


def _straight_high(ranks: list[int]) -> int | None:
    distinct = sorted(set(ranks), reverse=True)
    if distinct == [14, 5, 4, 3, 2]:
        return 5
    if len(distinct) == 5 and distinct[0] - distinct[-1] == 4:
        return distinct[0]
    return None
