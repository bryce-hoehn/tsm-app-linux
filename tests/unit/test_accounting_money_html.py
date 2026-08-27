"""money_html: the gold/silver/copper split shown across the dashboard."""

from __future__ import annotations

from tsm.ui.views.accounting_dashboard import money_html

_GOLD = "#ffd100"
_POSITIVE = "#4caf50"
_NEGATIVE = "#f44336"


def test_splits_into_gold_silver_copper():
    """121937820 copper is the "12,193g 78s 20c" from the design."""
    html = money_html(121_937_820)

    assert "12,193g" in html
    assert "78s" in html
    assert "20c" in html


def test_units_keep_their_own_colours():
    html = money_html(10_101)

    assert f'color:{_GOLD}">1g' in html
    assert "#c7c7c7" in html  # silver
    assert "#cd7f32" in html  # copper


def test_untinted_amounts_stay_gold_even_when_negative():
    """Headline figures are not profit, so they are not colour coded."""
    assert f'color:{_GOLD}">-5g' in money_html(-50_000)


def test_tinted_amounts_are_coloured_by_sign():
    assert f'color:{_POSITIVE}">' in money_html(50_000, tint=True)
    assert f'color:{_NEGATIVE}">-' in money_html(-50_000, tint=True)


def test_signed_positive_values_get_a_plus():
    assert ">+5g" in money_html(50_000, signed=True, tint=True)


def test_zero_gets_no_sign():
    html = money_html(0, signed=True, tint=True)

    assert ">0g" in html
    assert "+" not in html


def test_known_non_item_types_get_a_fitting_icon():
    """Repair Bill and friends carry no item id, so they need a stand-in icon."""
    from tsm.ui.views.accounting_dashboard import icon_slug_for_non_item

    assert icon_slug_for_non_item("Repair Bill") == "trade_blacksmithing"
    assert icon_slug_for_non_item("Postage") == "inv_letter_15"
    assert icon_slug_for_non_item("Money Transfer") == "inv_misc_coin_02"


def test_non_item_lookup_ignores_case_and_padding():
    from tsm.ui.views.accounting_dashboard import icon_slug_for_non_item

    assert icon_slug_for_non_item("  repair bill  ") == "trade_blacksmithing"
    assert icon_slug_for_non_item("MONEY TRANSFER") == "inv_misc_coin_02"


def test_an_unknown_type_still_gets_an_icon():
    """A type TSM adds later must not leave an empty frame."""
    from tsm.ui.views.accounting_dashboard import icon_slug_for_non_item

    assert icon_slug_for_non_item("Some Future Type") == "inv_misc_questionmark"
    assert icon_slug_for_non_item("") == "inv_misc_questionmark"
