"""When the US equity market is actually open.

`is_regular_hours` used to ask only whether it was a weekday between 09:30 and 16:00, which is wrong twice a
year in ways that cost money: on Thanksgiving the market is shut and an order is rejected by the broker after
the pass has already paid for its account read, and on the half-days after Thanksgiving and before Christmas
and Independence Day the close is 13:00, so a 15:00 trading pass is firing into a closed market.

The holidays are computed from the NYSE's own rules rather than listed year by year, so this does not quietly
rot every January. The rules: New Year's Day, MLK Day (3rd Monday of January), Washington's Birthday (3rd
Monday of February), Good Friday, Memorial Day (last Monday of May), Juneteenth (June 19), Independence Day
(July 4), Labor Day (1st Monday of September), Thanksgiving (4th Thursday of November), and Christmas. A
fixed-date holiday falling on Saturday is observed the Friday before, and on Sunday the Monday after.

Not modelled: ad-hoc closures for national days of mourning, which are announced days ahead. Those go in
`no_trading_days` in sandbox_rules.yml, which this module also honours.
"""
from __future__ import annotations

from datetime import date as _date
from datetime import datetime, time, timedelta

REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)


def easter(year: int) -> _date:
    """Anonymous Gregorian algorithm. Good Friday is the only NYSE holiday tied to the lunar calendar."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month, day = divmod(h + ll - 7 * m + 114, 31)
    return _date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> _date:
    """The nth (1-based) `weekday` of a month; Monday is 0."""
    first = _date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> _date:
    nxt = _date(year + (month == 12), (month % 12) + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(d: _date) -> _date:
    """Saturday holidays move back to Friday, Sunday holidays forward to Monday."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def holidays(year: int) -> set[_date]:
    """Every day the NYSE is closed in `year`, weekends aside."""
    return {
        _observed(_date(year, 1, 1)),                      # New Year's Day
        _nth_weekday(year, 1, 0, 3),                       # MLK Day
        _nth_weekday(year, 2, 0, 3),                       # Washington's Birthday
        easter(year) - timedelta(days=2),                  # Good Friday
        _last_weekday(year, 5, 0),                         # Memorial Day
        _observed(_date(year, 6, 19)),                     # Juneteenth
        _observed(_date(year, 7, 4)),                      # Independence Day
        _nth_weekday(year, 9, 0, 1),                       # Labor Day
        _nth_weekday(year, 11, 3, 4),                      # Thanksgiving
        _observed(_date(year, 12, 25)),                    # Christmas
    }


def early_closes(year: int) -> set[_date]:
    """Half days: the market closes at 13:00 ET. The day after Thanksgiving, and Christmas Eve and July 3
    when they fall on a weekday and are not themselves the observed holiday."""
    out = {_nth_weekday(year, 11, 3, 4) + timedelta(days=1)}   # Black Friday
    hols = holidays(year)
    for d in (_date(year, 12, 24), _date(year, 7, 3)):
        if d.weekday() < 5 and d not in hols:
            out.add(d)
    return out


def is_holiday(d: _date, extra: list[str] | None = None) -> bool:
    """A market holiday, or a date listed in `no_trading_days`."""
    if d in holidays(d.year):
        return True
    return str(d.isoformat()) in {str(x) for x in (extra or [])}


def close_time(d: _date) -> time:
    return EARLY_CLOSE if d in early_closes(d.year) else REGULAR_CLOSE


def is_open(now: datetime, extra_closed: list[str] | None = None) -> bool:
    """Is the market open for regular-hours trading at `now`? `now` is read in whatever timezone it carries,
    so callers must pass market time."""
    d = now.date()
    if d.weekday() >= 5 or is_holiday(d, extra_closed):
        return False
    t = now.timetz().replace(tzinfo=None)
    return REGULAR_OPEN <= t <= close_time(d)


def why_closed(now: datetime, extra_closed: list[str] | None = None) -> str | None:
    """A human reason the market is shut at `now`, or None when it is open."""
    d = now.date()
    if d.weekday() >= 5:
        return f"{d:%A}; the market is closed at weekends"
    if d in holidays(d.year):
        return f"{d} is a market holiday"
    if str(d.isoformat()) in {str(x) for x in (extra_closed or [])}:
        return f"{d} is listed in no_trading_days"
    t = now.timetz().replace(tzinfo=None)
    close = close_time(d)
    if t < REGULAR_OPEN:
        return f"before the {REGULAR_OPEN:%H:%M} open"
    if t > close:
        return f"after the {close:%H:%M} close" + (" (half day)" if close == EARLY_CLOSE else "")
    return None
