from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

import httpx

from texas_holdem_trainer.ai.profiles import BotProfile
from texas_holdem_trainer.domain.actions import ActionType, LegalAction
from texas_holdem_trainer.domain.cards import Card
from texas_holdem_trainer.domain.evaluator import HandCategory, evaluate_best
from texas_holdem_trainer.domain.state import GameState


logger = logging.getLogger(__name__)


def _emit_llm_log(message: str) -> None:
    logger.info(message)
    print(message, flush=True)


@dataclass(frozen=True)
class DecisionResult:
    action: ActionType
    amount: int = 0
    confidence: float = 0.5
    reasoning: str = ""
    source_reasoning: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None


class AIProvider(Protocol):
    async def decide(
        self,
        state: GameState,
        seat: int,
        profile: BotProfile,
        legal_actions: Sequence[LegalAction],
        visible_state: Mapping[str, Any] | None = None,
    ) -> DecisionResult:
        ...


class HeuristicProvider:
    async def decide(
        self,
        state: GameState,
        seat: int,
        profile: BotProfile,
        legal_actions: Sequence[LegalAction],
        visible_state: Mapping[str, Any] | None = None,
    ) -> DecisionResult:
        if not legal_actions:
            raise ValueError("legal_actions must not be empty")

        legal_by_type = {action.type: action for action in legal_actions}
        player = state.players[seat]
        strength = _hand_strength([*player.hole_cards, *state.board])

        if ActionType.CALL in legal_by_type:
            return self._facing_bet_decision(
                state,
                profile,
                legal_by_type,
                strength,
            )

        return self._no_bet_decision(profile, legal_by_type, strength)

    def _facing_bet_decision(
        self,
        state: GameState,
        profile: BotProfile,
        legal_by_type: dict[ActionType, LegalAction],
        strength: float,
    ) -> DecisionResult:
        call_action = legal_by_type[ActionType.CALL]
        call_amount = call_action.min_amount
        pot_after_call = max(1, state.pot + call_amount)
        pot_odds = call_amount / pot_after_call
        continue_threshold = max(0.18, pot_odds - profile.risk_tolerance * 0.15)
        pressure = call_amount / max(1, state.pot + call_amount)

        can_raise = ActionType.RAISE in legal_by_type
        should_pressure = (
            can_raise
            and strength >= 0.68
            and profile.aggression >= 0.55
        ) or (
            can_raise
            and strength >= 0.48
            and profile.aggression + profile.bluff_frequency >= 0.95
        )
        if should_pressure:
            raise_action = legal_by_type[ActionType.RAISE]
            amount = _scaled_amount(raise_action, profile.aggression)
            return DecisionResult(
                action=ActionType.RAISE,
                amount=amount,
                confidence=min(0.95, 0.55 + strength * 0.35),
                reasoning="raising with enough hand strength and profile aggression",
            )

        if strength >= continue_threshold or (strength >= 0.42 and pressure <= 0.28):
            return DecisionResult(
                action=ActionType.CALL,
                amount=call_amount,
                confidence=min(0.9, 0.45 + strength * 0.35),
                reasoning="calling because hand strength or pot odds justify continuing",
            )

        if ActionType.FOLD in legal_by_type:
            return DecisionResult(
                action=ActionType.FOLD,
                confidence=min(0.9, 0.45 + pressure),
                reasoning="folding weak hand against a large price",
            )

        return _first_legal_decision(legal_by_type, "using only available legal action")

    def _no_bet_decision(
        self,
        profile: BotProfile,
        legal_by_type: dict[ActionType, LegalAction],
        strength: float,
    ) -> DecisionResult:
        can_bet = ActionType.BET in legal_by_type
        value_bet = can_bet and strength >= max(0.58, 0.82 - profile.aggression * 0.25)
        pressure_bet = (
            can_bet
            and strength >= 0.44
            and profile.aggression + profile.bluff_frequency >= 1.0
        )
        if value_bet or pressure_bet:
            bet_action = legal_by_type[ActionType.BET]
            amount = _scaled_amount(bet_action, profile.aggression)
            return DecisionResult(
                action=ActionType.BET,
                amount=amount,
                confidence=min(0.9, 0.5 + strength * 0.3),
                reasoning="betting because profile aggression supports pressure",
            )

        if ActionType.CHECK in legal_by_type:
            return DecisionResult(
                action=ActionType.CHECK,
                confidence=0.65,
                reasoning="checking when no bet is faced",
            )

        return _first_legal_decision(legal_by_type, "using first backend legal action")


class LLMProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.transport = transport

    async def decide(
        self,
        state: GameState,
        seat: int,
        profile: BotProfile,
        legal_actions: Sequence[LegalAction],
        visible_state: Mapping[str, Any] | None = None,
    ) -> DecisionResult:
        payload = {
            "model": profile.model or self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Choose exactly one backend-provided Texas Hold'em legal "
                        "action. Return strict JSON only. Write reasoning in Chinese."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "profile": {
                                "name": profile.name,
                                "style": profile.style.value,
                                "risk_tolerance": profile.risk_tolerance,
                                "bluff_frequency": profile.bluff_frequency,
                                "aggression": profile.aggression,
                            },
                            "visible_state": visible_state,
                            "legal_actions": [
                                {
                                    "action": action.type.value,
                                    "min_amount": action.min_amount,
                                    "max_amount": action.max_amount,
                                }
                                for action in legal_actions
                            ],
                            "required_json_schema": {
                                "action": "fold|check|call|bet|raise|all_in",
                                "amount": "integer",
                                "confidence": "number between 0 and 1",
                                "reasoning": "short Chinese string",
                            },
                        },
                        separators=(",", ":"),
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        request_url = f"{self.base_url}/chat/completions"
        _emit_llm_log(
            "LLM request "
            f"url={request_url} "
            f"model={payload['model']} "
            f"payload={json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
        )

        async with httpx.AsyncClient(
            timeout=self.timeout,
            transport=self.transport,
        ) as client:
            response = await client.post(
                request_url,
                json=payload,
                headers=headers,
            )
            _emit_llm_log(
                "LLM response "
                f"url={request_url} "
                f"status={response.status_code} "
                f"body={response.text}"
            )
            response.raise_for_status()

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("LLM response missing message content") from exc
        return self._parse_content(content)

    def _parse_content(self, content: str) -> DecisionResult:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM response content is not strict JSON") from exc

        required_keys = {"action", "amount", "confidence", "reasoning"}
        if not isinstance(parsed, dict):
            raise ValueError("LLM response JSON must be an object")
        if set(parsed) != required_keys:
            raise ValueError("LLM response JSON must contain exactly required keys")

        action_value = parsed["action"]
        amount = parsed["amount"]
        confidence = parsed["confidence"]
        reasoning = parsed["reasoning"]

        if not isinstance(action_value, str):
            raise ValueError("LLM action must be a string")
        try:
            action = ActionType(action_value)
        except ValueError as exc:
            raise ValueError("LLM action is not supported") from exc

        if not isinstance(amount, int) or isinstance(amount, bool):
            raise ValueError("LLM amount must be an integer")
        if (
            not isinstance(confidence, int | float)
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("LLM confidence must be a number between 0 and 1")
        if not isinstance(reasoning, str):
            raise ValueError("LLM reasoning must be a string")

        return DecisionResult(
            action=action,
            amount=amount,
            confidence=float(confidence),
            reasoning=reasoning,
        )


def _scaled_amount(action: LegalAction, aggression: float) -> int:
    span = action.max_amount - action.min_amount
    if span <= 0:
        return action.min_amount
    scale = min(0.35, max(0.0, aggression - 0.5))
    return min(action.max_amount, action.min_amount + int(span * scale))


def _first_legal_decision(
    legal_by_type: dict[ActionType, LegalAction],
    reasoning: str,
) -> DecisionResult:
    action = next(iter(legal_by_type.values()))
    return DecisionResult(
        action=action.type,
        amount=action.min_amount,
        confidence=0.4,
        reasoning=reasoning,
    )


def _hand_strength(cards: Sequence[Card]) -> float:
    if len(cards) >= 5:
        rank = evaluate_best(cards)
        category_scores = {
            HandCategory.HIGH_CARD: 0.26,
            HandCategory.PAIR: 0.48,
            HandCategory.TWO_PAIR: 0.67,
            HandCategory.THREE_OF_A_KIND: 0.76,
            HandCategory.STRAIGHT: 0.84,
            HandCategory.FLUSH: 0.88,
            HandCategory.FULL_HOUSE: 0.94,
            HandCategory.FOUR_OF_A_KIND: 0.98,
            HandCategory.STRAIGHT_FLUSH: 1.0,
        }
        kicker_bonus = min(0.07, sum(rank.tiebreakers[:2]) / 400)
        return min(1.0, category_scores[rank.category] + kicker_bonus)

    if len(cards) < 2:
        return 0.0

    first, second = cards[0], cards[1]
    high_rank = max(int(first.rank), int(second.rank))
    low_rank = min(int(first.rank), int(second.rank))
    suited_bonus = 0.05 if first.suit is second.suit else 0.0
    connected_bonus = 0.04 if high_rank - low_rank <= 1 else 0.0

    if high_rank == low_rank:
        return min(0.9, 0.48 + high_rank / 35)
    broadway_bonus = 0.08 if low_rank >= 10 else 0.0
    ace_bonus = 0.08 if high_rank == 14 else 0.0
    return min(
        0.82,
        0.18 + high_rank / 35 + low_rank / 70 + suited_bonus + connected_bonus
        + broadway_bonus + ace_bonus,
    )
