"""Ordering rules for the grouped Realm Data tab."""

from __future__ import annotations

from tsm.ui.viewmodels.realm_vm import RealmSummary
from tsm.ui.views.realm_grouping import (
    GV_LABELS,
    GV_ORDER,
    group_summaries,
    realm_count,
)


def region(name: str, game_version: str, last_updated: int = 100) -> RealmSummary:
    return RealmSummary(
        display_name=name,
        is_region=True,
        last_updated=last_updated,
        game_version=game_version,
        region=name,
        name=name,
    )


def realm(
    name: str, region_name: str, game_version: str, display: str | None = None
) -> RealmSummary:
    return RealmSummary(
        display_name=display or f"{region_name}-{name}",
        is_region=False,
        last_updated=100,
        game_version=game_version,
        region=region_name,
        name=name,
    )


def shape(rows) -> list[tuple[int, str]]:
    """(indent, label) per row, which is what the table actually renders."""
    return [(r.indent, r.label) for r in rows]


def test_groups_follow_gv_order_and_skip_empty_ones():
    summaries = [
        region("Fresh-EU", "anniversary"),
        region("EU", "retail"),
        region("BCC-EU", "bcc"),
    ]

    groups = group_summaries(summaries)

    assert [gv for gv, _label, _rows in groups] == ["retail", "bcc", "anniversary"]
    assert [label for _gv, label, _rows in groups] == ["Retail", "Progression", "Anniversary"]
    assert "classic" not in [gv for gv, _l, _r in groups]
    assert [gv for gv in GV_ORDER if gv in dict.fromkeys(g[0] for g in groups)] == [
        "retail",
        "bcc",
        "anniversary",
    ]


def test_each_region_is_followed_by_its_own_realms():
    summaries = [
        realm("Wild Growth-Alliance", "SoD-US", "classic"),
        region("HC-EU", "classic"),
        realm("Soulseeker-Alliance", "HC-EU", "classic"),
        region("SoD-US", "classic"),
    ]

    (_gv, label, rows) = group_summaries(summaries)[0]

    assert label == "Classic Era"
    assert shape(rows) == [
        (0, "HC-EU"),
        (1, "Soulseeker-Alliance"),
        (0, "SoD-US"),
        (1, "Wild Growth-Alliance"),
    ]
    assert [r.is_region for r in rows] == [True, False, True, False]


def test_realms_sort_within_their_region():
    summaries = [
        region("BCC-EU", "bcc"),
        realm("Venoxis-Horde", "BCC-EU", "bcc"),
        realm("Everlook-Horde", "BCC-EU", "bcc"),
        realm("Jin'do-Horde", "BCC-EU", "bcc"),
    ]

    (_gv, _label, rows) = group_summaries(summaries)[0]

    assert shape(rows) == [
        (0, "BCC-EU"),
        (1, "Everlook-Horde"),
        (1, "Jin'do-Horde"),
        (1, "Venoxis-Horde"),
    ]


def test_realm_label_drops_the_region_prefix_from_display_name():
    """AuctionDataService bakes "Progression-EU-" into display_name; the header says it."""
    summaries = [
        region("BCC-EU", "bcc"),
        realm("Everlook-Horde", "BCC-EU", "bcc", display="Progression-EU-Everlook-Horde"),
    ]

    (_gv, _label, rows) = group_summaries(summaries)[0]

    assert shape(rows) == [(0, "BCC-EU"), (1, "Everlook-Horde")]
    # the untouched display_name is still available for the delete dialog
    assert rows[1].summary.display_name == "Progression-EU-Everlook-Horde"


def test_realm_without_a_region_row_still_shows_under_a_placeholder():
    """A missing region blob must not make its realms disappear."""
    summaries = [realm("Tarren Mill", "EU", "retail")]

    (_gv, _label, rows) = group_summaries(summaries)[0]

    assert shape(rows) == [(0, "EU"), (1, "Tarren Mill")]
    placeholder = rows[0].summary
    assert placeholder.is_region is True
    assert placeholder.auctiondb_status == ""
    assert placeholder.last_updated == 0
    assert placeholder.game_version == "retail"


def test_realm_count_ignores_region_headers():
    summaries = [
        region("HC-EU", "classic"),
        realm("Soulseeker-Alliance", "HC-EU", "classic"),
        region("SoD-US", "classic"),
        realm("Wild Growth-Alliance", "SoD-US", "classic"),
    ]

    (_gv, _label, rows) = group_summaries(summaries)[0]

    assert len(rows) == 4
    assert realm_count(rows) == 2


def test_empty_input_produces_no_groups():
    assert group_summaries([]) == []


def test_unknown_game_version_is_kept_rather_than_dropped():
    """A game version the API adds later must still be visible."""
    summaries = [region("XX-EU", "midnight")]

    groups = group_summaries(summaries)

    assert [gv for gv, _l, _r in groups] == ["midnight"]
    assert groups[0][1] == "midnight"  # falls back to the raw key as its label
    assert "midnight" not in GV_LABELS


def test_remove_local_drops_exactly_one_of_two_equal_summaries():
    """Removal is by identity: value-equal duplicates must not both vanish."""
    from tsm.ui.viewmodels.realm_vm import RealmViewModel

    first = realm("Everlook-Horde", "BCC-EU", "bcc")
    second = realm("Everlook-Horde", "BCC-EU", "bcc")
    assert first == second and first is not second
    header = region("BCC-EU", "bcc")
    vm = RealmViewModel()
    vm._summaries = [header, first, second]

    vm.remove_local(first)

    assert len(vm.summaries) == 2
    assert vm.summaries[0] is header
    assert vm.summaries[1] is second
