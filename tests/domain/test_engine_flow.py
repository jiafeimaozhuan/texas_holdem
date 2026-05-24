from texas_holdem_trainer.domain.actions import ActionType
from texas_holdem_trainer.domain.cards import Card, Rank, Suit
from texas_holdem_trainer.domain.engine import PokerEngine
from texas_holdem_trainer.domain.state import Street


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


def test_start_hand_posts_blinds_deals_hole_cards_and_sets_preflop_order() -> None:
    engine = PokerEngine()
    state = engine.create_table(
        table_id="t1",
        player_names=["A", "B", "C", "D"],
        human_seat=0,
        starting_stack=1_000,
        small_blind=5,
        big_blind=10,
        seed=7,
    )

    engine.start_hand(state)

    assert state.street is Street.PREFLOP
    assert state.dealer_seat == 0
    assert state.current_actor_seat == 3
    assert state.current_bet == 10
    assert state.min_raise == 10
    assert state.pot == 15
    assert [player.stack for player in state.players] == [1_000, 995, 990, 1_000]
    assert [len(player.hole_cards) for player in state.players] == [2, 2, 2, 2]
    assert [entry["type"] for entry in state.hand_history[:4]] == [
        "hand_started",
        "blind",
        "blind",
        "deal",
    ]


def test_hand_progresses_through_streets_and_settles_showdown() -> None:
    engine = PokerEngine()
    state = engine.create_table(
        table_id="t1",
        player_names=["Button", "Big Blind"],
        human_seat=0,
        starting_stack=100,
        small_blind=5,
        big_blind=10,
        seed=11,
    )
    engine.start_hand(state)
    state.players[0].hole_cards = [c("Ah"), c("Ad")]
    state.players[1].hole_cards = [c("Kc"), c("Qd")]
    state.deck.cards = [c(card) for card in ["2c", "7d", "9h", "Ts", "3c"]]

    engine.apply_action(state, 0, ActionType.CALL)
    engine.apply_action(state, 1, ActionType.CHECK)
    assert state.street is Street.FLOP
    assert state.board == [c("2c"), c("7d"), c("9h")]
    assert state.current_actor_seat == 1

    engine.apply_action(state, 1, ActionType.CHECK)
    engine.apply_action(state, 0, ActionType.CHECK)
    assert state.street is Street.TURN
    assert state.board == [c("2c"), c("7d"), c("9h"), c("Ts")]

    engine.apply_action(state, 1, ActionType.CHECK)
    engine.apply_action(state, 0, ActionType.CHECK)
    assert state.street is Street.RIVER
    assert state.board == [c("2c"), c("7d"), c("9h"), c("Ts"), c("3c")]

    engine.apply_action(state, 1, ActionType.CHECK)
    engine.apply_action(state, 0, ActionType.CHECK)

    assert state.street is Street.COMPLETE
    assert state.pot == 0
    assert [player.stack for player in state.players] == [110, 90]
    assert "showdown" in [entry["type"] for entry in state.hand_history]
    assert state.hand_history[-1] == {
        "type": "settlement",
        "winners": [0],
        "pot": 20,
        "share": 20,
        "remainder": 0,
    }


def test_hand_ends_when_all_but_one_player_folds() -> None:
    engine = PokerEngine()
    state = engine.create_table(
        table_id="t1",
        player_names=["A", "B", "C"],
        human_seat=0,
        starting_stack=100,
        small_blind=5,
        big_blind=10,
        seed=13,
    )
    engine.start_hand(state)

    engine.apply_action(state, 0, ActionType.FOLD)
    engine.apply_action(state, 1, ActionType.FOLD)

    assert state.street is Street.COMPLETE
    assert state.current_actor_seat is None
    assert state.pot == 0
    assert [player.stack for player in state.players] == [100, 95, 105]
    assert state.hand_history[-1] == {
        "type": "settlement",
        "winners": [2],
        "pot": 15,
        "reason": "fold",
    }


def test_all_in_showdown_uses_single_simplified_pot() -> None:
    engine = PokerEngine()
    state = engine.create_table(
        table_id="t1",
        player_names=["A", "B", "C"],
        human_seat=0,
        starting_stack=50,
        small_blind=5,
        big_blind=10,
        seed=17,
    )
    engine.start_hand(state)
    state.players[0].hole_cards = [c("Ah"), c("Ad")]
    state.players[1].hole_cards = [c("Kh"), c("Kd")]
    state.players[2].hole_cards = [c("Qh"), c("Qd")]
    state.deck.cards = [c(card) for card in ["2c", "7d", "9h", "Ts", "3c"]]

    engine.apply_action(state, 0, ActionType.ALL_IN, amount=50)
    engine.apply_action(state, 1, ActionType.ALL_IN, amount=45)
    engine.apply_action(state, 2, ActionType.ALL_IN, amount=40)

    assert state.street is Street.COMPLETE
    assert state.board == [c("2c"), c("7d"), c("9h"), c("Ts"), c("3c")]
    assert state.pot == 0
    assert [player.total_committed for player in state.players] == [50, 50, 50]
    assert [player.stack for player in state.players] == [150, 0, 0]
    assert state.hand_history[-1] == {
        "type": "settlement",
        "winners": [0],
        "pot": 150,
        "share": 150,
        "remainder": 0,
    }


def test_heads_up_blinds_all_in_from_start_auto_settles_without_dead_actor() -> None:
    engine = PokerEngine()
    state = engine.create_table(
        table_id="t1",
        player_names=["Button", "Big Blind"],
        human_seat=0,
        starting_stack=5,
        small_blind=5,
        big_blind=10,
        seed=19,
    )

    engine.start_hand(state)

    assert state.street is Street.COMPLETE
    assert state.current_actor_seat is None
    assert state.board and len(state.board) == 5
    assert engine.legal_actions(state, 0) == []
    assert engine.legal_actions(state, 1) == []
    assert state.pot == 0
    assert sum(player.stack for player in state.players) == 10


def test_covered_all_in_auto_runs_remaining_streets_without_uncallable_actions() -> None:
    engine = PokerEngine()
    state = engine.create_table(
        table_id="t1",
        player_names=["Cover", "Short Small", "Short Big"],
        human_seat=0,
        starting_stack=100,
        small_blind=5,
        big_blind=10,
        seed=23,
    )
    state.players[1].stack = 20
    state.players[2].stack = 20
    engine.start_hand(state)
    state.players[0].hole_cards = [c("Ah"), c("Ad")]
    state.players[1].hole_cards = [c("Kh"), c("Kd")]
    state.players[2].hole_cards = [c("Qh"), c("Qd")]
    state.deck.cards = [c(card) for card in ["2c", "7d", "9h", "Ts", "3c"]]

    engine.apply_action(state, 0, ActionType.RAISE, amount=20)
    engine.apply_action(state, 1, ActionType.ALL_IN, amount=15)
    engine.apply_action(state, 2, ActionType.ALL_IN, amount=10)

    assert state.street is Street.COMPLETE
    assert state.current_actor_seat is None
    assert state.board == [c("2c"), c("7d"), c("9h"), c("Ts"), c("3c")]
    assert engine.legal_actions(state, 0) == []
    assert [player.total_committed for player in state.players] == [20, 20, 20]
    assert [player.stack for player in state.players] == [140, 0, 0]
