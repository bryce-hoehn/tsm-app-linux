"""Money rendering and icon fallbacks for the Accounting tab.

Kept free of PySide6 so the formatting rules can be tested without a display
stack, the same split _accounting_stats uses for the arithmetic.
"""

from __future__ import annotations

GOLD = "#ffd100"
SILVER = "#c7c7c7"
COPPER = "#cd7f32"
POSITIVE = "#4caf50"
NEGATIVE = "#f44336"

# Non-item rows (Repair Bill, Postage, ...) carry no item id and so no icon
# slug. Map the types TSM records to a fitting WoW icon, fetched through the
# same cache as real items. Keys are matched case-insensitively.
_NON_ITEM_ICONS: dict[str, str] = {
    "repair bill": "trade_blacksmithing",
    "postage": "inv_letter_15",
    "money transfer": "inv_misc_coin_02",
    "mail": "inv_letter_15",
    "trade": "inv_misc_gift_01",
    "vendor": "inv_misc_bag_10",
    "merchant": "inv_misc_bag_10",
    "auction": "inv_misc_coin_17",
    "auction deposit": "inv_misc_coin_17",
    "transfer": "inv_misc_coin_02",
    "guild bank": "achievement_guildperk_mobilebanking",
}
# Anything else without an item id still gets a frame with something in it.
_UNKNOWN_ICON = "inv_misc_questionmark"


def money_html(copper: int, signed: bool = False, tint: bool = False) -> str:
    """Gold/silver/copper split with each unit in its own colour.

    *tint* colours the amount by sign, which is what the profit column wants.
    """
    negative = copper < 0
    magnitude = abs(copper)
    gold, silver, copper_rest = magnitude // 10000, magnitude // 100 % 100, magnitude % 100

    sign = "-" if negative else ("+" if signed and magnitude else "")
    amount_color = (NEGATIVE if negative else POSITIVE) if tint else GOLD
    return (
        f'<span style="color:{amount_color}">{sign}{gold:,}g</span> '
        f'<span style="color:{SILVER}">{silver:02d}s</span> '
        f'<span style="color:{COPPER}">{copper_rest:02d}c</span>'
    )


def icon_slug_for_non_item(name: str) -> str:
    """Placeholder icon slug for a transaction type that is not an item."""
    return _NON_ITEM_ICONS.get(name.strip().lower(), _UNKNOWN_ICON)
