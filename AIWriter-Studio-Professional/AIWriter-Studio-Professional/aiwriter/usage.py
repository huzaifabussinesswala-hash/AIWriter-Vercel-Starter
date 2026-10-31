"""Plan limits and usage accounting. All periods are calendar day/month in UTC."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import repo

# daily limit None means "no daily limit"
PLANS = {
    "free": {"label": "Free", "daily": 5, "monthly": 150},
    "pro": {"label": "Pro", "daily": None, "monthly": 500},
    "business": {"label": "Business", "daily": None, "monthly": 2000},
}


@dataclass(frozen=True)
class Usage:
    plan: str
    plan_label: str
    daily_limit: Optional[int]
    daily_used: int
    daily_remaining: Optional[int]
    daily_percent: int
    monthly_limit: int
    monthly_used: int
    monthly_remaining: int
    monthly_percent: int
    blocked_reason: Optional[str]  # "daily", "monthly" or None
    daily_resets_at: datetime
    monthly_resets_at: datetime

    @property
    def allowed(self) -> bool:
        return self.blocked_reason is None


def period_bounds(now: datetime):
    """Return (day_start, next_day_start, month_start, next_month_start) in UTC."""
    now = now.astimezone(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    return day_start, day_start + timedelta(days=1), month_start, next_month


def _percent(used: int, limit: int) -> int:
    if limit <= 0:
        return 100
    return max(0, min(100, int(round(used * 100 / limit))))


def build_usage(plan: str, daily_used: int, monthly_used: int, now: datetime) -> Usage:
    spec = PLANS.get(plan, PLANS["free"])
    plan = plan if plan in PLANS else "free"
    daily_limit, monthly_limit = spec["daily"], spec["monthly"]
    day_start, day_end, month_start, month_end = period_bounds(now)

    daily_remaining = None if daily_limit is None else max(0, daily_limit - daily_used)
    monthly_remaining = max(0, monthly_limit - monthly_used)

    blocked = None
    if daily_remaining is not None and daily_remaining == 0:
        blocked = "daily"
    elif monthly_remaining == 0:
        blocked = "monthly"

    return Usage(
        plan=plan, plan_label=spec["label"],
        daily_limit=daily_limit, daily_used=daily_used, daily_remaining=daily_remaining,
        daily_percent=0 if daily_limit is None else _percent(daily_used, daily_limit),
        monthly_limit=monthly_limit, monthly_used=monthly_used, monthly_remaining=monthly_remaining,
        monthly_percent=_percent(monthly_used, monthly_limit),
        blocked_reason=blocked, daily_resets_at=day_end, monthly_resets_at=month_end,
    )


def compute_usage(conn, user, now: Optional[datetime] = None) -> Usage:
    now = now or datetime.now(timezone.utc)
    day_start, day_end, month_start, month_end = period_bounds(now)
    daily_used = repo.count_generations(conn, user["id"], day_start, day_end)
    monthly_used = repo.count_generations(conn, user["id"], month_start, month_end)
    return build_usage(user["plan"], daily_used, monthly_used, now)


LIMIT_MESSAGES = {
    "daily": "You have used all of today's generations on your plan. The daily limit resets at 00:00 UTC.",
    "monthly": "You have used all of this month's generations on your plan. The monthly limit resets on the 1st (UTC).",
}
