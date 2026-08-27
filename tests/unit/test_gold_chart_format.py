"""Gold formatting used by the chart axis and its hover readout."""

from __future__ import annotations

from tsm.ui.components._gold_format import RANGES, format_gold_full, format_gold_short


def test_short_format_switches_to_kilogold():
    assert format_gold_short(48_000_000) == "4.8kg"
    assert format_gold_short(5_850_000_000) == "585.0kg"


def test_short_format_keeps_plain_gold_below_a_thousand():
    assert format_gold_short(9_990_000) == "999g"
    assert format_gold_short(10_000) == "1g"


def test_short_format_falls_back_to_copper_under_one_gold():
    assert format_gold_short(0) == "0c"
    assert format_gold_short(500) == "500c"


def test_full_format_splits_gold_silver_copper():
    assert format_gold_full(26_470_000) == "2,647g 00s 00c"
    assert format_gold_full(1_234_567) == "123g 45s 67c"


def test_full_format_pads_silver_and_copper():
    assert format_gold_full(10_005) == "1g 00s 05c"


def test_full_format_marks_a_negative_balance():
    assert format_gold_full(-1_234_567) == "-123g 45s 67c"


def test_ranges_offer_all_last():
    labels = [label for label, _ in RANGES]

    assert labels == ["1D", "1W", "1M", "3M", "6M", "1Y", "2Y", "All"]
    assert RANGES[-1][1] is None  # "All" means no cutoff
    assert [days for _, days in RANGES[:-1]] == [1, 7, 30, 90, 180, 365, 730]
