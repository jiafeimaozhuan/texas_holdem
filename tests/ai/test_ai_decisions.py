import asyncio
import logging
from typing import get_type_hints

import httpx
import pytest

from texas_holdem_trainer.ai.profiles import BotProfile, BotStyle
from texas_holdem_trainer.ai.providers import (
    CodexAppServerClient,
    CodexAppServerProvider,
    HeuristicProvider,
    HumanReviewResult,
    LLMProvider,
)
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


@pytest.mark.asyncio
async def test_heuristic_provider_reviews_human_action() -> None:
    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, seat)
    call = next(action for action in legal_actions if action.type is ActionType.CALL)
    provider = HeuristicProvider()

    result = await provider.review_human_action(
        state,
        seat,
        legal_actions,
        ActionType.CALL,
        call.min_amount,
    )

    assert isinstance(result, HumanReviewResult)
    assert 0 <= result.score <= 100
    assert result.label in {"优秀", "可接受", "偏松", "偏紧", "风险过高"}
    assert result.reasoning
    assert result.suggested_action in {action.type for action in legal_actions}


def test_bot_profile_style_changes_aggression_parameters() -> None:
    conservative = BotProfile.for_style("tight", BotStyle.CONSERVATIVE)
    loose_aggressive = BotProfile.for_style("lag", BotStyle.LOOSE_AGGRESSIVE)
    bluff_heavy = BotProfile.for_style("bluffer", BotStyle.BLUFF_HEAVY)

    assert conservative.aggression < loose_aggressive.aggression
    assert conservative.risk_tolerance < loose_aggressive.risk_tolerance
    assert bluff_heavy.bluff_frequency > loose_aggressive.bluff_frequency


@pytest.mark.asyncio
async def test_ai_service_closes_unique_providers_once() -> None:
    class ClosableProvider(HeuristicProvider):
        def __init__(self) -> None:
            self.close_count = 0

        async def close(self) -> None:
            self.close_count += 1

    provider = ClosableProvider()
    service = AIService(
        primary_provider=provider,
        fallback_provider=provider,
        providers={"codex_app": provider},
    )

    await service.close()

    assert provider.close_count == 1


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
    assert result.fallback_reason == "primary_provider_error: TimeoutError: provider timed out"
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
    assert result.fallback_reason == "primary_provider_error: ReadTimeout: read timed out"
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
async def test_ai_service_raises_clean_error_for_malformed_fallback_result() -> None:
    class IllegalProvider:
        async def decide(self, state, seat, profile, legal_actions, visible_state=None):
            return DecisionResult(
                action=ActionType.CHECK,
                amount=0,
                confidence=0.9,
                reasoning="illegal primary",
            )

    class MalformedFallbackProvider:
        async def decide(self, state, seat, profile, legal_actions, visible_state=None):
            return {"action": "call", "amount": 10}

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, seat)
    service = AIService(
        primary_provider=IllegalProvider(),
        fallback_provider=MalformedFallbackProvider(),
    )

    with pytest.raises(ValueError, match="malformed decision"):
        await service.decide(
            state,
            seat,
            BotProfile.for_style("bot", BotStyle.TIGHT_AGGRESSIVE),
            legal_actions,
        )


@pytest.mark.asyncio
async def test_ai_service_replaces_semantic_private_card_primary_reasoning() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"action":"call","amount":10,"confidence":0.81,'
                                '"reasoning":"I have pocket kings, top set, '
                                'and the king of clubs and diamond."}'
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

    public_reasoning = result.reasoning
    assert result.fallback_used is False
    assert result.action is ActionType.CALL
    assert result.reasoning
    assert "跟注" in public_reasoning or "紧凶" in public_reasoning
    assert "pocket kings" not in public_reasoning
    assert "top set" not in public_reasoning
    assert "king of clubs and diamond" not in public_reasoning


