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

    async def get_user_realms(self, game_version: str) -> set[tuple[str, str]]:
        return self.user_realms.get(game_version, set())

    async def add_user_realm(self, game_version: str, region: str, name: str) -> None:
        self.added.append((game_version, region, name))

    async def save_snapshot(self, statuses) -> None:
        return None


class _Client:
    """Serves one status payload and records every blob URL fetched."""

    def __init__(self, status: dict):
        self._status = status
        self.downloaded: list[str] = []
        self.added_realms: list[tuple[str, int]] = []
        outer = self

        class _Status:
            async def get(self, channel: str = "release", tsm_version: str = ""):
                return outer._status

        class _Realms:
            async def add(self, game_version: str, realm_id: int):
                outer.added_realms.append((game_version, realm_id))
                return {}

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
async def test_filtered_out_realms_are_logged(tmp_path, caplog):
    """A silent skip is what hid issue #19; the drop must leave a trace."""
    status = {
        "extraClassicRealms": [
            _realm("Everlook-Horde", "Classic-EU"),
            _realm("Mirage Raceway-Horde", "Classic-EU"),
        ]
    }
    cache = _Cache(user_realms={"classic": {("Classic-EU", "Everlook-Horde")}})
    svc, _ = _service(tmp_path, status, cache)

    with caplog.at_level("INFO", logger="tsm.core.services.auction"):
        await svc.refresh_all_realms()

    assert "1 realm(s) not in the added-realm list" in caplog.text
    assert "Classic-EU-Mirage Raceway-Horde" in caplog.text
    assert "Everlook-Horde" not in caplog.text.split("not in the added-realm list")[1]


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
    # every realm still reaches the API, only the local table is selective
    assert client.added_realms == [("bcc", 106), ("classic", 477), ("anniversary", 551)]
