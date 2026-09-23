"""Accounting aggregation: gold history merging and per-item totals."""

from __future__ import annotations

from tsm.ui.views._accounting_stats import (
    ALL_CHARACTERS,
    GoldPoint,
    build_stats,
    characters_for_realm,
    collect_gold_logs,
    merge_gold_logs,
    parse_gold_log,
)

DAY = 86400


def row(label, item, copper, ts=0, player="Auctoria", qty=1):
    return {
        "label": label,
        "item": item,
        "qty": qty,
        "copper": copper,
        "timestamp": ts,
        "player": player,
    }


# ── gold log parsing ──────────────────────────────────────────────────


def test_parse_gold_log_scales_minutes_to_seconds():
    points = parse_gold_log("minute,copper\\n100,5000\\n101,7000")

    assert points == [GoldPoint(6000, 5000), GoldPoint(6060, 7000)]


def test_parse_gold_log_tolerates_junk_and_sorts():
    points = parse_gold_log("minute,copper\\n200,20\\nbad,row\\n100,10")

    assert [p.timestamp for p in points] == [6000, 12000]


def test_parse_gold_log_rejects_unexpected_headers():
    assert parse_gold_log("when,howmuch\\n100,5000") == []
    assert parse_gold_log("") == []


# ── merging across characters ─────────────────────────────────────────


def test_merge_forward_fills_each_character():
    """A character keeps its last balance between its own log entries."""
    a = [GoldPoint(0, 100), GoldPoint(200, 300)]
    b = [GoldPoint(100, 50)]

    merged = merge_gold_logs([a, b])

    assert merged == [
        GoldPoint(0, 100),  # only a has logged
        GoldPoint(100, 150),  # a forward filled at 100, plus b
        GoldPoint(200, 350),  # a updated, b forward filled
    ]


def test_merge_ignores_a_character_before_its_first_entry():
    """A newly created character must not look like it always held its balance."""
    old = [GoldPoint(0, 1000), GoldPoint(500, 1000)]
    new = [GoldPoint(500, 7)]

    merged = merge_gold_logs([old, new])

    assert merged == [GoldPoint(0, 1000), GoldPoint(500, 1007)]


def test_merge_handles_no_logs():
    assert merge_gold_logs([]) == []
    assert merge_gold_logs([[], []]) == []


# ── selecting logs out of SavedVariables ──────────────────────────────


def _sv():
    return {
        "s@Auctoria - Alliance - Tarren Mill@internalData@goldLog": "minute,copper\\n1,100",
        "s@Aimbabe - Alliance - Tarren Mill@internalData@goldLog": "minute,copper\\n1,200",
        "s@Someone - Horde - Other Realm@internalData@goldLog": "minute,copper\\n1,999",
        "g@ @internalData@warbankGoldLog": "minute,copper\\n1,50",
        "f@internalData@guildGoldLog": "minute,copper\\n1,70",
        "s@Auctoria - Alliance - Tarren Mill@internalData@goldLogLastUpdate": "123",
    }


def test_collect_takes_only_the_selected_realm():
    logs = collect_gold_logs(_sv(), "Tarren Mill", ALL_CHARACTERS)

    assert sorted(p[0].copper for p in logs) == [50, 70, 100, 200]


def test_collect_narrows_to_one_player_and_drops_shared_scopes():
    """Warbank and guild gold belongs to no character, so a player view excludes it."""
    logs = collect_gold_logs(_sv(), "Tarren Mill", "Auctoria")

    assert [p[0].copper for p in logs] == [100]


def test_characters_for_realm_lists_names_only():
    assert characters_for_realm(_sv(), "Tarren Mill") == ["Aimbabe", "Auctoria"]


# ── headline figures ──────────────────────────────────────────────────


def test_totals_and_daily_averages_divide_by_days_spanned():
    rows = [
        row("Sales", "i:1", 400_000, ts=0),
        row("Purchases", "i:2", -100_000, ts=DAY),
    ]

    stats = build_stats(rows, [], 0, 4 * DAY)

    assert (stats.earned, stats.spent, stats.profit) == (400_000, 100_000, 300_000)
    assert (stats.avg_earned, stats.avg_spent, stats.avg_profit) == (100_000, 25_000, 75_000)


def test_a_range_shorter_than_a_day_still_divides_by_one():
    stats = build_stats([row("Sales", "i:1", 500)], [], 0, 3600)

    assert stats.avg_earned == 500


def test_high_low_come_from_the_gold_series():
    series = [GoldPoint(0, 10), GoldPoint(DAY, 900), GoldPoint(2 * DAY, 400)]

    stats = build_stats([], series, 0, 2 * DAY)

    assert (stats.high, stats.low) == (900, 10)
    assert stats.gold_series == tuple(series)


def test_top_sale_and_purchase_are_single_largest_transactions():
    rows = [
        row("Sales", "i:1", 300),
        row("Sales", "i:2", 900),
        row("Purchases", "i:3", -700),
        row("Purchases", "i:4", -200),
    ]

    stats = build_stats(rows, [], 0, DAY)

    assert stats.top_sale == 900
    assert stats.top_purchase == 700  # reported as a magnitude


def test_daily_counts_are_transactions_per_day():
    rows = [row("Sales", "i:1", 10) for _ in range(20)]
    rows += [row("Purchases", "i:2", -10) for _ in range(6)]

    stats = build_stats(rows, [], 0, 2 * DAY)

    assert stats.daily_sales == 10
    assert stats.daily_purchases == 3


# ── per item totals ───────────────────────────────────────────────────


def test_item_variants_collapse_onto_the_base_item_string():
    rows = [
        row("Sales", "i:22449:0:0:0", 500),
        row("Purchases", "i:22449", -200),
    ]

    stats = build_stats(rows, [], 0, DAY)

    assert len(stats.top_items) == 1
    only = stats.top_items[0]
    assert (only.item_id, only.earned, only.spent, only.profit) == ("i:22449", 500, 200, 300)


def test_top_items_are_ordered_by_money_moved_not_profit():
    """Matches the design: a high volume loss ranks above a small quiet gain."""
    rows = [
        row("Sales", "i:big", 100),
        row("Purchases", "i:big", -900),
        row("Sales", "i:small", 300),
    ]

    stats = build_stats(rows, [], 0, DAY)

    assert [t.item_id for t in stats.top_items] == ["i:big", "i:small"]
    assert stats.top_items[0].profit == -800


def test_top_labels_pick_the_leader_of_each_column():
    rows = [
        row("Sales", "i:earner", 900),
        row("Purchases", "i:sink", -700),
    ]

    stats = build_stats(rows, [], 0, DAY)

    assert stats.top_earned == "i:earner"
    assert stats.top_spent == "i:sink"
    assert stats.top_profit == "i:earner"


def test_empty_input_is_all_zeroes():
    stats = build_stats([], [], 0, DAY)

    assert (stats.earned, stats.spent, stats.profit, stats.high, stats.low) == (0, 0, 0, 0, 0)
    assert stats.top_items == ()
    assert stats.top_earned == ""


def test_every_traded_item_is_listed_by_default():
    """The table replaces the old transaction list, so nothing is truncated."""
    rows = [row("Sales", f"i:{i}", 100 + i) for i in range(30)]

    stats = build_stats(rows, [], 0, DAY)

    assert len(stats.top_items) == 30
    assert stats.top_items[0].item_id == "i:29"  # largest volume first


def test_top_n_caps_the_list_when_asked():
    rows = [row("Sales", f"i:{i}", 100 + i) for i in range(30)]

    stats = build_stats(rows, [], 0, DAY, top_n=5)

    assert len(stats.top_items) == 5
