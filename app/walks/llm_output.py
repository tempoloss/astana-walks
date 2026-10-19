"""The response schema of the generation call (walks.generate): what the model returns for one answer. Code checks
every field afterwards; only `Recommendation` (walks.models) reaches a card."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .models import Confidence


class LLMRec(BaseModel):
    poi_id: str
    why: str = Field(
        description="ONE short sentence (up to 16 words): why this place fits THIS request. No distances, times or "
        "opening hours."
    )
    time_on_site_min: int = Field(description="Reasonable minutes to spend there.")
    what_to_do: str = Field(description="ONE short sentence: a concrete thing to do there.")
    confidence: Confidence
    generated_idea: bool = Field(
        description="true if what_to_do/why go beyond the facts given for this candidate (your own idea)."
    )
    notes: str = Field("", description="Optional caveat, e.g. missing data. Empty string if none.")


class LLMOutput(BaseModel):
    you_want: str = Field(
        "",
        description="ONE short clause, in the answer language, saying in plain words what the user is looking for "
        "(ru: 'Вы ищете, где выпить'; en: 'You are looking for a place for a drink'). No place names, numbers, "
        "hours, weather or advice.",
    )
    recommendations: list[LLMRec] = Field(description="1 to 3 recommendations, best first.")
    opening: str = Field(
        "",
        description="One or two natural sentences opening the reply: the wish in the person's terms, the conditions "
        "when they matter, the first pick by its exact name in «» with one concrete fact. Numbers only from the payload.",
    )
    route_order: list[str] = Field(
        default_factory=list, description="Optional visiting order of poi_ids."
    )
