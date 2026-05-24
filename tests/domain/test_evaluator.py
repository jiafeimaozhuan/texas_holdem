import pytest

from texas_holdem_trainer.domain.cards import Card, Rank, Suit
from texas_holdem_trainer.domain.evaluator import HandCategory, HandRank, evaluate_best


def c(value: str) -> Card:
    rank_map = {
        "2": Rank.TWO,
        "3": Rank.THREE,
        "4": Rank.FOUR,
        "5": Rank.FIVE,
        "6": Rank.SIX,
        "7": Rank.SEVEN,
        "8": Rank.EIGHT,
        "9": Rank.NINE,
        "T": Rank.TEN,
        "J": Rank.JACK,
        "Q": Rank.QUEEN,
        "K": Rank.KING,
        "A": Rank.ACE,
    }
    suit_map = {
        "c": Suit.CLUBS,
        "d": Suit.DIAMONDS,
        "h": Suit.HEARTS,
        "s": Suit.SPADES,
    }

    return Card(rank=rank_map[value[0]], suit=suit_map[value[1]])


def hand(cards: list[str]) -> HandRank:
    return evaluate_best([c(card) for card in cards])


def test_evaluates_high_card_with_top_five_tiebreakers() -> None:
    assert hand(["Ah", "Kd", "9c", "7s", "4h", "3d", "2c"]) == HandRank(
        HandCategory.HIGH_CARD,
        (14, 13, 9, 7, 4),
    )


def test_pair_beats_high_card() -> None:
    pair = hand(["Ah", "Ad", "9c", "7s", "4h"])
    high_card = hand(["Ah", "Kd", "9c", "7s", "4h"])

    assert pair.category == HandCategory.PAIR
    assert pair > high_card


def test_pair_kickers_compare_after_pair_rank() -> None:
    ace_pair_king_kicker = hand(["Ah", "Ad", "Kc", "Qs", "9h"])
    ace_pair_jack_kicker = hand(["Ah", "Ad", "Jc", "Qs", "9h"])

    assert ace_pair_king_kicker.tiebreakers == (14, 13, 12, 9)
    assert ace_pair_jack_kicker.tiebreakers == (14, 12, 11, 9)
    assert ace_pair_king_kicker > ace_pair_jack_kicker


def test_two_pair_tiebreakers_are_high_pair_low_pair_then_kicker() -> None:
    assert hand(["Ah", "Ad", "Kc", "Ks", "9h", "4d"]) == HandRank(
        HandCategory.TWO_PAIR,
        (14, 13, 9),
    )


def test_three_of_a_kind_tiebreakers_are_trip_rank_then_two_kickers() -> None:
    assert hand(["Ah", "Ad", "Ac", "Ks", "Qh", "4d"]) == HandRank(
        HandCategory.THREE_OF_A_KIND,
        (14, 13, 12),
    )


def test_wheel_straight_uses_five_as_high_card() -> None:
    assert hand(["Ah", "2d", "3c", "4s", "5h", "Kd"]) == HandRank(
        HandCategory.STRAIGHT,
        (5,),
    )


def test_regular_straight_chooses_highest_available_straight() -> None:
    assert hand(["9h", "Td", "Jc", "Qs", "Kh", "8d", "7c"]) == HandRank(
        HandCategory.STRAIGHT,
        (13,),
    )


def test_flush_tiebreakers_are_top_five_flush_ranks() -> None:
    assert hand(["Ah", "Jh", "9h", "7h", "4h", "2h", "Kd"]) == HandRank(
        HandCategory.FLUSH,
        (14, 11, 9, 7, 4),
    )


def test_full_house_chooses_highest_trip_and_highest_available_pair() -> None:
    assert hand(["Ah", "Ad", "Ac", "Ks", "Kh", "Kd", "Qh"]) == HandRank(
        HandCategory.FULL_HOUSE,
        (14, 13),
    )


def test_four_of_a_kind_tiebreakers_are_quad_rank_then_kicker() -> None:
    assert hand(["Ah", "Ad", "Ac", "As", "Kh", "Qd"]) == HandRank(
        HandCategory.FOUR_OF_A_KIND,
        (14, 13),
    )


def test_straight_flush_beats_four_of_a_kind() -> None:
    straight_flush = hand(["9h", "Th", "Jh", "Qh", "Kh", "2d", "3c"])
    quads = hand(["Ah", "Ad", "Ac", "As", "Kh", "Qd", "2c"])

    assert straight_flush.category == HandCategory.STRAIGHT_FLUSH
    assert straight_flush > quads


def test_equal_ranked_hands_compare_equal() -> None:
    first = hand(["Ah", "Ad", "Kc", "Qs", "9h", "4d"])
    second = hand(["As", "Ac", "Kd", "Qh", "9c", "3d"])

    assert first == second


@pytest.mark.parametrize(
    "cards",
    [
        ["Ah", "Kd", "9c", "7s"],
        ["Ah", "Kd", "9c", "7s", "4h", "3d", "2c", "As"],
    ],
)
def test_evaluate_best_rejects_card_counts_outside_five_to_seven(
    cards: list[str],
) -> None:
    with pytest.raises(ValueError):
        hand(cards)
