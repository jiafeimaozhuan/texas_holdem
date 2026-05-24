from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from texas_holdem_trainer.ai.profiles import BotStyle
from texas_holdem_trainer.domain.actions import ActionType


class CreateTableRequest(BaseModel):
    player_names: list[str] | None = None
    human_name: str = "Hero"
    bot_count: int = Field(default=3, ge=1, le=8)
    bot_styles: list[BotStyle] = Field(default_factory=list)
    starting_stack: int = Field(default=1_000, gt=0)
    small_blind: int = Field(default=5, gt=0)
    big_blind: int = Field(default=10, gt=0)
    human_seat: int = Field(default=0, ge=0)
    seed: int | None = None


class UpdateBotsRequest(BaseModel):
    bot_styles: list[BotStyle] = Field(default_factory=list)


class SubmitActionRequest(BaseModel):
    action: ActionType
    amount: int = Field(default=0, ge=0)


class CardView(BaseModel):
    rank: str
    suit: str
    code: str


class LegalActionView(BaseModel):
    action: ActionType
    min_amount: int
    max_amount: int


class PlayerView(BaseModel):
    seat: int
    name: str
    stack: int
    is_human: bool
    folded: bool
    all_in: bool
    street_bet: int
    total_committed: int
    hole_cards: list[CardView] | None = None


class CoachEventView(BaseModel):
    type: Literal["ai_decision"] = "ai_decision"
    hand_number: int
    street: str
    seat: int
    name: str
    style: BotStyle
    provider: str
    model: str
    action: ActionType
    amount: int
    confidence: float
    reasoning: str
    fallback_used: bool
    fallback_reason: str | None = None


class HistoryEventView(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    hand_number: int | None = None
    dealer_seat: int | None = None
    street: str | None = None
    seat: int | None = None
    action: str | None = None
    amount: int | None = None
    blind: str | None = None
    cards: str | None = None
    board_count: int | None = None
    winners: list[int] | None = None
    pot: int | None = None
    reason: str | None = None
    share: int | None = None
    remainder: int | None = None
    ranks: dict[int, dict[str, Any]] | None = None
    name: str | None = None
    style: BotStyle | None = None
    provider: str | None = None
    model: str | None = None
    confidence: float | None = None
    reasoning: str | None = None
    fallback_used: bool | None = None
    fallback_reason: str | None = None


class TableStateResponse(BaseModel):
    table_id: str
    hand_number: int
    street: str
    board: list[CardView]
    pot: int
    current_bet: int
    min_raise: int
    current_actor_seat: int | None
    dealer_seat: int
    small_blind: int
    big_blind: int
    human_seat: int
    players: list[PlayerView]
    legal_actions: list[LegalActionView]
    coach_events: list[CoachEventView]
    history_events: list[HistoryEventView]
    ai_provider_status: str


class StartHandResponse(BaseModel):
    table_id: str
    state: TableStateResponse


class HistoryResponse(BaseModel):
    table_id: str
    events: list[HistoryEventView]
