"""Accounting aggregation: gold history and per-item totals.

Free of Qt imports so the arithmetic can be unit tested without a QApplication,
the same split used by realm_grouping.py. Parsing helpers come from
_accounting_utils.py; this module only aggregates.
"""

from __future__ import annotations

from dataclasses import dataclass

from tsm.ui.views._accounting_utils import _base_item_str, _parse_tsm_csv

ALL_CHARACTERS = "All characters"

# Scopes that hold gold but belong to no single character, so they are only
# counted when no player filter is active.
_SHARED_SCOPES = ("warbank", "guild")


@dataclass(frozen=True)
class GoldPoint:
    timestamp: int  # unix seconds
    copper: int


@dataclass(frozen=True)
class ItemTotals:
    item_id: str  # "i:34113", or the raw string for non-items like "Repair Bill"
    earned: int
    spent: int  # positive magnitude
    profit: int


@dataclass(frozen=True)
class AccountingStats:
    gold_series: tuple[GoldPoint, ...] = ()
    high: int = 0
    low: int = 0
    daily_sales: int = 0
    daily_purchases: int = 0
    top_sale: int = 0
    top_purchase: int = 0
    earned: int = 0
    spent: int = 0
    profit: int = 0
    avg_earned: int = 0
    avg_spent: int = 0
    avg_profit: int = 0
    top_earned: str = ""
    top_spent: str = ""
    top_profit: str = ""
    top_items: tuple[ItemTotals, ...] = ()


def parse_gold_log(csv_string: str) -> list[GoldPoint]:
    """Parse a TSM goldLog value: "minute,copper" rows, minute being unix/60."""
    headers, rows = _parse_tsm_csv(csv_string)
    if not headers:
        return []
    lower = [h.lower().strip() for h in headers]
    try:
        m_idx, c_idx = lower.index("minute"), lower.index("copper")
    except ValueError:
        return []

    points: list[GoldPoint] = []
    for row in rows:
        try:
            points.append(GoldPoint(int(row[m_idx]) * 60, int(row[c_idx])))
        except (ValueError, IndexError):
            continue
    points.sort(key=lambda p: p.timestamp)
    return points


def merge_gold_logs(logs: list[list[GoldPoint]]) -> list[GoldPoint]:
    """Total gold over time across several characters.

    Each character logs only its own balance, at its own irregular times, so the
    total is not a sum of raw rows. At every timestamp any character logged, sum
    each one's most recent value at or before it. A character contributes nothing
    before its first entry, which is what keeps a newly created character from
    appearing to have held its balance all along.
    """
    logs = [log for log in logs if log]
    if not logs:
        return []

    timestamps = sorted({p.timestamp for log in logs for p in log})
    cursors = [0] * len(logs)
    running = [0] * len(logs)
    started = [False] * len(logs)

    merged: list[GoldPoint] = []
    for ts in timestamps:
        for i, log in enumerate(logs):
            while cursors[i] < len(log) and log[cursors[i]].timestamp <= ts:
                running[i] = log[cursors[i]].copper
                started[i] = True
                cursors[i] += 1
        merged.append(GoldPoint(ts, sum(v for v, on in zip(running, started, strict=True) if on)))
    return merged


def collect_gold_logs(
    sv_db: dict[str, object], realm: str, character_filter: str = ALL_CHARACTERS
) -> list[list[GoldPoint]]:
    """Pull the goldLog series for *realm* out of a SavedVariables dict.

    Character logs are keyed "s@<char> - <faction> - <realm>@internalData@goldLog".
    The warbank and guild logs have no character in their key and are included
    only when no character filter is active.
    """
    logs: list[list[GoldPoint]] = []
    for key, value in sv_db.items():
        if not key.endswith("@internalData@goldLog") and "GoldLog" not in key:
            continue
        if not isinstance(value, str) or not value:
            continue

        scope = key.split("@")[0]
        if scope == "s":
            parts = key.split("@")
            if len(parts) < 2:
                continue
            character = parts[1]
            if realm and not character.endswith(realm):
                continue
            if character_filter != ALL_CHARACTERS and not character.startswith(
                f"{character_filter} "
            ):
                continue
        elif any(s in key for s in _SHARED_SCOPES):
            if character_filter != ALL_CHARACTERS:
                continue
        else:
            continue

        points = parse_gold_log(value)
        if points:
            logs.append(points)
    return logs


def characters_for_realm(sv_db: dict[str, object], realm: str) -> list[str]:
    """Character names with a gold log on *realm*, for the player dropdown."""
    names: set[str] = set()
    for key in sv_db:
        if not key.startswith("s@") or not key.endswith("@internalData@goldLog"):
            continue
        parts = key.split("@")
        if len(parts) < 2:
            continue
        character = parts[1]
        if realm and not character.endswith(realm):
            continue
        names.add(character.split(" - ")[0])
    return sorted(names)


def _days_spanned(start_ts: int, end_ts: int) -> int:
    """Whole days covered by the range, never less than one."""
    return max(1, (end_ts - start_ts) // 86400)


def build_stats(
    rows: list[dict],
    gold_series: list[GoldPoint],
    start_ts: int,
    end_ts: int,
    top_n: int | None = None,
) -> AccountingStats:
    """Aggregate unified transaction rows plus a gold series into headline figures.

    *rows* are the dicts produced by _to_unified_rows: label, item, qty, copper,
    timestamp, player. Positive copper is money in, negative is money out.
    """
    earned = sum(r["copper"] for r in rows if r["copper"] > 0)
    spent = -sum(r["copper"] for r in rows if r["copper"] < 0)
    days = _days_spanned(start_ts, end_ts)

    sales = [r for r in rows if r["label"] == "Sales"]
    purchases = [r for r in rows if r["label"] == "Purchases"]

    per_item: dict[str, list[int]] = {}
    for row in rows:
        item_id = _base_item_str(str(row["item"]))
        bucket = per_item.setdefault(item_id, [0, 0])
        if row["copper"] > 0:
            bucket[0] += row["copper"]
        else:
            bucket[1] += -row["copper"]

    totals = [
        ItemTotals(item_id=item_id, earned=e, spent=s, profit=e - s)
        for item_id, (e, s) in per_item.items()
    ]
    # Busiest first: the design orders by how much money moved, not by profit.
    totals.sort(key=lambda t: t.earned + t.spent, reverse=True)

    def _top(key) -> str:
        best = max(totals, key=key, default=None)
        return best.item_id if best is not None and key(best) > 0 else ""

    values = [p.copper for p in gold_series]
    return AccountingStats(
        gold_series=tuple(gold_series),
        high=max(values, default=0),
        low=min(values, default=0),
        daily_sales=len(sales) // days,
        daily_purchases=len(purchases) // days,
        top_sale=max((r["copper"] for r in sales), default=0),
        top_purchase=max((-r["copper"] for r in purchases), default=0),
        earned=earned,
        spent=spent,
        profit=earned - spent,
        avg_earned=earned // days,
        avg_spent=spent // days,
        avg_profit=(earned - spent) // days,
        top_earned=_top(lambda t: t.earned),
        top_spent=_top(lambda t: t.spent),
        top_profit=_top(lambda t: t.profit),
        top_items=tuple(totals if top_n is None else totals[:top_n]),
    )
