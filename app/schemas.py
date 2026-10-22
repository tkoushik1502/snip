from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class LinkCreate(BaseModel):
    url: HttpUrl = Field(description="The destination URL (http or https).")
    alias: str | None = Field(
        default=None, description="Optional custom code, 3-32 chars of [A-Za-z0-9_-]."
    )
    expires_in_hours: int | None = Field(
        default=None, ge=1, le=24 * 365, description="Optional lifetime of the link."
    )


class LinkOut(BaseModel):
    code: str
    short_url: str
    target_url: str
    created_at: datetime
    expires_at: datetime | None
    click_count: int


class DailyClicks(BaseModel):
    date: str
    clicks: int


class ReferrerCount(BaseModel):
    referrer: str
    clicks: int


class LinkStats(BaseModel):
    link: LinkOut
    total_clicks: int
    clicks_by_day: list[DailyClicks]
    top_referrers: list[ReferrerCount]
