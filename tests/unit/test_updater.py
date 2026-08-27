"""Unit tests for UpdateService addon naming and per-game-version installs."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from tsm.core.services.updater import UpdateService

ADDON = "TradeSkillMaster_AppHelper"
GAME_VERSIONS = ("_retail_", "_classic_era_", "_classic_", "_anniversary_")


@dataclass
class _Install:
    path: str


class _FakeDetector:
    def __init__(self, base: Path):
        self.installs = [_Install(path=str(base))]


class _FakeAddonAPI:
    """Records every requested API name and answers with a marker zip."""

    def __init__(self) -> None:
        self.requested: list[str] = []

    async def download(self, name: str, channel: str = "release") -> bytes:
        self.requested.append(name)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(f"{ADDON}/served.txt", name)
            zf.writestr(f"{ADDON}/{ADDON}.toc", "## Version: v4.14.10\n")
        return buf.getvalue()


class _FakeClient:
    def __init__(self) -> None:
        self.addon = _FakeAddonAPI()


def _make_wow_tree(base: Path, game_versions=GAME_VERSIONS, with_addon=()) -> None:
    """Create a WoW tree. with_addon lists the game versions that already have
    an outdated copy of the addon installed."""
    for gv in game_versions:
        gv_dir = base / gv
        (gv_dir / "Interface" / "AddOns").mkdir(parents=True)
        (gv_dir / "Wow.exe").write_bytes(b"MZ")
    for gv in with_addon:
        addon_dir = base / gv / "Interface" / "AddOns" / ADDON
        addon_dir.mkdir(parents=True, exist_ok=True)
        (addon_dir / f"{ADDON}.toc").write_text("## Version: v4.14.09\n")


def _served(base: Path, gv: str) -> str | None:
    marker = base / gv / "Interface" / "AddOns" / ADDON / "served.txt"
    return marker.read_text() if marker.is_file() else None


@pytest.mark.asyncio
async def test_check_and_update_requests_package_per_game_version(tmp_path):
    """Each client gets the package built for it, never the retail build."""
    base = tmp_path / "wow"
    _make_wow_tree(base, with_addon=("_retail_", "_classic_era_", "_anniversary_"))
    client = _FakeClient()
    svc = UpdateService(api_client=client, wow_detector=_FakeDetector(base))

    updated = await svc.check_and_update([{"name": ADDON, "version_str": "v4.14.10"}])

    assert updated == [ADDON]
    assert sorted(client.addon.requested) == [
        ADDON,
        f"{ADDON}-Anniversary",
        f"{ADDON}-Classic",
    ]
    assert _served(base, "_retail_") == ADDON
    assert _served(base, "_classic_era_") == f"{ADDON}-Classic"
    assert _served(base, "_anniversary_") == f"{ADDON}-Anniversary"
    # _classic_ had no copy installed, so it is left alone.
    assert _served(base, "_classic_") is None


@pytest.mark.asyncio
async def test_check_and_update_downloads_each_package_once(tmp_path):
    """Two installs of the same game version share one download."""
    base_a = tmp_path / "wow-a"
    base_b = tmp_path / "wow-b"
    for base in (base_a, base_b):
        _make_wow_tree(base, game_versions=("_retail_",), with_addon=("_retail_",))
    client = _FakeClient()
    detector = _FakeDetector(base_a)
    detector.installs.append(_Install(path=str(base_b)))
    svc = UpdateService(api_client=client, wow_detector=detector)

    await svc.check_and_update([{"name": ADDON, "version_str": "v4.14.10"}])

    assert client.addon.requested == [ADDON]
    assert _served(base_a, "_retail_") == ADDON
    assert _served(base_b, "_retail_") == ADDON


@pytest.mark.asyncio
async def test_install_or_update_addon_keeps_the_suffix(tmp_path):
    """The suffixed UI name is what goes to the API; only its own client is touched."""
    base = tmp_path / "wow"
    _make_wow_tree(base)
    client = _FakeClient()
    svc = UpdateService(api_client=client, wow_detector=_FakeDetector(base))

    ok = await svc.install_or_update_addon(f"{ADDON}-Progression", "v4.14.10")

    assert ok is True
    assert client.addon.requested == [f"{ADDON}-Progression"]
    assert _served(base, "_classic_") == f"{ADDON}-Progression"
    for gv in ("_retail_", "_classic_era_", "_anniversary_"):
        assert _served(base, gv) is None


@pytest.mark.asyncio
async def test_install_or_update_addon_retail_has_no_suffix(tmp_path):
    base = tmp_path / "wow"
    _make_wow_tree(base)
    client = _FakeClient()
    svc = UpdateService(api_client=client, wow_detector=_FakeDetector(base))

    ok = await svc.install_or_update_addon(ADDON, "v4.14.10")

    assert ok is True
    assert client.addon.requested == [ADDON]
    assert _served(base, "_retail_") == ADDON


@pytest.mark.asyncio
async def test_download_failure_is_requested_once_per_package(tmp_path):
    """A package the server refuses is not re-requested for every install."""
    base_a = tmp_path / "wow-a"
    base_b = tmp_path / "wow-b"
    for base in (base_a, base_b):
        _make_wow_tree(base, game_versions=("_retail_",), with_addon=("_retail_",))
    client = _FakeClient()

    async def boom(name: str, channel: str = "release") -> bytes:
        client.addon.requested.append(name)
        raise RuntimeError("Invalid request.")

    client.addon.download = boom
    detector = _FakeDetector(base_a)
    detector.installs.append(_Install(path=str(base_b)))
    svc = UpdateService(api_client=client, wow_detector=detector)

    updated = await svc.check_and_update([{"name": ADDON, "version_str": "v4.14.10"}])

    assert updated == []
    assert client.addon.requested == [ADDON]
