"""Integration tests for TSMApiClient using aioresponses."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import parse_qs, urlparse

import pytest
from aioresponses import CallbackResult, aioresponses

from tsm.api.client import OIDC_URL, TSMApiClient, TSMApiError

# Regex helpers, match base URL regardless of dynamic query params (time, token)
RE_AUTH = re.compile(r"http://app-server\.tradeskillmaster\.com/v2/auth.*")
RE_STATUS = re.compile(r"http://app-server\.tradeskillmaster\.com/v2/status.*")
RE_CDN = re.compile(r"https://cdn\.tradeskillmaster\.com/data/test\.txt.*")
RE_ADDON = re.compile(r"http://addon-server\.tradeskillmaster\.com/v2/addon/.*")
RE_ADDON_CDN = re.compile(r"https://cdn\.tradeskillmaster\.com/addons/.*")

ADDON_USER_INFO = {
    "session": "s",
    "userId": 1,
    "endpointSubdomains": {"addon": "addon-server"},
}


@pytest.mark.asyncio
async def test_oidc_login():
    client = TSMApiClient()
    with aioresponses() as m:
        m.post(OIDC_URL, payload={"access_token": "oidc_tok", "token_type": "Bearer"})
        result = await client.auth.get_oidc_token("user@test.com", "pass")
    assert result["access_token"] == "oidc_tok"
    await client.close()


@pytest.mark.asyncio
async def test_authenticate_sets_user_info():
    client = TSMApiClient()
    user_info = {
        "session": "sess123",
        "userId": 42,
        "isPremium": True,
        "endpointSubdomains": {"status": "app-server"},
    }
    with aioresponses() as m:
        m.post(RE_AUTH, payload=user_info)
        result = await client.auth.authenticate("oidc_tok")
    assert result["session"] == "sess123"
    assert client.session_token == "sess123"
    await client.close()


@pytest.mark.asyncio
async def test_status_call():
    client = TSMApiClient()
    client.set_user_info(
        {
            "session": "s",
            "userId": 1,
            "endpointSubdomains": {"status": "app-server"},
        }
    )
    status_payload = {
        "realms": [{"name": "Blackhand", "region": "EU", "ahId": 1, "appDataStrings": {}}],
        "regions": [],
        "addonMessage": {"id": 0, "msg": ""},
        "appVersion": 41402,
    }
    with aioresponses() as m:
        m.get(RE_STATUS, payload=status_payload)
        result = await client.status.get()
    realms = result.get("realms", [])
    assert realms[0].get("name") == "Blackhand"
    await client.close()


@pytest.mark.asyncio
async def test_raw_download():
    client = TSMApiClient()
    blob = "return {downloadTime=1710000000,fields={},data={}}"
    with aioresponses() as m:
        m.get(RE_CDN, body=blob)
        result = await client.raw_download("https://cdn.tradeskillmaster.com/data/test.txt")
    assert "downloadTime" in result
    await client.close()


@pytest.mark.asyncio
async def test_addon_download_direct_bytes():
    """Old API behavior: addon endpoint returns zip bytes directly."""
    client = TSMApiClient()
    client.set_user_info(ADDON_USER_INFO)
    fake_zip = b"PK\x03\x04fake-zip-content"
    with aioresponses() as m:
        m.get(RE_ADDON, body=fake_zip, content_type="application/zip")
        result = await client.addon.download("TradeSkillMaster")
    assert result == fake_zip
    await client.close()


@pytest.mark.asyncio
async def test_addon_download_json_redirect():
    """New API behavior: addon endpoint returns JSON with redirect URL."""
    client = TSMApiClient()
    client.set_user_info(ADDON_USER_INFO)
    fake_zip = b"PK\x03\x04fake-zip-from-cdn"
    with aioresponses() as m:
        m.get(RE_ADDON, payload={"url": "https://cdn.tradeskillmaster.com/addons/tsm.zip"})
        m.get(RE_ADDON_CDN, body=fake_zip, content_type="application/zip")
        result = await client.addon.download("TradeSkillMaster")
    assert result == fake_zip
    await client.close()


@pytest.mark.asyncio
async def test_addon_download_json_missing_url():
    """JSON response with no recognizable URL key raises ValueError."""
    client = TSMApiClient()
    client.set_user_info(ADDON_USER_INFO)
    with aioresponses() as m:
        m.get(RE_ADDON, payload={"foo": "bar"})
        with pytest.raises(ValueError, match="no URL"):
            await client.addon.download("TradeSkillMaster")
    await client.close()


@pytest.mark.asyncio
async def test_addon_download_api_error_envelope():
    """{"success": false, ...} on any endpoint raises TSMApiError with the message."""
    client = TSMApiClient()
    client.set_user_info(ADDON_USER_INFO)
    with aioresponses() as m:
        m.get(RE_ADDON, payload={"success": False, "error": "Invalid request."})
        with pytest.raises(TSMApiError, match="Invalid request"):
            await client.addon.download("TradeSkillMaster")
    await client.close()


@pytest.mark.asyncio
async def test_status_error_envelope_raises():
    """A failed status call must not look like an empty-but-successful response."""
    client = TSMApiClient()
    client.set_user_info(
        {"session": "s", "userId": 1, "endpointSubdomains": {"status": "app-server"}}
    )
    with aioresponses() as m:
        m.get(RE_STATUS, payload={"success": False, "error": "Invalid request."})
        with pytest.raises(TSMApiError, match="Invalid request"):
            await client.status.get()
    await client.close()


@pytest.mark.asyncio
async def test_addon_download_omits_tsm_version():
    """The /v2/addon endpoint takes no tsm_version parameter; only /v2/status does."""
    client = TSMApiClient()
    client.set_user_info(ADDON_USER_INFO)
    seen: list[str] = []

    def callback(url, **kwargs):
        seen.append(str(url))
        return CallbackResult(body=b"PK\x03\x04zip", content_type="application/zip")

    with aioresponses() as m:
        m.get(RE_ADDON, callback=callback)
        await client.addon.download("TradeSkillMaster_AppHelper-Progression")

    assert len(seen) == 1
    query = parse_qs(urlparse(seen[0]).query)
    assert "tsm_version" not in query
    assert query["channel"] == ["release"]
    assert "/v2/addon/TradeSkillMaster_AppHelper-Progression" in seen[0]
    await client.close()


@pytest.mark.asyncio
async def test_retry_on_server_error():
    client = TSMApiClient()
    client.set_user_info(
        {
            "session": "s",
            "userId": 1,
            "endpointSubdomains": {"status": "app-server"},
        }
    )
    good_payload = {"realms": [], "regions": [], "addonMessage": {"id": 0, "msg": ""}}
    with aioresponses() as m:
        m.get(RE_STATUS, status=503)
        m.get(RE_STATUS, status=503)
        m.get(RE_STATUS, payload=good_payload)
        result = await client.status.get()
    assert result.get("realms") == []
    await client.close()


@pytest.mark.asyncio
async def test_reauth_retries_once_after_rejection():
    """A rejected request recovers in place: log in again, then retry."""
    client = TSMApiClient()
    client.set_user_info(
        {"session": "stale", "userId": 1, "endpointSubdomains": {"addon": "addon-server"}}
    )
    calls: list[str] = []

    async def reauth() -> None:
        calls.append("reauth")
        client.set_user_info(
            {"session": "fresh", "userId": 1, "endpointSubdomains": {"addon": "addon-server"}}
        )

    client.set_reauth_callback(reauth)

    seen: list[str] = []

    def callback(url, **kwargs):
        seen.append(str(url))
        if len(seen) == 1:
            return CallbackResult(
                payload={"success": False, "error": "Invalid request."},
                content_type="application/json",
            )
        return CallbackResult(body=b"PK\x03\x04zip", content_type="application/zip")

    with aioresponses() as m:
        m.get(RE_ADDON, callback=callback, repeat=True)
        result = await client.addon.download("TradeSkillMaster")

    assert result == b"PK\x03\x04zip"
    assert calls == ["reauth"]
    assert parse_qs(urlparse(seen[0]).query)["session"] == ["stale"]
    assert parse_qs(urlparse(seen[1]).query)["session"] == ["fresh"]
    await client.close()


@pytest.mark.asyncio
async def test_reauth_picks_up_a_new_subdomain():
    """endpointSubdomains is per session, so the retry must re-resolve the host."""
    client = TSMApiClient()
    client.set_user_info(
        {"session": "s", "userId": 1, "endpointSubdomains": {"addon": "app-server"}}
    )

    async def reauth() -> None:
        client.set_user_info(
            {"session": "s2", "userId": 1, "endpointSubdomains": {"addon": "app-server5"}}
        )

    client.set_reauth_callback(reauth)

    with aioresponses() as m:
        m.get(
            re.compile(r"http://app-server\.tradeskillmaster\.com/v2/addon/.*"),
            payload={"success": False, "error": "Invalid request."},
        )
        m.get(
            re.compile(r"http://app-server5\.tradeskillmaster\.com/v2/addon/.*"),
            body=b"PK\x03\x04zip",
            content_type="application/zip",
        )
        result = await client.addon.download("TradeSkillMaster")

    assert result == b"PK\x03\x04zip"
    await client.close()


@pytest.mark.asyncio
async def test_reauth_is_not_retried_forever():
    """If the retry is rejected too, the error surfaces after exactly one reauth."""
    client = TSMApiClient()
    client.set_user_info(
        {"session": "s", "userId": 1, "endpointSubdomains": {"addon": "addon-server"}}
    )
    calls: list[str] = []

    async def reauth() -> None:
        calls.append("reauth")

    client.set_reauth_callback(reauth)

    with aioresponses() as m:
        m.get(RE_ADDON, payload={"success": False, "error": "Invalid request."}, repeat=True)
        with pytest.raises(TSMApiError, match="Invalid request"):
            await client.addon.download("TradeSkillMaster")

    assert calls == ["reauth"]
    await client.close()


@pytest.mark.asyncio
async def test_concurrent_rejections_reauthenticate_once():
    """Several requests rejected at once share a single login, then all retry."""
    client = TSMApiClient()
    client.set_user_info(
        {"session": "stale", "userId": 1, "endpointSubdomains": {"addon": "addon-server"}}
    )
    logins: list[str] = []

    async def reauth() -> None:
        await asyncio.sleep(0.05)  # hold the lock so the others queue behind it
        logins.append("login")
        client.set_user_info(
            {"session": "fresh", "userId": 1, "endpointSubdomains": {"addon": "addon-server"}}
        )

    client.set_reauth_callback(reauth)

    def callback(url, **kwargs):
        if parse_qs(urlparse(str(url)).query)["session"] == ["stale"]:
            return CallbackResult(
                payload={"success": False, "error": "Invalid request."},
                content_type="application/json",
            )
        return CallbackResult(body=b"PK\x03\x04zip", content_type="application/zip")

    with aioresponses() as m:
        m.get(RE_ADDON, callback=callback, repeat=True)
        results = await asyncio.gather(
            client.addon.download("TradeSkillMaster"),
            client.addon.download("TradeSkillMaster_AppHelper"),
            client.addon.download("TradeSkillMaster_AppHelper-Classic"),
        )

    assert results == [b"PK\x03\x04zip"] * 3
    assert logins == ["login"]
    await client.close()
