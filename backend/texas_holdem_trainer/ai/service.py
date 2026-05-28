from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Mapping, Sequence

from texas_holdem_trainer.ai.profiles import BotProfile
from texas_holdem_trainer.ai.providers import AIProvider, DecisionResult, HeuristicProvider
from texas_holdem_trainer.domain.actions import ActionType, LegalAction
from texas_holdem_trainer.domain.cards import Card
from texas_holdem_trainer.domain.state import GameState


_SAFE_BLIND_VALUES = frozenset({"small_blind", "big_blind"})
_SAFE_DEAL_CARD_VALUES = frozenset({"hole"})
_SAFE_ACTION_VALUES = frozenset(action.value for action in ActionType)
_SAFE_STREET_VALUES = frozenset(
    {"preflop", "flop", "turn", "river", "showdown", "complete", "waiting"},
)
_SAFE_SETTLEMENT_REASON_VALUES = frozenset({"fold"})
_SAFE_HAND_RANK_CATEGORIES = frozenset(
    {
        "HIGH_CARD",
        "PAIR",
        "TWO_PAIR",
        "THREE_OF_A_KIND",
        "STRAIGHT",
        "FLUSH",
        "FULL_HOUSE",
        "FOUR_OF_A_KIND",
        "STRAIGHT_FLUSH",
    },
)

logger = logging.getLogger(__name__)


class AIService:
    def __init__(
        self,
        primary_provider: AIProvider,
        fallback_provider: AIProvider | None = None,
        providers: Mapping[str, AIProvider] | None = None,
    ) -> None:
        self.primary_provider = primary_provider
        self.fallback_provider = fallback_provider or HeuristicProvider()
        self.providers = dict(providers or {})

    async def decide(
        self,
        state: GameState,
        seat: int,
        profile: BotProfile,
        legal_actions: Sequence[LegalAction],
    ) -> DecisionResult:
        visible_state = self.build_visible_payload(state, seat, legal_actions)
        provider = self.providers.get(profile.provider, self.primary_provider)
        try:
            result = await provider.decide(
                state,
                seat,
                profile,
                legal_actions,
                visible_state=visible_state,
            )
        except Exception as exc:
            logger.exception(
                "AI primary provider failed table=%s hand=%s seat=%s provider=%s profile=%s",
                state.table_id,
                state.hand_number,
                seat,
                profile.provider,
                profile.name,
            )
            return await self._fallback(
                state,
                seat,
                profile,
                legal_actions,
                visible_state,
                _provider_error_reason(exc),
            )

        if not isinstance(result, DecisionResult) or not self.is_legal_result(
            result,
            legal_actions,
        ):
            return await self._fallback(
                state,
                seat,
                profile,
                legal_actions,
                visible_state,
                "illegal_primary_action",
            )

        return self._with_public_reasoning(
            result,
            profile,
            legal_actions,
            private_cards=state.players[seat].hole_cards,
            fallback_used=False,
            fallback_reason=None,
        )

    def sanitize_public_reasoning(
        self,
        reasoning: str,
        private_cards: Sequence[Card],
    ) -> str:
        sanitized = reasoning
        private_card_strings = [_card_to_string(card) for card in private_cards]
        if len(private_card_strings) == 2:
            first, second = private_card_strings
            sanitized = sanitized.replace(f"{first} {second}", "[private cards]")
            sanitized = sanitized.replace(f"{second} {first}", "[private cards]")
        for card_string in private_card_strings:
            sanitized = sanitized.replace(card_string, "[private card]")
        return sanitized

    def build_visible_payload(
        self,
        state: GameState,
        seat: int,
        legal_actions: Sequence[LegalAction],
    ) -> dict[str, Any]:
        players: list[dict[str, Any]] = []
        for player in state.players:
            player_payload = {
                "seat": player.seat,
                "name": player.name,
                "stack": player.stack,
                "is_human": player.is_human,
                "folded": player.folded,
                "all_in": player.all_in,
                "street_bet": player.street_bet,
                "total_committed": player.total_committed,
                "acted_this_street": player.acted_this_street,
            }
            if player.seat == seat:
                player_payload["hole_cards"] = [
                    _card_to_string(card) for card in player.hole_cards
                ]
            players.append(player_payload)

        return {
            "table_id": state.table_id,
            "hand_number": state.hand_number,
            "acting_seat": seat,
            "dealer_seat": state.dealer_seat,
            "street": state.street.value,
            "board": [_card_to_string(card) for card in state.board],
            "pot": state.pot,
            "current_bet": state.current_bet,
            "min_raise": state.min_raise,
            "small_blind": state.small_blind,
            "big_blind": state.big_blind,
            "players": players,
            "legal_actions": [
                {
                    "action": action.type.value,
                    "min_amount": action.min_amount,
                    "max_amount": action.max_amount,
                }
                for action in legal_actions
            ],
            "action_history": [
                _sanitize_history_entry(entry) for entry in state.hand_history
            ],
        }

    def is_legal_result(
        self,
        result: DecisionResult,
        legal_actions: Sequence[LegalAction],
    ) -> bool:
        if not isinstance(result.action, ActionType):
            return False
        if not isinstance(result.amount, int) or isinstance(result.amount, bool):
            return False
        return any(
            action.type is result.action
            and action.min_amount <= result.amount <= action.max_amount
            for action in legal_actions
        )

    async def _fallback(
        self,
        state: GameState,
        seat: int,
        profile: BotProfile,
        legal_actions: Sequence[LegalAction],
        visible_state: Mapping[str, Any],
        reason: str,
    ) -> DecisionResult:
        fallback = await self.fallback_provider.decide(
            state,
            seat,
            profile,
            legal_actions,
            visible_state=visible_state,
        )
        if not isinstance(fallback, DecisionResult):
            raise ValueError("fallback provider returned a malformed decision")
        if not self.is_legal_result(fallback, legal_actions):
            raise ValueError("fallback provider returned an illegal action")
        return self._with_public_reasoning(
            fallback,
            profile,
            legal_actions,
            private_cards=state.players[seat].hole_cards,
            fallback_used=True,
            fallback_reason=reason,
        )

    def _with_public_reasoning(
        self,
        result: DecisionResult,
        profile: BotProfile,
        legal_actions: Sequence[LegalAction],
        *,
        private_cards: Sequence[Card],
        fallback_used: bool,
        fallback_reason: str | None,
    ) -> DecisionResult:
        return replace(
            result,
            reasoning=self._build_public_reasoning(
                result,
                profile,
                legal_actions,
                fallback_used=fallback_used,
            ),
            source_reasoning=self.sanitize_public_reasoning(
                result.reasoning,
                private_cards,
            ),
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )

    def _build_public_reasoning(
        self,
        result: DecisionResult,
        profile: BotProfile,
        legal_actions: Sequence[LegalAction],
        *,
        fallback_used: bool,
    ) -> str:
        style = _describe_style(profile.style.value)
        action = _describe_action(result)
        context = _describe_legal_context(legal_actions)
        prefix = "主决策不可用，已回退；" if fallback_used else ""
        return f"{prefix}{style}风格选择{action}，{context}。"