@pytest.mark.asyncio
async def test_ai_service_replaces_semantic_private_card_fallback_reasoning() -> None:
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
                reasoning=(
                    "Fallback says pocket kings, top set, and king of clubs "
                    "and diamond are strong enough to call."
                ),
            )

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
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

    public_reasoning = result.reasoning
    assert result.fallback_used is True
    assert result.fallback_reason == "illegal_primary_action"
    assert result.action is ActionType.CALL
    assert result.reasoning
    assert "跟注" in public_reasoning or "紧凶" in public_reasoning
    assert "回退" in public_reasoning
    assert "pocket kings" not in public_reasoning
    assert "top set" not in public_reasoning
    assert "king of clubs and diamond" not in public_reasoning


@pytest.mark.asyncio
async def test_ai_service_public_reasoning_mentions_action_or_style() -> None:
    class PrimaryProvider:
        async def decide(self, state, seat, profile, legal_actions, visible_state=None):
            call = next(
                action for action in legal_actions if action.type is ActionType.CALL
            )
            return DecisionResult(
                action=ActionType.CALL,
                amount=call.min_amount,
                confidence=0.72,
                reasoning="ok",
            )

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, seat)
    service = AIService(primary_provider=PrimaryProvider())

    result = await service.decide(
        state,
        seat,
        BotProfile.for_style("bot", BotStyle.CONSERVATIVE),
        legal_actions,
    )

    public_reasoning = result.reasoning
    assert result.reasoning
    assert "跟注" in public_reasoning or "保守" in public_reasoning
    assert result.reasoning != "ok"


@pytest.mark.asyncio
async def test_ai_service_reviews_human_action_with_configured_provider() -> None:
    class ReviewProvider:
        async def decide(self, state, seat, profile, legal_actions, visible_state=None):
            raise AssertionError("decision path should not be used")

        async def review_human_action(
            self,
            state,
            seat,
            legal_actions,
            action,
            amount,
            visible_state=None,
        ):
            assert visible_state is not None
            return HumanReviewResult(
                score=91,
                label="优秀",
                reasoning="Kc Kd 这里跟注价格合理。",
                suggested_action=action,
                suggested_amount=amount,
                provider="custom",
                model="custom-model",
            )

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    state.players[seat].hole_cards = [c("Kc"), c("Kd")]
    legal_actions = engine.legal_actions(state, seat)
    call = next(action for action in legal_actions if action.type is ActionType.CALL)
    service = AIService(
        primary_provider=HeuristicProvider(),
        fallback_provider=HeuristicProvider(),
        providers={"reviewer": ReviewProvider()},
        reviewer_provider="reviewer",
        reviewer_model="review-model",
    )

    result = await service.review_human_action(
        state,
        seat,
        legal_actions,
        ActionType.CALL,
        call.min_amount,
    )

    assert result.score == 91
    assert result.provider == "reviewer"
    assert result.model == "review-model"
    assert result.fallback_used is False
    assert "Kc" not in result.reasoning
    assert "Kd" not in result.reasoning
    assert "[private cards]" in result.reasoning


@pytest.mark.asyncio
async def test_ai_service_falls_back_when_review_provider_fails() -> None:
    class FailingReviewProvider:
        async def decide(self, state, seat, profile, legal_actions, visible_state=None):
            raise AssertionError("decision path should not be used")

        async def review_human_action(
            self,
            state,
            seat,
            legal_actions,
            action,
            amount,
            visible_state=None,
        ):
            raise TimeoutError("review timed out")

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, seat)
    call = next(action for action in legal_actions if action.type is ActionType.CALL)
    service = AIService(
        primary_provider=HeuristicProvider(),
        fallback_provider=HeuristicProvider(),
        providers={"reviewer": FailingReviewProvider()},
        reviewer_provider="reviewer",
    )

    result = await service.review_human_action(
        state,
        seat,
        legal_actions,
        ActionType.CALL,
        call.min_amount,
    )

    assert result.provider == "heuristic"
    assert result.model == "local"
    assert result.fallback_used is True
    assert result.fallback_reason == "primary_provider_error: TimeoutError: review timed out"
    assert result.reasoning


