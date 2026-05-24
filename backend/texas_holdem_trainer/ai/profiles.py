from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BotStyle(str, Enum):
    TIGHT_AGGRESSIVE = "tight_aggressive"
    LOOSE_AGGRESSIVE = "loose_aggressive"
    CONSERVATIVE = "conservative"
    BLUFF_HEAVY = "bluff_heavy"
    GTO_LEANING = "gto_leaning"


@dataclass(frozen=True)
class BotProfile:
    name: str
    style: BotStyle
    provider: str = "heuristic"
    model: str | None = None
    risk_tolerance: float = 0.5
    bluff_frequency: float = 0.1
    aggression: float = 0.5

    @classmethod
    def for_style(
        cls,
        name: str,
        style: BotStyle,
        provider: str = "heuristic",
        model: str | None = None,
    ) -> BotProfile:
        defaults = {
            BotStyle.TIGHT_AGGRESSIVE: {
                "risk_tolerance": 0.45,
                "bluff_frequency": 0.08,
                "aggression": 0.68,
            },
            BotStyle.LOOSE_AGGRESSIVE: {
                "risk_tolerance": 0.72,
                "bluff_frequency": 0.18,
                "aggression": 0.82,
            },
            BotStyle.CONSERVATIVE: {
                "risk_tolerance": 0.22,
                "bluff_frequency": 0.03,
                "aggression": 0.25,
            },
            BotStyle.BLUFF_HEAVY: {
                "risk_tolerance": 0.78,
                "bluff_frequency": 0.36,
                "aggression": 0.74,
            },
            BotStyle.GTO_LEANING: {
                "risk_tolerance": 0.52,
                "bluff_frequency": 0.11,
                "aggression": 0.55,
            },
        }[style]
        return cls(
            name=name,
            style=style,
            provider=provider,
            model=model,
            **defaults,
        )