def _card_to_string(card: Card) -> str:
    rank_names = {
        2: "2",
        3: "3",
        4: "4",
        5: "5",
        6: "6",
        7: "7",
        8: "8",
        9: "9",
        10: "T",
        11: "J",
        12: "Q",
        13: "K",
        14: "A",
    }
    return f"{rank_names[int(card.rank)]}{card.suit.value}"


def _provider_error_reason(exc: Exception) -> str:
    message = str(exc).strip().replace("\n", " ")
    if len(message) > 180:
        message = f"{message[:177]}..."
    suffix = f": {message}" if message else ""
    return f"primary_provider_error: {type(exc).__name__}{suffix}"


def _describe_action(result: DecisionResult) -> str:
    if result.action is ActionType.FOLD:
        return "弃牌"
    if result.action is ActionType.CHECK:
        return "过牌"
    if result.action is ActionType.CALL:
        return f"跟注 {result.amount}"
    if result.action is ActionType.BET:
        return f"下注 {result.amount}"
    if result.action is ActionType.RAISE:
        return f"加注到 {result.amount}"
    if result.action is ActionType.ALL_IN:
        return f"全下 {result.amount}"
    return result.action.value


def _describe_legal_context(legal_actions: Sequence[LegalAction]) -> str:
    legal_action_names = "、".join(_action_type_label(action.type) for action in legal_actions)
    if any(action.type is ActionType.CALL for action in legal_actions):
        return f"当前面对下注，可选行动为：{legal_action_names}"
    if any(action.type is ActionType.CHECK for action in legal_actions):
        return f"当前无人下注，可选行动为：{legal_action_names}"
    return f"可选行动为：{legal_action_names}"