@pytest.mark.asyncio
async def test_ai_service_falls_back_when_review_provider_suggests_illegal_action() -> None:
    class IllegalReviewProvider:
        async def decide(self, state, seat, profile, legal_actions, visible_state=None):
            raise AssertionError("decision path should not be used")

        async def review_human_action(
            self,
            state,
            seat,
            legal_actions,
            action,
            amount,
            visible_state=None,
        ):
            return HumanReviewResult(
                score=88,
                label="优秀",
                reasoning="非法建议不应被前端展示。",
                suggested_action=ActionType.CHECK,
                suggested_amount=0,
            )

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, seat)
    call = next(action for action in legal_actions if action.type is ActionType.CALL)
    service = AIService(
        primary_provider=HeuristicProvider(),
        fallback_provider=HeuristicProvider(),
        providers={"reviewer": IllegalReviewProvider()},
        reviewer_provider="reviewer",
    )

    result = await service.review_human_action(
        state,
        seat,
        legal_actions,
        ActionType.CALL,
        call.min_amount,
    )

    assert result.provider == "heuristic"
    assert result.fallback_used is True
    assert result.fallback_reason == "invalid_review_result"
    assert result.suggested_action in {action.type for action in legal_actions}


@pytest.mark.asyncio
async def test_ai_service_accepts_no_suggestion_with_zero_amount() -> None:
    class NoSuggestionReviewProvider:
        async def decide(self, state, seat, profile, legal_actions, visible_state=None):
            raise AssertionError("decision path should not be used")

        async def review_human_action(
            self,
            state,
            seat,
            legal_actions,
            action,
            amount,
            visible_state=None,
        ):
            return HumanReviewResult(
                score=89,
                label="优秀",
                reasoning="本次行动合理，无需调整。",
                suggested_action=None,
                suggested_amount=0,
            )

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, seat)
    call = next(action for action in legal_actions if action.type is ActionType.CALL)
    service = AIService(
        primary_provider=HeuristicProvider(),
        fallback_provider=HeuristicProvider(),
        providers={"reviewer": NoSuggestionReviewProvider()},
        reviewer_provider="reviewer",
        reviewer_model="review-model",
    )

    result = await service.review_human_action(
        state,
        seat,
        legal_actions,
        ActionType.CALL,
        call.min_amount,
    )

    assert result.provider == "reviewer"
    assert result.fallback_used is False
    assert result.suggested_action is None
    assert result.suggested_amount is None


@pytest.mark.asyncio
async def test_codex_app_server_provider_reviews_human_action_with_retry() -> None:
    class FakeCodexClient:
        def __init__(self) -> None:
            self.calls = []

        async def complete(
            self,
            *,
            prompt,
            model,
            output_schema,
            thread_key,
            timeout,
        ):
            self.calls.append(
                {
                    "prompt": prompt,
                    "model": model,
                    "output_schema": output_schema,
                    "thread_key": thread_key,
                    "timeout": timeout,
                }
            )
            if len(self.calls) == 1:
                return "not json"
            return (
                '{"score":82,"label":"可接受","reasoning":"跟注价格可接受，'
                '但后续需要控制底池。","suggested_action":"call",'
                '"suggested_amount":10}'
            )

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, seat)
    call = next(action for action in legal_actions if action.type is ActionType.CALL)
    client = FakeCodexClient()
    provider = CodexAppServerProvider(
        model="gpt-5.5",
        timeout=30,
        client=client,
    )

    result = await provider.review_human_action(
        state,
        seat,
        legal_actions,
        ActionType.CALL,
        call.min_amount,
    )

    assert result.score == 82
    assert result.label == "可接受"
    assert result.suggested_action is ActionType.CALL
    assert result.suggested_amount == 10
    assert result.provider == "codex_app"
    assert result.model == "gpt-5.5"
    assert len(client.calls) == 2
    assert client.calls[0]["thread_key"] == "review:gpt-5.5"
    assert client.calls[1]["thread_key"] == "review:gpt-5.5"
    assert client.calls[0]["output_schema"]["required"] == [
        "score",
        "label",
        "reasoning",
        "suggested_action",
        "suggested_amount",
    ]
    assert "上一轮返回无效" in client.calls[1]["prompt"]


