import pytest

from texas_holdem_trainer.domain.actions import ActionType
from texas_holdem_trainer.domain.engine import PokerEngine


def action_by_type(state, action_type: ActionType):
    actions = PokerEngine().legal_actions(state, state.current_actor_seat)
    return next(action for action in actions if action.type is action_type)


def test_legal_actions_when_facing_bet_include_call_raise_and_all_in() -> None:
    engine = PokerEngine()
    state = engine.create_table(
        table_id="t1",
        player_names=["A", "B", "C"],
        human_seat=0,
        starting_stack=100,
        small_blind=5,
        big_blind=10,
        seed=3,
    )
    engine.start_hand(state)

    legal = engine.legal_actions(state, state.current_actor_seat)
    types = {action.type for action in legal}

    assert {ActionType.FOLD, ActionType.CALL, ActionType.RAISE, ActionType.ALL_IN} <= types
    assert ActionType.CHECK not in types
    raise_action = action_by_type(state, ActionType.RAISE)
    assert raise_action.min_amount == state.current_bet + state.min_raise
    assert raise_action.max_amount == state.players[state.current_actor_seat].stack
    all_in = action_by_type(state, ActionType.ALL_IN)
    assert all_in.min_amount == all_in.max_amount == 100


def test_legal_actions_when_no_bet_faced_include_check_bet_and_all_in() -> None:
    engine = PokerEngine()
    state = engine.create_table(
        table_id="t1",
        player_names=["A", "B", "C"],
        human_seat=0,
        starting_stack=100,
        small_blind=5,
        big_blind=10,
        seed=5,
    )
    engine.start_hand(state)
    engine.apply_action(state, 0, ActionType.CALL)
    engine.apply_action(state, 1, ActionType.CALL)
    engine.apply_action(state, 2, ActionType.CHECK)

    legal = engine.legal_actions(state, state.current_actor_seat)
    types = {action.type for action in legal}

    assert {ActionType.CHECK, ActionType.BET, ActionType.ALL_IN} <= types
    assert ActionType.CALL not in types
    bet = action_by_type(state, ActionType.BET)
    assert bet.min_amount == state.big_blind
    assert bet.max_amount == state.players[state.current_actor_seat].stack


def test_legal_actions_are_empty_for_non_current_actor() -> None:
    engine = PokerEngine()
    state = engine.create_table(
        table_id="t1",
        player_names=["A", "B", "C"],
        human_seat=0,
        starting_stack=100,
        small_blind=5,
        big_blind=10,
        seed=7,
    )
    engine.start_hand(state)

    assert engine.legal_actions(state, 1) == []


def test_apply_action_rejects_out_of_turn_seat() -> None:
    engine = PokerEngine()
    state = engine.create_table(
        table_id="t1",
        player_names=["A", "B", "C"],
        human_seat=0,
        starting_stack=100,
        small_blind=5,
        big_blind=10,
        seed=9,
    )
    engine.start_hand(state)

    with pytest.raises(ValueError, match="not the current actor"):
        engine.apply_action(state, 1, ActionType.FOLD)