def _action_type_label(action: ActionType) -> str:
    labels = {
        ActionType.FOLD: "弃牌",
        ActionType.CHECK: "过牌",
        ActionType.CALL: "跟注",
        ActionType.BET: "下注",
        ActionType.RAISE: "加注",
        ActionType.ALL_IN: "全下",
    }
    return labels[action]


def _describe_style(style: str) -> str:
    labels = {
        "tight_aggressive": "紧凶",
        "loose_aggressive": "松凶",
        "conservative": "保守",
        "bluff_heavy": "诈唬型",
        "gto_leaning": "GTO 倾向",
    }
    return labels.get(style, style)


def _sanitize_history_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    event_type = entry.get("type")
    if not isinstance(event_type, str):
        return {}

    if event_type == "hand_started":
        return _copy_typed_fields(
            entry,
            event_type,
            {"hand_number": int, "dealer_seat": int},
        )
    if event_type == "blind":
        return _copy_typed_fields(
            entry,
            event_type,
            {"seat": int, "blind": str, "amount": int},
            allowed_strings={"blind": _SAFE_BLIND_VALUES},
        )
    if event_type == "deal":
        sanitized = {"type": event_type}
        cards = entry.get("cards")
        if isinstance(cards, str) and cards in _SAFE_DEAL_CARD_VALUES:
            sanitized["cards"] = cards
        return sanitized
    if event_type == "action":
        return _copy_typed_fields(
            entry,
            event_type,
            {"street": str, "seat": int, "action": str, "amount": int},
            allowed_strings={
                "street": _SAFE_STREET_VALUES,
                "action": _SAFE_ACTION_VALUES,
            },
        )
    if event_type == "street":
        return _copy_typed_fields(
            entry,
            event_type,
            {"street": str, "board_count": int},
            allowed_strings={"street": _SAFE_STREET_VALUES},
        )
    if event_type == "showdown":
        sanitized = {"type": event_type}
        ranks = _sanitize_showdown_ranks(entry.get("ranks"))
        if ranks:
            sanitized["ranks"] = ranks
        winners = _sanitize_int_list(entry.get("winners"))
        if winners is not None:
            sanitized["winners"] = winners
        return sanitized
    if event_type == "settlement":
        sanitized = _copy_typed_fields(
            entry,
            event_type,
            {"pot": int, "reason": str, "share": int, "remainder": int},
            allowed_strings={"reason": _SAFE_SETTLEMENT_REASON_VALUES},
        )
        winners = _sanitize_int_list(entry.get("winners"))
        if winners is not None:
            sanitized["winners"] = winners
        return sanitized
    if event_type == "debug_reveal":
        return {"type": event_type}

    return {}


def _copy_typed_fields(
    entry: Mapping[str, Any],
    event_type: str,
    fields: Mapping[str, type],
    allowed_strings: Mapping[str, frozenset[str]] | None = None,
) -> dict[str, Any]:
    sanitized: dict[str, Any] = {"type": event_type}
    for field, expected_type in fields.items():
        value = entry.get(field)
        if isinstance(value, expected_type) and not isinstance(value, bool):
            if (
                expected_type is str
                and allowed_strings is not None
                and field in allowed_strings
                and value not in allowed_strings[field]
            ):
                continue
            sanitized[field] = value
    return sanitized


def _sanitize_showdown_ranks(value: Any) -> dict[Any, dict[str, Any]]:
    if not isinstance(value, Mapping):
        return {}

    sanitized: dict[Any, dict[str, Any]] = {}
    for seat, rank in value.items():
        if not isinstance(seat, int) or isinstance(seat, bool):
            continue
        if not isinstance(rank, Mapping):
            continue
        rank_payload: dict[str, Any] = {}
        if rank.get("category") in _SAFE_HAND_RANK_CATEGORIES:
            rank_payload["category"] = rank["category"]
        tiebreakers = _sanitize_int_list(rank.get("tiebreakers"))
        if tiebreakers is not None:
            rank_payload["tiebreakers"] = tuple(tiebreakers)
        if rank_payload:
            sanitized[seat] = rank_payload
    return sanitized


def _sanitize_int_list(value: Any) -> list[int] | None:
    if not isinstance(value, list | tuple):
        return None
    if not all(isinstance(item, int) and not isinstance(item, bool) for item in value):
        return None
    return list(value)