@pytest.mark.asyncio
async def test_ai_service_replaces_primary_reasoning_with_public_template() -> None:
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
    assert "[private cards]" not in result.reasoning
    assert "can continue" not in result.reasoning
    assert "跟注" in result.reasoning
    assert result.source_reasoning == "I hold [private cards] and can continue."


@pytest.mark.asyncio
async def test_ai_service_replaces_fallback_reasoning_with_public_template() -> None:
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
    assert "[private cards]" not in result.reasoning
    assert "strong enough to call" not in result.reasoning
    assert "回退" in result.reasoning
    assert "跟注" in result.reasoning


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
async def test_llm_provider_logs_request_and_response_without_api_key(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
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

    with caplog.at_level(logging.INFO, logger="texas_holdem_trainer.ai.providers"):
        await provider.decide(
            state,
            seat,
            BotProfile.for_style("bot", BotStyle.GTO_LEANING, provider="llm"),
            legal_actions,
            visible_state={"acting_seat": seat},
        )

    logs = "\n".join(record.getMessage() for record in caplog.records)
    printed = capsys.readouterr().out
    combined = f"{logs}\n{printed}"
    assert "LLM request" in combined
    assert "LLM response" in combined
    assert "test-model" in combined
    assert '\\"visible_state\\":{\\"acting_seat\\":0}' in combined
    assert '"content":"{\\"action\\":\\"call\\",\\"amount\\":10' in combined
    assert "secret-token" not in combined
    assert "Authorization" not in combined


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


@pytest.mark.asyncio
async def test_codex_app_server_provider_returns_backend_legal_json_decision() -> None:
    class FakeCodexClient:
        def __init__(self) -> None:
            self.prompt = ""
            self.model = ""
            self.output_schema = {}
            self.thread_key = ""
            self.thread_keys = []

        async def complete(
            self,
            *,
            prompt: str,
            model: str,
            output_schema: dict,
            thread_key: str,
            timeout: float,
        ) -> str:
            self.prompt = prompt
            self.model = model
            self.output_schema = output_schema
            self.thread_key = thread_key
            self.thread_keys.append(thread_key)
            return (
                '{"action":"call","amount":10,'
                '"confidence":0.82,"reasoning":"跟注价格合适，保留摊牌权益。"}'
            )

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    legal_actions = engine.legal_actions(state, seat)
    client = FakeCodexClient()
    provider = CodexAppServerProvider(model="gpt-5.5", client=client)

    result = await provider.decide(
        state,
        seat,
        BotProfile.for_style("bot", BotStyle.GTO_LEANING, provider="codex_app"),
        legal_actions,
        visible_state={"acting_seat": seat},
    )

    assert result == DecisionResult(
        action=ActionType.CALL,
        amount=10,
        confidence=0.82,
        reasoning="跟注价格合适，保留摊牌权益。",
    )
    assert client.model == "gpt-5.5"
    assert client.thread_key == "decision:gpt-5.5"
    assert '"visible_state"' in client.prompt
    assert client.output_schema["required"] == [
        "action",
        "amount",
        "confidence",
        "reasoning",
    ]


@pytest.mark.asyncio
async def test_codex_app_server_provider_rejects_non_json_response() -> None:
    class FakeCodexClient:
        async def complete(self, **kwargs):
            return "我会跟注。"

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    provider = CodexAppServerProvider(model="gpt-5.5", client=FakeCodexClient())

    with pytest.raises(ValueError, match="strict JSON"):
        await provider.decide(
            state,
            seat,
            BotProfile.for_style("bot", BotStyle.GTO_LEANING, provider="codex_app"),
            engine.legal_actions(state, seat),
            visible_state={"acting_seat": seat},
        )


@pytest.mark.asyncio
async def test_codex_app_server_provider_retries_invalid_json_response() -> None:
    class FakeCodexClient:
        def __init__(self) -> None:
            self.calls = []

        async def complete(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return "我会跟注。"
            return (
                '{"action":"call","amount":10,'
                '"confidence":0.73,"reasoning":"第二次严格返回 JSON。"}'
            )

    engine, state = preflop_facing_bet_state()
    seat = state.current_actor_seat
    client = FakeCodexClient()
    provider = CodexAppServerProvider(model="gpt-5.5", client=client)

    result = await provider.decide(
        state,
        seat,
        BotProfile.for_style("bot", BotStyle.LOOSE_AGGRESSIVE, provider="codex_app"),
        engine.legal_actions(state, seat),
        visible_state={"acting_seat": seat},
    )

    assert result == DecisionResult(
        action=ActionType.CALL,
        amount=10,
        confidence=0.73,
        reasoning="第二次严格返回 JSON。",
    )
    assert len(client.calls) == 2
    assert client.calls[0]["thread_key"] == "decision:gpt-5.5"
    assert client.calls[1]["thread_key"] == "decision:gpt-5.5"
    assert "上一轮返回无效" in client.calls[1]["prompt"]


@pytest.mark.asyncio
async def test_codex_app_server_client_reads_final_message_from_completed_turn() -> None:
    class FakeCodexClient(CodexAppServerClient):
        def __init__(self) -> None:
            super().__init__(command="codex")
            self.sent_messages = []
            self.read_index = 0
            self.messages = [
                {
                    "id": 1,
                    "result": {
                        "turn": {
                            "id": "turn-1",
                            "items": [],
                            "itemsView": "notLoaded",
                            "status": "inProgress",
                        }
                    },
                },
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turn": {
                            "id": "turn-1",
                            "items": [],
                            "itemsView": "notLoaded",
                            "status": "completed",
                        },
                    },
                },
            ]

        async def _write_message(self, message):
            self.sent_messages.append(message)

        async def _read_message(self):
            message = self.messages[self.read_index]
            self.read_index += 1
            return message

        async def _request(self, method, params):
            assert method == "thread/read"
            assert params == {"threadId": "thread-1", "includeTurns": True}
            return {
                "thread": {
                    "turns": [
                        {
                            "id": "turn-1",
                            "items": [
                                {
                                    "type": "agentMessage",
                                    "text": (
                                        '{"action":"call","amount":10,'
                                        '"confidence":0.5,"reasoning":"测试"}'
                                    ),
                                    "phase": "final_answer",
                                }
                            ],
                            "itemsView": "full",
                            "status": "completed",
                        }
                    ]
                }
            }

    client = FakeCodexClient()

    content = await client._start_turn_and_wait(
        thread_id="thread-1",
        model="gpt-5.5",
        prompt="prompt",
        output_schema={"type": "object"},
    )

    assert content == '{"action":"call","amount":10,"confidence":0.5,"reasoning":"测试"}'
    assert client.sent_messages[0]["method"] == "turn/start"


