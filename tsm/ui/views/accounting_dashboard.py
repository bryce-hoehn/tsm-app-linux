"""Accounting overview: gold chart, headline figures and top items.

Sits above the transaction filters in the Accounting tab. All arithmetic comes
from _accounting_stats, so this module only renders.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tsm.core.services.icon_cache import IconCache
from tsm.core.services.item_cache import ItemCache
from tsm.ui.components.gold_chart import GoldChart, RangeSelector
from tsm.ui.components.item_icon import item_icon_pixmap
from tsm.ui.views._accounting_format import (
    POSITIVE,
    icon_slug_for_non_item,
    money_html,
)
from tsm.ui.views._accounting_stats import AccountingStats, ItemTotals

_MUTED = "#8a8a8a"
_DIM = "#666666"

ITEM_COL = 1  # the name column, where the hover filter looks for an item id
# Non-items are not loot, so they have no quality. Grey, like a poor item.
_NON_ITEM_QUALITY = 0

_ICON_SIZE = 32
_ROW_HEIGHT = 40
# Cell widgets carry no item size hint, so the money columns get an explicit
# width. Fits "1,071,848g 69s 68c" plus padding.
_MONEY_COL_WIDTH = 170
_CHART_CARD_HEIGHT = 230


def _rich(text: str, align_right: bool = False) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setStyleSheet("background: transparent;")
    if align_right:
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return label


def _caption(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setStyleSheet(
        f"color: {_MUTED}; font-size: 10px; font-weight: bold; background: transparent;"
    )
    return label


def _name_widget(name: str, item_id: str) -> QWidget:
    """Item name over its id, as in the design.

    Transparent to mouse events so the table viewport still sees the hover and
    the WoW tooltip keeps working over these rows.
    """
    widget = QWidget()
    widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    widget.setStyleSheet("background: transparent;")
    box = QVBoxLayout(widget)
    box.setContentsMargins(4, 2, 4, 2)
    box.setSpacing(0)

    title = QLabel(name)
    title.setStyleSheet("color: #ffffff; font-weight: bold; background: transparent;")
    box.addWidget(title)

    # Only real items have an id worth showing. "Money Transfer" and friends
    # would just repeat the name.
    if item_id.startswith("i:"):
        subtitle = QLabel(item_id)
        subtitle.setStyleSheet(f"color: {_DIM}; font-size: 10px; background: transparent;")
        box.addWidget(subtitle)
    return widget


class _Card(QFrame):
    """Panel with the app's card background."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("accounting-card")
        self.setFrameShape(QFrame.Shape.NoFrame)


