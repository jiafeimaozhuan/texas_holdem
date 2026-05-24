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