@pytest.mark.asyncio
async def test_codex_app_server_client_retries_until_turn_items_are_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCodexClient(CodexAppServerClient):
        def __init__(self) -> None:
            super().__init__(command="codex")
            self.reads = 0

        async def _request(self, method, params):
            assert method == "thread/read"
            self.reads += 1
            if self.reads == 1:
                return {
                    "thread": {
                        "turns": [
                            {
                                "id": "turn-1",
                                "items": [],
                                "itemsView": "notLoaded",
                                "status": "completed",
                            }
                        ]
                    }
                }
            return {
                "thread": {
                    "turns": [
                        {
                            "id": "turn-1",
                            "items": [
                                {
                                    "type": "agentMessage",
                                    "text": (
                                        '{"action":"fold","amount":0,'
                                        '"confidence":0.8,"reasoning":"测试"}'
                                    ),
                                    "phase": "final_answer",
                                }
                            ],
                            "itemsView": "full",
                            "status": "completed",
                        }
                    ]
                }
            }

    async def no_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr("texas_holdem_trainer.ai.providers.asyncio.sleep", no_sleep)
    client = FakeCodexClient()

    content = await client._read_completed_turn_message(
        thread_id="thread-1",
        turn_id="turn-1",
    )

    assert content == '{"action":"fold","amount":0,"confidence":0.8,"reasoning":"测试"}'
    assert client.reads == 2


