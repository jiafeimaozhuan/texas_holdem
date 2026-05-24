from typing import get_type_hints

import httpx
import pytest

from texas_holdem_trainer.ai.profiles import BotProfile, BotStyle
from texas_holdem_trainer.ai.providers import HeuristicProvider, LLMProvider
from texas_holdem_trainer.ai.service import AIService, DecisionResult
from texas_holdem_trainer.domain.actions import ActionType, LegalAction
from texas_holdem_trainer.domain.cards import Card, Rank, Suit
from texas_holdem_trainer.domain.engine import PokerEngine


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


def is_backend_legal(result: DecisionResult, legal_actions: list[LegalAction]) -> bool:
    return any(
        action.type is result.action
        and action.min_amount <= result.amount <= action.max_amount
        for action in legal_actions
    )


def preflop_facing_bet_state():
    engine = PokerEngine()
    state = engine.create_table(
        table_id="ai-test",
        player_names=["Alice", "Bob", "Cara"],
        human_seat=0,
        starting_stack=100,
        small_blind=5,
        big_blind=10,
        seed=31,
    )
    engine.start_hand(state)
    return engine, state


@pytest.mark.asyncio
async def test_heuristic_provider_returns_one_backend_legal_action() -> None:
    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, seat)
    provider = HeuristicProvider()
    profile = BotProfile.for_style("bot", BotStyle.GTO_LEANING)

    result = await provider.decide(state, seat, profile, legal_actions)

    assert is_backend_legal(result, legal_actions)
    assert result.reasoning


def test_bot_profile_style_changes_aggression_parameters() -> None:
    conservative = BotProfile.for_style("tight", BotStyle.CONSERVATIVE)
    loose_aggressive = BotProfile.for_style("lag", BotStyle.LOOSE_AGGRESSIVE)
    bluff_heavy = BotProfile.for_style("bluffer", BotStyle.BLUFF_HEAVY)

    assert conservative.aggression < loose_aggressive.aggression
    assert conservative.risk_tolerance < loose_aggressive.risk_tolerance
    assert bluff_heavy.bluff_frequency > loose_aggressive.bluff_frequency


@pytest.mark.asyncio
async def test_ai_service_records_fallback_when_primary_provider_times_out() -> None:
    class TimeoutProvider:
        async def decide(self, state, seat, profile, legal_actions, visible_state=None):
            raise TimeoutError("provider timed out")

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, seat)
    service = AIService(primary_provider=TimeoutProvider())

    result = await service.decide(
        state,
        seat,
        BotProfile.for_style("bot", BotStyle.TIGHT_AGGRESSIVE),
        legal_actions,
    )

    assert result.fallback_used is True
    assert result.fallback_reason == "primary_provider_error: TimeoutError"
    assert is_backend_legal(result, legal_actions)


@pytest.mark.asyncio
async def test_ai_service_records_fallback_when_llm_provider_times_out() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, seat)
    provider = LLMProvider(
        base_url="https://example.test",
        api_key="secret-token",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )
    service = AIService(primary_provider=provider)

    result = await service.decide(
        state,
        seat,
        BotProfile.for_style("bot", BotStyle.TIGHT_AGGRESSIVE, provider="llm"),
        legal_actions,
    )

    assert result.fallback_used is True
    assert result.fallback_reason == "primary_provider_error: ReadTimeout"
    assert is_backend_legal(result, legal_actions)


@pytest.mark.asyncio
async def test_ai_service_records_fallback_when_primary_returns_illegal_action() -> None:
    class IllegalProvider:
        async def decide(self, state, seat, profile, legal_actions, visible_state=None):
            return DecisionResult(
                action=ActionType.CHECK,
                amount=0,
                confidence=0.9,
                reasoning="illegal check while facing a bet",
            )

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, seat)
    service = AIService(primary_provider=IllegalProvider())

    result = await service.decide(
        state,
        seat,
        BotProfile.for_style("bot", BotStyle.TIGHT_AGGRESSIVE),
        legal_actions,
    )

    assert result.fallback_used is True
    assert result.fallback_reason == "illegal_primary_action"
    assert result.action is not ActionType.CHECK
    assert is_backend_legal(result, legal_actions)


@pytest.mark.asyncio
async def test_ai_service_records_fallback_when_llm_provider_returns_illegal_action() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"action":"check","amount":0,'
                                '"confidence":0.92,"reasoning":"not facing a bet"}'
                            )
                        }
                    }
                ]
            },
        )
    )
    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, seat)
    provider = LLMProvider(
        base_url="https://example.test",
        api_key="secret-token",
        model="test-model",
        transport=transport,
    )
    service = AIService(primary_provider=provider)

    result = await service.decide(
        state,
        seat,
        BotProfile.for_style("bot", BotStyle.TIGHT_AGGRESSIVE, provider="llm"),
        legal_actions,
    )

    assert result.fallback_used is True
    assert result.fallback_reason == "illegal_primary_action"
    assert result.action is not ActionType.CHECK
    assert is_backend_legal(result, legal_actions)