class AccountingDashboard(QWidget):
    """Chart, headline stats, the three money panels and the top items table."""

    range_changed: Signal = Signal(object)  # days, or None for all

    def __init__(
        self,
        item_cache: ItemCache,
        icon_cache: IconCache,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._item_cache = item_cache
        self._icon_cache = icon_cache
        self._headline: dict[str, QLabel] = {}
        self._panel: dict[str, QLabel] = {}
        self._setup_ui()

    # ── Construction ──────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(8)
        chart_card = self._build_chart_card()
        chart_card.setFixedHeight(_CHART_CARD_HEIGHT)
        vbox.addWidget(chart_card)
        vbox.addWidget(self._build_headline_row())
        vbox.addWidget(self._build_money_panels())
        vbox.addWidget(self._build_top_items(), 1)

    def _build_chart_card(self) -> QWidget:
        card = _Card()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Player gold")
        title.setStyleSheet("font-weight: bold; font-size: 13px; background: transparent;")
        header.addWidget(title)
        self._chart_subtitle = QLabel("")
        self._chart_subtitle.setStyleSheet(
            f"color: {_MUTED}; font-size: 11px; background: transparent;"
        )
        header.addWidget(self._chart_subtitle)
        header.addStretch()
        selector = RangeSelector()
        selector.range_changed.connect(self.range_changed)
        header.addWidget(selector)
        outer.addLayout(header)

        self._chart = GoldChart()
        outer.addWidget(self._chart, 1)
        return card

    def _build_headline_row(self) -> QWidget:
        card = _Card()
        grid = QGridLayout(card)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(24)
        for column, key in enumerate(
            ("High", "Low", "Daily sales", "Daily purchases", "Top sale", "Top purchase")
        ):
            grid.addWidget(_caption(key), 0, column)
            value = _rich("")
            self._headline[key] = value
            grid.addWidget(value, 1, column)
            grid.setColumnStretch(column, 1)
        return card

    def _build_money_panels(self) -> QWidget:
        card = _Card()
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(16)

        panels = (
            ("Sales", ("Total gold earned", "Average earned per day", "Top item")),
            ("Expenses", ("Total gold spent", "Average spent per day", "Top item")),
            ("Profit", ("Total profit", "Average profit per day", "Top item")),
        )
        for index, (title, lines) in enumerate(panels):
            column = QVBoxLayout()
            column.setSpacing(4)
            column.addWidget(_caption(title))
            for line in lines:
                line_row = QHBoxLayout()
                name = QLabel(line)
                name.setStyleSheet("background: transparent;")
                line_row.addWidget(name)
                line_row.addSpacing(12)
                line_row.addStretch()
                value = _rich("", align_right=True)
                self._panel[f"{title}/{line}"] = value
                line_row.addWidget(value)
                column.addLayout(line_row)
            row.addLayout(column, 1)
            if index < len(panels) - 1:
                divider = QFrame()
                divider.setFrameShape(QFrame.Shape.VLine)
                divider.setFixedWidth(1)
                divider.setStyleSheet("background-color: #2e2e2e; border: none;")
                row.addWidget(divider)
        return card

    def _build_top_items(self) -> QWidget:
        card = _Card()
        box = QVBoxLayout(card)
        box.setContentsMargins(12, 8, 12, 8)
        box.setSpacing(4)
        self._items_caption = _caption("Items sold and bought")
        box.addWidget(self._items_caption)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Item", "Earned", "Spent", "Profit"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(_ROW_HEIGHT)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (2, 3, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, _MONEY_COL_WIDTH)
        self.table.setColumnWidth(0, _ICON_SIZE + 12)
        header.setMinimumSectionSize(16)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Keep a few rows visible even at the window's minimum height; the table
        # scrolls rather than collapsing to nothing.
        self.table.setMinimumHeight(_ROW_HEIGHT * 3)
        box.addWidget(self.table)
        return card

    # ── Data ──────────────────────────────────────────────────────────

    def set_stats(self, stats: AccountingStats) -> None:
        self._chart.set_points([(p.timestamp, p.copper) for p in stats.gold_series])
        span = self._chart.date_span()
        if span:
            start, end = span
            self._chart_subtitle.setText(
                f"{datetime.fromtimestamp(start):%d %b %Y} to "
                f"{datetime.fromtimestamp(end):%d %b %Y}"
            )
        else:
            self._chart_subtitle.setText("")

        self._headline["High"].setText(money_html(stats.high))
        self._headline["Low"].setText(money_html(stats.low))
        self._headline["Daily sales"].setText(f"<b>{stats.daily_sales:,}</b>")
        self._headline["Daily purchases"].setText(f"<b>{stats.daily_purchases:,}</b>")
        self._headline["Top sale"].setText(money_html(stats.top_sale))
        self._headline["Top purchase"].setText(money_html(stats.top_purchase))

        self._panel["Sales/Total gold earned"].setText(money_html(stats.earned))
        self._panel["Sales/Average earned per day"].setText(money_html(stats.avg_earned))
        self._panel["Sales/Top item"].setText(self._item_link(stats.top_earned))
        self._panel["Expenses/Total gold spent"].setText(money_html(stats.spent))
        self._panel["Expenses/Average spent per day"].setText(money_html(stats.avg_spent))
        self._panel["Expenses/Top item"].setText(self._item_link(stats.top_spent))
        self._panel["Profit/Total profit"].setText(money_html(stats.profit, tint=True))
        self._panel["Profit/Average profit per day"].setText(
            money_html(stats.avg_profit, tint=True)
        )
        self._panel["Profit/Top item"].setText(self._item_link(stats.top_profit))

        self._fill_items(list(stats.top_items))

    def _item_name(self, item_id: str) -> str:
        """Cached name, falling back to the raw string for non-items."""
        numeric = item_id.split(":")[1] if item_id.startswith("i:") else ""
        return (self._item_cache.get_name(numeric) if numeric else None) or item_id

    def _item_link(self, item_id: str) -> str:
        if not item_id:
            return f'<span style="color:{_DIM}">-</span>'
        return f'<span style="color:{POSITIVE}">{self._item_name(item_id)}</span>'

    def _fill_items(self, items: list[ItemTotals]) -> None:
        self._items_caption.setText(f"ITEMS SOLD AND BOUGHT  ({len(items):,})")
        self.table.setRowCount(len(items))
        for row, totals in enumerate(items):
            numeric = totals.item_id.split(":")[1] if totals.item_id.startswith("i:") else ""
            slug, quality = self._icon_for(totals.item_id, numeric)

            icon_item = QTableWidgetItem()
            icon_item.setData(
                Qt.ItemDataRole.DecorationRole,
                item_icon_pixmap(self._icon_cache.path_for(slug), quality, _ICON_SIZE),
            )
            self.table.setItem(row, 0, icon_item)

            # The item stays in place under the widget: the hover filter reads
            # the id off it to show the full WoW tooltip.
            name_cell = QTableWidgetItem()
            name_cell.setData(Qt.ItemDataRole.UserRole, numeric)
            self.table.setItem(row, 1, name_cell)
            self.table.setCellWidget(
                row, 1, _name_widget(self._item_name(totals.item_id), totals.item_id)
            )

            for column, (value, tint) in enumerate(
                ((totals.earned, False), (totals.spent, False), (totals.profit, True)), start=2
            ):
                if value == 0 and column != 4:
                    cell = _rich(f'<span style="color:{_DIM}">-</span>', align_right=True)
                else:
                    cell = _rich(money_html(value, signed=tint, tint=tint), align_right=True)
                self.table.setCellWidget(row, column, cell)

    def _icon_for(self, item_id: str, numeric: str) -> tuple[str, int]:
        """Icon slug and quality colour for a row, item or not."""
        if not numeric:
            return icon_slug_for_non_item(item_id), _NON_ITEM_QUALITY
        entry = self._item_cache.get(numeric)
        if not entry:
            return "", 1  # name not resolved yet, so no slug to draw
        quality = entry.get("quality")
        return (
            str(entry.get("icon", "")),
            int(quality) if isinstance(quality, (int, float)) else 1,
        )

    def request_icons(self, items: list[ItemTotals], on_done) -> None:
        """Fetch any icons the visible rows still lack."""
        slugs: list[str] = []
        for totals in items:
            numeric = totals.item_id.split(":")[1] if totals.item_id.startswith("i:") else ""
            slug, _quality = self._icon_for(totals.item_id, numeric)
            if slug:
                slugs.append(slug)
        self._icon_cache.ensure_fetched(slugs, on_done)