@pytest.mark.asyncio
async def test_codex_app_server_client_restarts_before_context_grows_too_large() -> None:
    class FakeCodexClient(CodexAppServerClient):
        def __init__(self) -> None:
            super().__init__(command="codex", max_turns_per_process=2)
            self.ensure_count = 0
            self.close_count = 0
            self.started_turns = []

        async def _ensure_process(self) -> None:
            self.ensure_count += 1
            self.process = object()

        async def close(self) -> None:
            self.close_count += 1
            self.process = None
            self._thread_ids.clear()
            self._turns_started = 0

        async def _thread_id(self, thread_key, model):
            return f"thread-{thread_key}"

        async def _start_turn_and_wait(self, *, thread_id, model, prompt, output_schema):
            self.started_turns.append((thread_id, prompt))
            return '{"action":"fold","amount":0,"confidence":0.8,"reasoning":"测试"}'

    client = FakeCodexClient()

    for index in range(3):
        await client._complete_locked(
            prompt=f"prompt-{index}",
            model="gpt-5.5",
            output_schema={"type": "object"},
            thread_key="decision:gpt-5.5",
        )

    assert client.close_count == 1
    assert client._turns_started == 1
    assert client.started_turns == [
        ("thread-decision:gpt-5.5", "prompt-0"),
        ("thread-decision:gpt-5.5", "prompt-1"),
        ("thread-decision:gpt-5.5", "prompt-2"),
    ]


@pytest.mark.asyncio
async def test_codex_app_server_client_closes_process_after_timeout() -> None:
    class SlowCodexClient(CodexAppServerClient):
        def __init__(self) -> None:
            super().__init__(command="codex")
            self.close_count = 0

        async def _complete_locked(self, *, prompt, model, output_schema, thread_key):
            await asyncio.sleep(1)
            return "{}"

        async def close(self) -> None:
            self.close_count += 1
            await super().close()

    client = SlowCodexClient()

    with pytest.raises(TimeoutError):
        await client.complete(
            prompt="prompt",
            model="gpt-5.5",
            output_schema={"type": "object"},
            thread_key="decision:gpt-5.5",
            timeout=0.01,
        )

    assert client.close_count == 1


@pytest.mark.asyncio
async def test_codex_app_server_client_closes_process_after_runtime_error() -> None:
    class FailingCodexClient(CodexAppServerClient):
        def __init__(self) -> None:
            super().__init__(command="codex")
            self.close_count = 0

        async def _complete_locked(self, *, prompt, model, output_schema, thread_key):
            raise ValueError("Codex app-server turn/start failed")

        async def close(self) -> None:
            self.close_count += 1
            await super().close()

    client = FailingCodexClient()

    with pytest.raises(ValueError, match="turn/start failed"):
        await client.complete(
            prompt="prompt",
            model="gpt-5.5",
            output_schema={"type": "object"},
            thread_key="decision:gpt-5.5",
            timeout=1,
        )

    assert client.close_count == 1


@pytest.mark.asyncio
async def test_codex_app_server_client_reads_multiline_json_rpc_message() -> None:
    class FakeStdout:
        def __init__(self) -> None:
            self.lines = iter(
                [
                    b'{\n',
                    b'  "id": 7,\n',
                    b'  "result": {\n',
                    b'    "ok": true\n',
                    b'  }\n',
                    b'}\n',
                ]
            )

        async def readline(self):
            return next(self.lines, b"")

    class FakeProcess:
        stdout = FakeStdout()

    client = CodexAppServerClient(command="codex")
    client.process = FakeProcess()

    message = await client._read_message()

    assert message == {"id": 7, "result": {"ok": True}}


@pytest.mark.asyncio
async def test_codex_app_server_client_skips_non_json_stdout_lines() -> None:
    class FakeStdout:
        def __init__(self) -> None:
            self.lines = iter(
                [
                    b"status: starting\n",
                    b'{"id":8,"result":{"ok":true}}\n',
                ]
            )

        async def readline(self):
            return next(self.lines, b"")

    class FakeProcess:
        stdout = FakeStdout()

    client = CodexAppServerClient(command="codex")
    client.process = FakeProcess()

    message = await client._read_message()

    assert message == {"id": 8, "result": {"ok": True}}