@pytest.mark.asyncio
async def test_ai_service_redacts_private_hole_cards_from_primary_reasoning() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"action":"call","amount":10,"confidence":0.81,'
                                '"reasoning":"I hold Kc Kd and can continue."}'
                            )
                        }
                    }
                ]
            },
        )
    )
    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    state.players[seat].hole_cards = [c("Kc"), c("Kd")]
    legal_actions = engine.legal_actions(state, seat)
    provider = LLMProvider(
        base_url="https://example.test",
        api_key="secret-token",
        model="test-model",
        transport=transport,
    )
    service = AIService(primary_provider=provider)

    result = await service.decide(
        state,
        seat,
        BotProfile.for_style("bot", BotStyle.TIGHT_AGGRESSIVE, provider="llm"),
        legal_actions,
    )

    assert result.fallback_used is False
    assert result.action is ActionType.CALL
    assert "Kc" not in result.reasoning
    assert "Kd" not in result.reasoning
    assert "[private cards]" in result.reasoning
    assert "can continue" in result.reasoning


@pytest.mark.asyncio
async def test_ai_service_redacts_private_hole_cards_from_fallback_reasoning() -> None:
    class IllegalProvider:
        async def decide(self, state, seat, profile, legal_actions, visible_state=None):
            return DecisionResult(
                action=ActionType.CHECK,
                amount=0,
                confidence=0.9,
                reasoning="illegal primary",
            )

    class LeakyFallbackProvider:
        async def decide(self, state, seat, profile, legal_actions, visible_state=None):
            call = next(
                action for action in legal_actions if action.type is ActionType.CALL
            )
            return DecisionResult(
                action=ActionType.CALL,
                amount=call.min_amount,
                confidence=0.64,
                reasoning="Fallback says Kc Kd is strong enough to call.",
            )

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    state.players[seat].hole_cards = [c("Kc"), c("Kd")]
    legal_actions = engine.legal_actions(state, seat)
    service = AIService(
        primary_provider=IllegalProvider(),
        fallback_provider=LeakyFallbackProvider(),
    )

    result = await service.decide(
        state,
        seat,
        BotProfile.for_style("bot", BotStyle.TIGHT_AGGRESSIVE),
        legal_actions,
    )

    assert result.fallback_used is True
    assert result.fallback_reason == "illegal_primary_action"
    assert result.action is ActionType.CALL
    assert "Kc" not in result.reasoning
    assert "Kd" not in result.reasoning
    assert "[private cards]" in result.reasoning
    assert "strong enough to call" in result.reasoning


def test_llm_provider_transport_type_accepts_only_async_transport() -> None:
    hints = get_type_hints(LLMProvider.__init__)

    assert hints["transport"] == httpx.AsyncBaseTransport | None


def test_visible_payload_sanitizes_action_history_hidden_cards() -> None:
    engine, state = preflop_facing_bet_state()
    acting_seat = state.current_actor_seat
    opponent_seat = next(
        player.seat for player in state.players if player.seat != acting_seat
    )
    legal_actions = engine.legal_actions(state, acting_seat)
    state.hand_history.append(
        {
            "type": "action",
            "street": "preflop",
            "seat": opponent_seat,
            "action": "call",
            "amount": 10,
            "hole_cards": ["Kc", "Kd"],
            "debug": {"hole_cards": ["Kc", "Kd"]},
        }
    )
    state.hand_history.append(
        {
            "type": "debug_reveal",
            "seat": opponent_seat,
            "hole_cards": ["Qs", "Qh"],
            "cards": ["Qs", "Qh"],
        }
    )
    state.hand_history.append(
        {
            "type": "showdown",
            "ranks": {
                opponent_seat: {
                    "category": "PAIR",
                    "tiebreakers": (13, 12, 8),
                    "hole_cards": ["Kc", "Kd"],
                }
            },
            "winners": [opponent_seat],
        }
    )
    state.hand_history.append({"type": "deal", "cards": ["Qs", "Qh"]})
    service = AIService(primary_provider=HeuristicProvider())

    payload = service.build_visible_payload(state, acting_seat, legal_actions)

    history = payload["action_history"]
    assert history[-4] == {
        "type": "action",
        "street": "preflop",
        "seat": opponent_seat,
        "action": "call",
        "amount": 10,
    }
    assert history[-3] == {"type": "debug_reveal"}
    assert history[-2] == {
        "type": "showdown",
        "ranks": {
            opponent_seat: {
                "category": "PAIR",
                "tiebreakers": (13, 12, 8),
            }
        },
        "winners": [opponent_seat],
    }
    assert history[-1] == {"type": "deal"}
    assert "hole_cards" not in repr(history)
    assert "Kc" not in repr(history)
    assert "Kd" not in repr(history)
    assert "Qs" not in repr(history)
    assert "Qh" not in repr(history)


