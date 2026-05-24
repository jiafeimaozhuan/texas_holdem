import pytest

from texas_holdem_trainer.domain.actions import ActionType
from texas_holdem_trainer.domain.engine import PokerEngine


def action_by_type(state, action_type: ActionType):
    actions = PokerEngine().legal_actions(state, state.current_actor_seat)
    return next(action for action in actions if action.type is action_type)


def pending_call_all_in_state():
    engine = PokerEngine()
    state = engine.create_table(
        table_id="t1",
        player_names=["Short Button", "Big Blind"],
        human_seat=0,
        starting_stack=100,
        small_blind=5,
        big_blind=10,
        seed=11,
    )
    state.players[0].stack = 15
    engine.start_hand(state)
    engine.apply_action(state, 0, ActionType.ALL_IN, amount=10)
    return engine, state


def short_player_facing_large_bet_state():
    engine = PokerEngine()
    state = engine.create_table(
        table_id="t1",
        player_names=["Short", "Caller", "Bettor"],
        human_seat=0,
        starting_stack=100,
        small_blind=5,
        big_blind=10,
        seed=13,
    )
    engine.start_hand(state)
    player = state.players[0]
    player.stack = 25
    player.street_bet = 0
    player.total_committed = 0
    player.all_in = False
    state.players[1].stack = 100
    state.players[1].all_in = False
    state.players[2].stack = 100
    state.players[2].street_bet = 75
    state.current_bet = 75
    state.min_raise = 50
    state.current_actor_seat = 0
    return engine, state


def insufficient_all_in_after_prior_call_state():
    engine = PokerEngine()
    state = engine.create_table(
        table_id="t1",
        player_names=["Caller", "Short Small", "Big Blind"],
        human_seat=0,
        starting_stack=100,
        small_blind=5,
        big_blind=10,
        seed=17,
    )
    state.players[1].stack = 12
    engine.start_hand(state)

    engine.apply_action(state, 0, ActionType.CALL)
    engine.apply_action(state, 1, ActionType.ALL_IN, amount=7)
    engine.apply_action(state, 2, ActionType.CALL)

    return engine, state


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


def test_pending_call_against_all_in_only_exposes_fold_and_call() -> None:
    engine, state = pending_call_all_in_state()

    legal = engine.legal_actions(state, 1)
    types = {action.type for action in legal}

    assert types == {ActionType.FOLD, ActionType.CALL}
    call = next(action for action in legal if action.type is ActionType.CALL)
    assert call.min_amount == call.max_amount == 5


@pytest.mark.parametrize("action", [ActionType.RAISE, ActionType.ALL_IN])
def test_pending_call_against_all_in_rejects_uncallable_extra_chips(
    action: ActionType,
) -> None:
    engine, state = pending_call_all_in_state()
    amount = state.players[1].stack if action is ActionType.ALL_IN else 20

    with pytest.raises(ValueError, match="uncallable"):
        engine.apply_action(state, 1, action, amount=amount)

    assert state.players[1].stack == 90
    assert state.players[1].street_bet == 10


def test_short_player_facing_bet_cannot_raise_but_can_move_all_in() -> None:
    engine, state = short_player_facing_large_bet_state()

    legal = engine.legal_actions(state, 0)
    types = {action.type for action in legal}

    assert ActionType.RAISE not in types
    assert {ActionType.FOLD, ActionType.CALL, ActionType.ALL_IN} <= types

    with pytest.raises(ValueError, match="minimum raise"):
        engine.apply_action(state, 0, ActionType.RAISE, amount=25)

    engine.apply_action(state, 0, ActionType.ALL_IN, amount=25)

    assert state.players[0].all_in is True
    assert state.players[0].street_bet == 25
    assert state.hand_history[-1]["action"] == "all_in"


def test_insufficient_all_in_does_not_reopen_raise_to_prior_caller() -> None:
    engine, state = insufficient_all_in_after_prior_call_state()

    assert state.current_actor_seat == 0
    assert state.current_bet == 12
    assert state.min_raise == 10
    assert state.players[0].acted_this_street is True

    legal = engine.legal_actions(state, 0)
    types = {action.type for action in legal}

    assert types == {ActionType.FOLD, ActionType.CALL}
    call = next(action for action in legal if action.type is ActionType.CALL)
    assert call.min_amount == call.max_amount == 2

    with pytest.raises(ValueError, match="reopened"):
        engine.apply_action(state, 0, ActionType.RAISE, amount=20)

    with pytest.raises(ValueError, match="reopened"):
        engine.apply_action(state, 0, ActionType.ALL_IN, amount=90)


def test_full_all_in_raise_reopens_action_to_prior_caller() -> None:
    engine = PokerEngine()
    state = engine.create_table(
        table_id="t1",
        player_names=["Caller", "Full Raise Small", "Big Blind"],
        human_seat=0,
        starting_stack=100,
        small_blind=5,
        big_blind=10,
        seed=19,
    )
    state.players[1].stack = 25
    engine.start_hand(state)

    engine.apply_action(state, 0, ActionType.CALL)
    engine.apply_action(state, 1, ActionType.ALL_IN, amount=20)
    engine.apply_action(state, 2, ActionType.CALL)

    assert state.current_actor_seat == 0
    assert state.current_bet == 25
    assert state.min_raise == 15
    assert state.players[0].acted_this_street is False

    legal = engine.legal_actions(state, 0)
    types = {action.type for action in legal}

    assert {ActionType.FOLD, ActionType.CALL, ActionType.RAISE, ActionType.ALL_IN} <= types
