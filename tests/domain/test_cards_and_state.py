import pytest

from texas_holdem_trainer.domain.actions import ActionType, LegalAction
from texas_holdem_trainer.domain.cards import Deck, Rank, Suit
from texas_holdem_trainer.domain.state import GameState, PlayerState, Street


def test_deck_has_52_unique_cards():
    deck = Deck.new_shuffled(seed=7)
    cards = deck.cards
    assert len(cards) == 52
    assert len(set(cards)) == 52


def test_deal_removes_cards_from_deck():
    deck = Deck.new_shuffled(seed=7)
    first = deck.deal(2)
    second = deck.deal(3)
    assert len(first) == 2
    assert len(second) == 3
    assert len(deck.cards) == 47
    assert set(first).isdisjoint(second)


def test_player_state_tracks_bet_and_stack():
    player = PlayerState(seat=0, name="Hero", stack=1000, is_human=True)
    player.commit_chips(25)
    assert player.stack == 975
    assert player.street_bet == 25
    assert player.total_committed == 25


def test_player_state_rejects_non_integer_chip_amount_without_mutation():
    player = PlayerState(seat=0, name="Hero", stack=1000, is_human=True)
    before = (player.stack, player.street_bet, player.total_committed, player.all_in)

    with pytest.raises(TypeError):
        player.commit_chips(1.5)

    assert (player.stack, player.street_bet, player.total_committed, player.all_in) == before


def test_game_state_active_players_excludes_folded_and_busted():
    players = [
        PlayerState(seat=0, name="Hero", stack=1000, is_human=True),
        PlayerState(seat=1, name="Bot", stack=0, folded=True),
    ]
    state = GameState(
        table_id="t1",
        players=players,
        dealer_seat=0,
        small_blind=10,
        big_blind=20,
    )
    assert state.street == Street.WAITING
    assert [p.name for p in state.players_in_hand()] == ["Hero"]


def test_legal_action_represents_amount_bounds():
    action = LegalAction(type=ActionType.RAISE, min_amount=60, max_amount=300)
    assert action.type is ActionType.RAISE
    assert action.min_amount == 60
    assert action.max_amount == 300


@pytest.mark.parametrize(
    ("min_amount", "max_amount"),
    [
        (0.5, 100),
        (0, 100.5),
    ],
)
def test_legal_action_rejects_fractional_amount_bounds(min_amount, max_amount):
    with pytest.raises(TypeError):
        LegalAction(type=ActionType.RAISE, min_amount=min_amount, max_amount=max_amount)


@pytest.mark.parametrize(
    ("min_amount", "max_amount"),
    [
        (False, 100),
        (0, True),
    ],
)
def test_legal_action_rejects_bool_amount_bounds(min_amount, max_amount):
    with pytest.raises(TypeError):
        LegalAction(type=ActionType.RAISE, min_amount=min_amount, max_amount=max_amount)


@pytest.mark.parametrize(
    ("min_amount", "max_amount"),
    [
        (-1, 100),
        (0, -1),
    ],
)
def test_legal_action_rejects_negative_amount_bounds(min_amount, max_amount):
    with pytest.raises(ValueError):
        LegalAction(type=ActionType.RAISE, min_amount=min_amount, max_amount=max_amount)


def test_legal_action_rejects_min_amount_greater_than_max_amount():
    with pytest.raises(ValueError):
        LegalAction(type=ActionType.RAISE, min_amount=101, max_amount=100)
