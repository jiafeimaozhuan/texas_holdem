from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ActionType(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"


@dataclass(frozen=True, slots=True)
class LegalAction:
    type: ActionType
    min_amount: int = 0
    max_amount: int = 0

    def __post_init__(self) -> None:
        for field_name, amount in (
            ("min_amount", self.min_amount),
            ("max_amount", self.max_amount),
        ):
            if not isinstance(amount, int) or isinstance(amount, bool):
                raise TypeError(f"{field_name} must be an integer")
            if amount < 0:
                raise ValueError(f"{field_name} must be non-negative")

        if self.min_amount > self.max_amount:
            raise ValueError("min_amount must be less than or equal to max_amount")