def test_visible_payload_rejects_card_like_strings_in_known_history_fields() -> None:
    engine, state = preflop_facing_bet_state()
    acting_seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, acting_seat)
    state.players[acting_seat].hole_cards = [c("2c"), c("3d")]
    state.hand_history.extend(
        [
            {"type": "deal", "cards": "Kc Kd"},
            {
                "type": "showdown",
                "ranks": {
                    "Kc Kd": {"category": "PAIR", "tiebreakers": [13]},
                    1: {"category": "PAIR", "tiebreakers": [13]},
                },
                "winners": [1],
            },
            {
                "type": "action",
                "street": "Ah Ad",
                "seat": 1,
                "action": "Kc Kd",
                "amount": 10,
            },
            {"type": "blind", "seat": 1, "blind": "Ah Ad", "amount": 5},
            {
                "type": "settlement",
                "winners": [1],
                "pot": 30,
                "reason": "Kc Kd",
            },
        ]
    )
    service = AIService(primary_provider=HeuristicProvider())

    payload = service.build_visible_payload(state, acting_seat, legal_actions)

    payload_repr = repr(payload)
    assert "Kc Kd" not in payload_repr
    assert "Ah Ad" not in payload_repr
    history = payload["action_history"]
    assert history[-5] == {"type": "deal"}
    assert history[-4] == {
        "type": "showdown",
        "ranks": {1: {"category": "PAIR", "tiebreakers": (13,)}},
        "winners": [1],
    }
    assert history[-3] == {"type": "action", "seat": 1, "amount": 10}
    assert history[-2] == {"type": "blind", "seat": 1, "amount": 5}
    assert history[-1] == {"type": "settlement", "winners": [1], "pot": 30}


def test_visible_payload_does_not_echo_unknown_card_like_history_type() -> None:
    engine, state = preflop_facing_bet_state()
    acting_seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, acting_seat)
    state.hand_history.append({"type": "Kc Kd", "cards": ["Kc", "Kd"]})
    service = AIService(primary_provider=HeuristicProvider())

    payload = service.build_visible_payload(state, acting_seat, legal_actions)

    payload_repr = repr(payload)
    assert "Kc Kd" not in payload_repr
    assert "Kc" not in payload_repr
    assert "Kd" not in payload_repr


@pytest.mark.asyncio
async def test_ai_service_hides_opponent_hole_cards_from_visible_prompt_payload() -> None:
    class CapturingProvider:
        def __init__(self) -> None:
            self.visible_state = None

        async def decide(self, state, seat, profile, legal_actions, visible_state=None):
            self.visible_state = visible_state
            call = next(action for action in legal_actions if action.type is ActionType.CALL)
            return DecisionResult(
                action=ActionType.CALL,
                amount=call.min_amount,
                confidence=0.7,
                reasoning="captured prompt payload",
            )

    engine, state = preflop_facing_bet_state()
    acting_seat = state.current_actor_seat
    opponent_seats = [player.seat for player in state.players if player.seat != acting_seat]
    state.players[acting_seat].hole_cards = [c("Ah"), c("Ad")]
    state.players[opponent_seats[0]].hole_cards = [c("Kc"), c("Kd")]
    state.players[opponent_seats[1]].hole_cards = [c("Qs"), c("Qh")]
    legal_actions = engine.legal_actions(state, acting_seat)
    provider = CapturingProvider()
    service = AIService(primary_provider=provider)

    await service.decide(
        state,
        acting_seat,
        BotProfile.for_style("bot", BotStyle.GTO_LEANING),
        legal_actions,
    )

    payload = provider.visible_state
    assert payload["acting_seat"] == acting_seat
    acting_player = next(
        player for player in payload["players"] if player["seat"] == acting_seat
    )
    opponent_players = [
        player for player in payload["players"] if player["seat"] != acting_seat
    ]
    assert acting_player["hole_cards"] == ["Ah", "Ad"]
    assert all("hole_cards" not in player for player in opponent_players)
    assert "Kc" not in repr(payload)
    assert "Kd" not in repr(payload)
    assert "Qs" not in repr(payload)
    assert "Qh" not in repr(payload)


@pytest.mark.asyncio
async def test_llm_provider_parses_strict_json_response_from_mock_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat/completions"
        assert request.headers["authorization"] == "Bearer secret-token"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"action":"call","amount":10,'
                                '"confidence":0.76,"reasoning":"priced in"}'
                            )
                        }
                    }
                ]
            },
        )

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, seat)
    provider = LLMProvider(
        base_url="https://example.test",
        api_key="secret-token",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )

    result = await provider.decide(
        state,
        seat,
        BotProfile.for_style("bot", BotStyle.GTO_LEANING, provider="llm"),
        legal_actions,
        visible_state={"acting_seat": seat},
    )

    assert result == DecisionResult(
        action=ActionType.CALL,
        amount=10,
        confidence=0.76,
        reasoning="priced in",
    )


@pytest.mark.asyncio
async def test_llm_provider_rejects_json_missing_required_keys() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"action":"call","amount":10,"confidence":0.5}'
                        }
                    }
                ]
            },
        )
    )
    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    provider = LLMProvider(
        base_url="https://example.test",
        api_key="secret-token",
        model="test-model",
        transport=transport,
    )

    with pytest.raises(ValueError, match="required keys"):
        await provider.decide(
            state,
            seat,
            BotProfile.for_style("bot", BotStyle.GTO_LEANING, provider="llm"),
            engine.legal_actions(state, seat),
            visible_state={"acting_seat": seat},
        )
