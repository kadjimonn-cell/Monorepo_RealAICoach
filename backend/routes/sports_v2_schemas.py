from __future__ import annotations

from pydantic import BaseModel, Field


class AudioPlayRequest(BaseModel):
    item_id: str = Field(min_length=4, max_length=64)
    listen_seconds: int = Field(default=0, ge=0, le=86400)
    completed: bool = False
    source: str | None = None


class InboxMarkListenedRequest(BaseModel):
    item_id: str = Field(min_length=4, max_length=64)


class FollowLeagueRequest(BaseModel):
    league_name: str = Field(min_length=2, max_length=120)


class SportsReminderSettingsRequest(BaseModel):
    league_name: str = Field(min_length=2, max_length=120)
    pre_kickoff_15_enabled: bool = False


class SportsBlackoutRulePayload(BaseModel):
    rule_id: str | None = Field(default=None, min_length=4, max_length=80)
    league: str = Field(min_length=2, max_length=120)
    countries: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    start_at: str | None = None
    end_at: str | None = None
    reason: str = Field(default="Regional rights restriction.", min_length=8, max_length=220)
    is_active: bool = True


class SportsCategoryCurationPayload(BaseModel):
    ordered_categories: list[str] = Field(default_factory=list)
    pinned_categories: list[str] = Field(default_factory=list)


class SportsPredictionSubmitRequest(BaseModel):
    challenge_id: str = Field(min_length=8, max_length=120)
    option_key: str = Field(min_length=2, max_length=40)
