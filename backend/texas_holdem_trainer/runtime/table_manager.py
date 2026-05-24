from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from itertools import cycle

from texas_holdem_trainer.ai.profiles import BotProfile, BotStyle
from texas_holdem_trainer.ai.providers import DecisionResult, HeuristicProvider
from texas_holdem_trainer.ai.service import AIService
from texas_holdem_trainer.api.schemas import (
    CardView,
    CoachEventView,
    CreateTableRequest,
    HistoryEventView,
    HistoryResponse,
    LegalActionView,
    PlayerView,
    SubmitActionRequest,
    TableStateResponse,
    UpdateBotsRequest,
)
from texas_holdem_trainer.domain.actions import ActionType, LegalAction
from texas_holdem_trainer.domain.cards import Card
from texas_holdem_trainer.domain.engine import ACTIVE_STREETS, PokerEngine
from texas_holdem_trainer.domain.state import GameState, Street


class TableNotFoundError(KeyError):
    pass


class IllegalActionError(ValueError):
    pass


@dataclass
class TableSession:
    state: GameState
    profiles: dict[int, BotProfile]
    coach_events: list[CoachEventView] = field(default_factory=list)
    subscribers: set[asyncio.Queue[TableStateResponse]] = field(default_factory=set)


class TableManager:
    def __init__(
        self,
        *,
        engine: PokerEngine | None = None,
        ai_service: AIService | None = None,
    ) -> None:
        self.engine = engine or PokerEngine()
        self.ai_service = ai_service or AIService(primary_provider=HeuristicProvider())
        self.tables: dict[str, TableSession] = {}
        self._next_table_number = 1

    def reset(self) -> None:
        self.tables.clear()
        self._next_table_number = 1

    def create_table(self, request: CreateTableRequest) -> TableStateResponse:
        names = self._player_names(request)
        table_id = self._new_table_id()
        state = self.engine.create_table(
            table_id=table_id,
            player_names=names,
            human_seat=request.human_seat,
            starting_stack=request.starting_stack,
            small_blind=request.small_blind,
            big_blind=request.big_blind,
            seed=request.seed,
        )
        self.tables[table_id] = TableSession(
            state=state,
            profiles=self._profiles_for_state(state, request.bot_styles),
        )
        return self.get_state(table_id)

    def _new_table_id(self) -> str:
        table_id = f"table-{self._next_table_number}"
        self._next_table_number += 1
        return table_id

    async def start_hand(self, table_id: str) -> TableStateResponse:
        session = self._session(table_id)
        self.engine.start_hand(session.state)
        session.coach_events.clear()
        await self._advance_ai_turns(session)
        state = self._state_response(session)
        await self.broadcast(table_id, state)
        return state

    def get_state(self, table_id: str) -> TableStateResponse:
        return self._state_response(self._session(table_id))

    async def submit_human_action(
        self,
        table_id: str,
        request: SubmitActionRequest,
    ) -> TableStateResponse:
        session = self._session(table_id)
        state = session.state
        human_seat = self._human_seat(state)
        if state.current_actor_seat != human_seat:
            raise IllegalActionError("it is not the human player's turn")

        legal_actions = self.engine.legal_actions(state, human_seat)
        self._ensure_legal_request(request.action, request.amount, legal_actions)
        self.engine.apply_action(state, human_seat, request.action, request.amount)
        await self._advance_ai_turns(session)
        response = self._state_response(session)
        await self.broadcast(table_id, response)
        return response

    def get_history(self, table_id: str) -> HistoryResponse:
        session = self._session(table_id)
        return HistoryResponse(
            table_id=table_id,
            events=self._history_events(session),
        )

    def update_bots(
        self,
        table_id: str,
        request: UpdateBotsRequest,
    ) -> TableStateResponse:
        session = self._session(table_id)
        if session.state.street not in {Street.WAITING, Street.COMPLETE}:
            raise ValueError("bot profiles can only be updated between hands")
        session.profiles = self._profiles_for_state(session.state, request.bot_styles)
        return self._state_response(session)

    async def subscribe(self, table_id: str) -> asyncio.Queue[TableStateResponse]:
        session = self._session(table_id)
        queue: asyncio.Queue[TableStateResponse] = asyncio.Queue()
        session.subscribers.add(queue)
        await queue.put(self._state_response(session))
        return queue

    def unsubscribe(
        self,
        table_id: str,
        queue: asyncio.Queue[TableStateResponse],
    ) -> None:
        session = self.tables.get(table_id)
        if session is not None:
            session.subscribers.discard(queue)

    async def broadcast(
        self,
        table_id: str,
        state: TableStateResponse | None = None,
    ) -> None:
        session = self._session(table_id)
        payload = state or self._state_response(session)
        for queue in list(session.subscribers):
            await queue.put(payload)

    async def _advance_ai_turns(self, session: TableSession) -> None:
        state = session.state
        while (
            state.street in ACTIVE_STREETS
            and state.current_actor_seat is not None
            and not state.players[state.current_actor_seat].is_human
        ):
            seat = state.current_actor_seat
            legal_actions = self.engine.legal_actions(state, seat)
            if not legal_actions:
                return
            profile = session.profiles[seat]
            decision = await self.ai_service.decide(
                state,
                seat,
                profile,
                legal_actions,
            )
            event = self._coach_event(state, seat, profile, decision)
            self.engine.apply_action(state, seat, decision.action, decision.amount)
            session.coach_events.append(event)

    def _state_response(self, session: TableSession) -> TableStateResponse:
        state = session.state
        human_seat = self._human_seat(state)
        reveal_all = state.street is Street.COMPLETE
        legal_actions = (
            self.engine.legal_actions(state, human_seat)
            if state.current_actor_seat == human_seat
            else []
        )
        return TableStateResponse(
            table_id=state.table_id,
            hand_number=state.hand_number,
            street=state.street.value,
            board=[_card_view(card) for card in state.board],
            pot=state.pot,
            current_bet=state.current_bet,
            min_raise=state.min_raise,
            current_actor_seat=state.current_actor_seat,
            dealer_seat=state.dealer_seat,
            small_blind=state.small_blind,
            big_blind=state.big_blind,
            human_seat=human_seat,
            players=[
                PlayerView(
                    seat=player.seat,
                    name=player.name,
                    stack=player.stack,
                    is_human=player.is_human,
                    folded=player.folded,
                    all_in=player.all_in,
                    street_bet=player.street_bet,
                    total_committed=player.total_committed,
                    hole_cards=(
                        [_card_view(card) for card in player.hole_cards]
                        if reveal_all or player.is_human
                        else None
                    ),
                )
                for player in state.players
            ],
            legal_actions=[_legal_action_view(action) for action in legal_actions],
            coach_events=list(session.coach_events),
            history_events=self._history_events(session),
        )

    def _history_events(self, session: TableSession) -> list[HistoryEventView]:
        events = [HistoryEventView(**entry) for entry in session.state.hand_history]
        events.extend(
            HistoryEventView(**event.model_dump())
            for event in session.coach_events
        )
        return events

    def _coach_event(
        self,
        state: GameState,
        seat: int,
        profile: BotProfile,
        decision: DecisionResult,
    ) -> CoachEventView:
        return CoachEventView(
            hand_number=state.hand_number,
            street=state.street.value,
            seat=seat,
            name=state.players[seat].name,
            style=profile.style,
            action=decision.action,
            amount=decision.amount,
            confidence=decision.confidence,
            reasoning=decision.reasoning,
            fallback_used=decision.fallback_used,
            fallback_reason=decision.fallback_reason,
        )

    def _session(self, table_id: str) -> TableSession:
        try:
            return self.tables[table_id]
        except KeyError as exc:
            raise TableNotFoundError("table not found") from exc

    def _player_names(self, request: CreateTableRequest) -> list[str]:
        if request.player_names is not None:
            return request.player_names

        player_count = request.bot_count + 1
        names: list[str] = []
        for seat in range(player_count):
            if seat == request.human_seat:
                names.append(request.human_name)
            else:
                bot_number = len(names) if seat > request.human_seat else len(names) + 1
                names.append(f"Bot {bot_number}")
        return names

    def _profiles_for_state(
        self,
        state: GameState,
        styles: list[BotStyle],
    ) -> dict[int, BotProfile]:
        default_styles = list(BotStyle)
        style_cycle = cycle(styles or default_styles)
        profiles: dict[int, BotProfile] = {}
        for player in state.players:
            if player.is_human:
                continue
            profiles[player.seat] = BotProfile.for_style(player.name, next(style_cycle))
        return profiles

    def _human_seat(self, state: GameState) -> int:
        for player in state.players:
            if player.is_human:
                return player.seat
        raise ValueError("table has no human player")

    def _ensure_legal_request(
        self,
        action: ActionType,
        amount: int,
        legal_actions: list[LegalAction],
    ) -> None:
        if any(
            legal.type is action
            and legal.min_amount <= amount <= legal.max_amount
            for legal in legal_actions
        ):
            return
        legal_payload = [
            {
                "action": legal.type.value,
                "min_amount": legal.min_amount,
                "max_amount": legal.max_amount,
            }
            for legal in legal_actions
        ]
        raise IllegalActionError(
            f"illegal action {action.value} for amount {amount}; "
            f"legal actions: {legal_payload}"
        )


def _legal_action_view(action: LegalAction) -> LegalActionView:
    return LegalActionView(
        action=action.type,
        min_amount=action.min_amount,
        max_amount=action.max_amount,
    )


def _card_view(card: Card) -> CardView:
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
    rank = rank_names[int(card.rank)]
    return CardView(rank=rank, suit=card.suit.value, code=f"{rank}{card.suit.value}")
