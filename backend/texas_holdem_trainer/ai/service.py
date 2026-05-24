from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from texas_holdem_trainer.ai.profiles import BotProfile
from texas_holdem_trainer.ai.providers import AIProvider, DecisionResult, HeuristicProvider
from texas_holdem_trainer.domain.actions import ActionType, LegalAction
from texas_holdem_trainer.domain.cards import Card
from texas_holdem_trainer.domain.state import GameState


class AIService:
    def __init__(
        self,
        primary_provider: AIProvider,
        fallback_provider: AIProvider | None = None,
    ) -> None:
        self.primary_provider = primary_provider
        self.fallback_provider = fallback_provider or HeuristicProvider()

    async def decide(
        self,
        state: GameState,
        seat: int,
        profile: BotProfile,
        legal_actions: Sequence[LegalAction],
    ) -> DecisionResult:
        visible_state = self.build_visible_payload(state, seat, legal_actions)
        try:
            result = await self.primary_provider.decide(
                state,
                seat,
                profile,
                legal_actions,
                visible_state=visible_state,
            )
        except Exception as exc:
            return await self._fallback(
                state,
                seat,
                profile,
                legal_actions,
                visible_state,
                f"primary_provider_error: {type(exc).__name__}",
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

        return result

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
        if not self.is_legal_result(fallback, legal_actions):
            raise ValueError("fallback provider returned an illegal action")
        return replace(fallback, fallback_used=True, fallback_reason=reason)


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
        )
    if event_type == "deal":
        sanitized = {"type": event_type}
        if isinstance(entry.get("cards"), str):
            sanitized["cards"] = entry["cards"]
        return sanitized
    if event_type == "action":
        return _copy_typed_fields(
            entry,
            event_type,
            {"street": str, "seat": int, "action": str, "amount": int},
        )
    if event_type == "street":
        return _copy_typed_fields(
            entry,
            event_type,
            {"street": str, "board_count": int},
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
        )
        winners = _sanitize_int_list(entry.get("winners"))
        if winners is not None:
            sanitized["winners"] = winners
        return sanitized

    return {"type": event_type}


def _copy_typed_fields(
    entry: Mapping[str, Any],
    event_type: str,
    fields: Mapping[str, type],
) -> dict[str, Any]:
    sanitized: dict[str, Any] = {"type": event_type}
    for field, expected_type in fields.items():
        value = entry.get(field)
        if isinstance(value, expected_type) and not isinstance(value, bool):
            sanitized[field] = value
    return sanitized


def _sanitize_showdown_ranks(value: Any) -> dict[Any, dict[str, Any]]:
    if not isinstance(value, Mapping):
        return {}

    sanitized: dict[Any, dict[str, Any]] = {}
    for seat, rank in value.items():
        if not isinstance(rank, Mapping):
            continue
        rank_payload: dict[str, Any] = {}
        if isinstance(rank.get("category"), str):
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
