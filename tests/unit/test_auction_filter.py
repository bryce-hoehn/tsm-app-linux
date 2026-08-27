"""Which game versions get narrowed to the user's added realms, and which do not.

/v2/status returns the account's own realms for retail and bcc, but the full
catalogue for Classic Era and Anniversary. Filtering bcc against the added-realm
table skipped every Progression realm (issue #19).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from tsm.core.services.auction import AuctionDataService

APPHELPER = "TradeSkillMaster_AppHelper"


def _realm(name: str, region: str, last_modified: int = 1_800_000_000) -> dict:
    return {
        "id": 1,
        "name": name,
        "region": region,
        "appDataStrings": {
            "AUCTIONDB_NON_COMMODITY_DATA": {
                "url": f"https://cdn.example/{region}/{name}",
                "lastModified": last_modified,
            }
        },
    }


@dataclass
class _Install:
    path: str


class _Detector:
    def __init__(self, base):
        self.installs = [_Install(path=str(base))]


class _AddonWriter:
    """Stands in for AddonWriterService: supplies the detector, records nothing."""

    def __init__(self, base):
        self._detector = _Detector(base)

    def get_detector(self):
        return self._detector

    async def write_data(self, data) -> None:
        return None


@dataclass
class _Cache:
    user_realms: dict[str, set[tuple[str, str]]] = field(default_factory=dict)
    added: list[tuple[str, str, str]] = field(default_factory=list)
    removed: list[tuple[str, str, str]] = field(default_factory=list)

    async def get_user_realms(self, game_version: str) -> set[tuple[str, str]]:
        return self.user_realms.get(game_version, set())

    async def add_user_realm(self, game_version: str, region: str, name: str) -> None:
        self.added.append((game_version, region, name))

    async def remove_user_realm(self, game_version: str, region: str, name: str) -> None:
        self.removed.append((game_version, region, name))

    async def save_snapshot(self, statuses) -> None:
        return None


class _Client:
    """Serves one status payload and records every blob URL fetched."""

    def __init__(self, status: dict):
        self._status = status
        self.downloaded: list[str] = []
        self.added_realms: list[tuple[str, int]] = []
        self.removed_realms: list[tuple[str, str, str]] = []
        outer = self

        class _Status:
            async def get(self, channel: str = "release", tsm_version: str = ""):
                return outer._status

        class _Realms:
            async def add(self, game_version: str, realm_id: int):
                outer.added_realms.append((game_version, realm_id))
                return {}

            async def remove(self, game_version: str, region: str, realm: str):
                outer.removed_realms.append((game_version, region, realm))
                return {"success": True}

        self.status = _Status()
        self.realms = _Realms()

    async def raw_download(self, url: str) -> str:
        self.downloaded.append(url)
        return "return {downloadTime=1800000000,fields={},data={}}"


def _make_wow_tree(base, game_versions=("_retail_", "_classic_", "_classic_era_", "_anniversary_")):
    for gv in game_versions:
        (base / gv / "Interface" / "AddOns" / APPHELPER).mkdir(parents=True)


def _service(tmp_path, status, cache=None):
    base = tmp_path / "wow"
    _make_wow_tree(base)
    client = _Client(status)
    svc = AuctionDataService(client, cache or _Cache(), _AddonWriter(base))
    return svc, client


def _synced_names(data) -> set[str]:
    return {rs.name for rs in data.realm_statuses if not rs.is_region}


@pytest.mark.asyncio
async def test_bcc_realms_sync_without_any_added_realms(tmp_path):
    """status keys Progression realms by account, so no local filter applies."""
    status = {"realms-Progression": [_realm("Everlook-Horde", "BCC-EU")]}
    svc, client = _service(tmp_path, status)

    data = await svc.refresh_all_realms()

    assert _synced_names(data) == {"Everlook-Horde"}
    assert len(client.downloaded) == 1


@pytest.mark.asyncio
async def test_bcc_realms_sync_despite_a_stale_bare_region_row(tmp_path):
    """The exact regression: a stored ("EU", name) row must not skip ("BCC-EU", name)."""
    status = {"realms-Progression": [_realm("Everlook-Horde", "BCC-EU")]}
    cache = _Cache(user_realms={"bcc": {("EU", "Everlook-Horde")}})
    svc, client = _service(tmp_path, status, cache)

    data = await svc.refresh_all_realms()

    assert _synced_names(data) == {"Everlook-Horde"}
    assert len(client.downloaded) == 1


@pytest.mark.asyncio
async def test_classic_era_still_filters_by_exact_region(tmp_path):
    """Guards commit 0238697: Classic-EU, HC-EU and SoD-EU must stay distinct."""
    status = {
        "extraClassicRealms": [
            _realm("Everlook-Horde", "Classic-EU"),
            _realm("Everlook-Horde", "HC-EU"),
            _realm("Everlook-Horde", "SoD-EU"),
        ]
    }
    cache = _Cache(user_realms={"classic": {("HC-EU", "Everlook-Horde")}})
    svc, client = _service(tmp_path, status, cache)

    data = await svc.refresh_all_realms()

    assert [rs.region for rs in data.realm_statuses if not rs.is_region] == ["HC-EU"]
    assert client.downloaded == ["https://cdn.example/HC-EU/Everlook-Horde"]


@pytest.mark.asyncio
async def test_anniversary_skips_entirely_when_nothing_was_added(tmp_path):
    status = {"extraAnniversaryRealms": [_realm("Maladath (AU)-Alliance", "Fresh-US")]}
    svc, client = _service(tmp_path, status)

    data = await svc.refresh_all_realms()

    assert _synced_names(data) == set()
    assert client.downloaded == []


@pytest.mark.asyncio
async def test_add_realm_stores_catalogue_game_versions_only(tmp_path):
    svc, client = _service(tmp_path, {})
    cache = svc._cache

    await svc.add_realm("bcc", 106, "EU", "Everlook-Horde")
    await svc.add_realm("classic", 477, "HC-EU", "Skull Rock-Alliance")
    await svc.add_realm("anniversary", 551, "Fresh-US", "Maladath (AU)-Alliance")

    assert ("bcc", "EU", "Everlook-Horde") not in cache.added
    assert cache.added == [
        ("classic", "HC-EU", "Skull Rock-Alliance"),
        ("anniversary", "Fresh-US", "Maladath (AU)-Alliance"),
    ]
    # Only bcc is registered server side. realms2/add answers "Internal error.
    # Contact support." for the catalogue game versions, and registering them
    # would not affect what syncs.
    assert client.added_realms == [("bcc", 106)]


@pytest.mark.asyncio
async def test_remove_catalogue_realm_is_local_only(tmp_path):
    """Classic Era and Anniversary are filtered locally, so no API call is right.

    realms2/remove answers "Invalid request." for them and changes nothing, since
    /v2/status returns the whole catalogue regardless of what is registered.
    """
    svc, client = _service(tmp_path, {})
    cache = svc._cache

    await svc.remove_realm("classic", "HC-EU", "Soulseeker-Alliance")
    await svc.remove_realm("anniversary", "Fresh-EU", "Thunderstrike-Alliance")

    assert client.removed_realms == []
    assert cache.removed == [
        ("classic", "HC-EU", "Soulseeker-Alliance"),
        ("anniversary", "Fresh-EU", "Thunderstrike-Alliance"),
    ]


@pytest.mark.asyncio
async def test_remove_progression_realm_sends_the_bare_region(tmp_path):
    """Verified live 2026-08-27: bcc/EU/<realm> succeeds, bcc/BCC-EU/<realm> does not."""
    svc, client = _service(tmp_path, {})

    await svc.remove_realm("bcc", "BCC-EU", "Venoxis-Horde")

    assert client.removed_realms == [("bcc", "EU", "Venoxis-Horde")]
    assert svc._cache.removed == []  # bcc is not tracked locally


@pytest.mark.asyncio
async def test_remove_retail_realm_passes_the_region_through(tmp_path):
    svc, client = _service(tmp_path, {})

    await svc.remove_realm("retail", "EU", "Tarren Mill")

    assert client.removed_realms == [("retail", "EU", "Tarren Mill")]


def test_bare_region_only_strips_a_game_version_prefix():
    from tsm.core.services.auction import _bare_region

    assert _bare_region("BCC-EU") == "EU"
    assert _bare_region("EU") == "EU"
    assert _bare_region("US") == "US"
    # Never used on a user_added_realms key, where these three must stay distinct
    assert _bare_region("HC-EU") == "EU"
    assert _bare_region("SoD-EU") == "EU"


@pytest.mark.asyncio
async def test_skipped_realms_log_counts_at_info_and_names_at_debug(tmp_path, caplog):
    """240 catalogue realms every five minutes must not dump names at INFO."""
    status = {
        "extraClassicRealms": [
            _realm("Everlook-Horde", "Classic-EU"),
            _realm("Mirage Raceway-Horde", "Classic-EU"),
            _realm("Pyrewood Village-Horde", "Classic-EU"),
        ]
    }
    cache = _Cache(user_realms={"classic": {("Classic-EU", "Everlook-Horde")}})
    svc, _ = _service(tmp_path, status, cache)

    with caplog.at_level("INFO", logger="tsm.core.services.auction"):
        await svc.refresh_all_realms()
    assert "_classic_era_: 2 of 3 realms not in the added-realm list" in caplog.text
    assert "Mirage Raceway-Horde" not in caplog.text

    caplog.clear()
    with caplog.at_level("DEBUG", logger="tsm.core.services.auction"):
        await svc.refresh_all_realms()
    assert "Mirage Raceway-Horde" in caplog.text


@pytest.mark.asyncio
async def test_add_catalogue_realm_survives_an_api_that_refuses(tmp_path):
    """Add Realm for Classic Era must not depend on realms2/add succeeding.

    Before this, the API error propagated and the local row was never written,
    so adding a Classic Era or Anniversary realm did nothing at all.
    """
    svc, client = _service(tmp_path, {})

    async def boom(game_version: str, realm_id: int):
        raise RuntimeError("Internal error. Contact support.")

    client.realms.add = boom

    await svc.add_realm("classic", 477, "HC-EU", "Skull Rock-Alliance")

    assert svc._cache.added == [("classic", "HC-EU", "Skull Rock-Alliance")]
