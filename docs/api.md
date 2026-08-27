# TradeSkillMaster API Reference

Reverse-engineered from `AppAPI.pyc` and `MainThread.pyc` shipped with the original
Windows TSM Desktop App. All information here was derived by reading the decompiled
bytecode; nothing was obtained from official documentation.

---

## Base URLs

| Purpose                           | URL                                                                        |
| --------------------------------- | -------------------------------------------------------------------------- |
| Authentication (Keycloak OIDC)    | `https://id.tradeskillmaster.com/realms/app/protocol/openid-connect/token` |
| App server (auth + all API calls) | `http://app-server.tradeskillmaster.com/v2/`                               |
| Endpoint-specific subdomains      | `http://{subdomain}.tradeskillmaster.com/v2/`                              |
| CDN data blobs                    | Variable URLs returned by the status endpoint                              |

After a successful login the server returns a map of `endpointSubdomains`; subsequent
calls are routed to the subdomain assigned to each endpoint.

---

## Authentication

Authentication is a two-step process.

### Step 1 - Keycloak OIDC token

```
POST https://id.tradeskillmaster.com/realms/app/protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded
```

Form body:

| Field          | Value                       |
| -------------- | --------------------------- |
| `username`     | User's TSM account e-mail   |
| `password`     | User's TSM account password |
| `client_id`    | `legacy-desktop-app`        |
| `grant_type`   | `password`                  |
| `code`         | _(empty string)_            |
| `redirect_uri` | _(empty string)_            |
| `scope`        | `openid`                    |

**Important:** Must be sent as `application/x-www-form-urlencoded`. Keycloak rejects
`multipart/form-data` with HTTP 401.

Response (JSON):

```json
{
  "access_token": "<jwt>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid"
}
```

### Step 2 - TSM session exchange

Exchange the OIDC access token for a TSM session token and user info.

```
POST http://app-server.tradeskillmaster.com/v2/auth
Content-Type: application/json
```

Query parameters: see [Request Authentication](#request-authentication) below.

Request body:

```json
{ "token": "<access_token from step 1>" }
```

Response:

```json
{
  "success": true,
  "session": "<session_token>",
  "userId": 123456,
  "isPremium": true,
  "endpointSubdomains": {
    "status": "app-server",
    "addon": "app-server5",
    "auctiondb": "app-server5",
    "app": "app-server",
    "backup": "app-server",
    "shopping": "app-server",
    "sv": "legacy-app2"
  }
}
```

The `session` token must be included in all subsequent requests. The
`endpointSubdomains` map tells the client which subdomain to call for each endpoint.

**This map is assigned per session and is not stable.** Observed live: `status`
is consistently `app-server`, while `addon` and `auctiondb` come back as
`app-server4` or `app-server5` depending on the login, and the set of keys varies
(`sv` is not always present). A subdomain only serves the endpoints it was
assigned: asking `app-server` for `/v2/addon` is rejected even with a valid
session. The map must therefore be read from the auth response for every session,
never cached or hardcoded, and a rejected call is worth retrying after a fresh
login.

---

## Request Authentication

Every API call (except the OIDC step) includes these query parameters:

| Parameter     | Type   | Description                           |
| ------------- | ------ | ------------------------------------- |
| `session`     | string | Session token from the auth exchange  |
| `version`     | int    | App version integer (`41402`)         |
| `time`        | int    | Current Unix timestamp (seconds)      |
| `token`       | string | HMAC token - see below                |
| `channel`     | string | _(optional)_ `"release"` or `"beta"`  |
| `tsm_version` | string | _(optional)_ TSM addon version string |

`tsm_version` is the version of the installed **TradeSkillMaster addon**, read
from its `.toc`, not the version of whatever is being requested. The original
client sends it on `/v2/status` only (`AppAPI.py:171`); `/v2/addon` is called
without it (`AppAPI.py:175`).

### HMAC token computation

```python
import time
from hashlib import sha256

APP_VERSION = 41402
HMAC_SECRET = "3FB1CC5EDC5B43F21CB8ACC23B42B703"

t = int(time.time())
raw = f"{APP_VERSION}:{t}:{HMAC_SECRET}"
token = sha256(raw.encode("utf-8")).hexdigest()
```

The secret is the same for all clients. Token validity is verified server-side by
checking that `time` is within a reasonable window of the server clock.

---

## Request Format

All API requests (except OIDC and raw CDN downloads) follow the same pattern:

- **GET** when there is no body.
- **POST** when a body is present.
- JSON bodies are compressed with gzip and sent with `Content-Encoding: gzip`.
- `User-Agent` header: `TSMApplication/41402`
- SSL verification is disabled in the original app (`verify=False`); the server
  uses plain HTTP for all non-OIDC endpoints.

The response `Content-Type` determines how the response is parsed:

| Content-Type                                   | Parsing               |
| ---------------------------------------------- | --------------------- |
| `application/json`                             | Decoded as JSON       |
| `application/zip` / `application/octet-stream` | Returned as raw bytes |
| anything else                                  | Decoded as UTF-8 text |

Failed requests with HTTP 5xx are retried up to 3 times with exponential back-off
(2 s, 4 s). HTTP 4xx errors are raised immediately without retry.

### Error envelope

Every JSON response carries a `success` field. A rejection is **HTTP 200** with:

```json
{ "success": false, "error": "Invalid request." }
```

`"Invalid request."` is the server's generic rejection string and does not say
what was wrong. It is returned for an expired or unknown session, for an empty
session, and for asking a subdomain to serve an endpoint it was not assigned. A
client that only looks at the HTTP status treats these as successful empty
responses.

---

## Endpoints

### `GET /v2/status`

Fetch the current status including realm lists, download URLs, addon versions, and
an optional broadcast message.

Query params: standard auth params + optional `channel` and `tsm_version`.

Response structure:

```json
{
  "success": true,
  "channels": { "release": "Release" },
  "appInfo": { "news": "Welcome to TSM!", "minTSMUpdateNotificationVersion": 3030600 },
  "addons": [{ "name": "TradeSkillMaster", "version_str": "v4.14.76" }],
  "addons-Classic": [{ "name": "TradeSkillMaster-Classic", "version_str": "v4.14.76" }],
  "addons-BCC": [{ "name": "TradeSkillMaster-BCC", "version_str": "v4.14.76" }],
  "addonMessage": { "id": 0, "msg": "" },
  "realms": [ ... ],
  "regions": [ ... ],
  "realms-Progression": [ ... ],
  "regions-Progression": [ ... ],
  "extraClassicRealms": [ ... ],
  "extraClassicRegions": [ ... ],
  "extraAnniversaryRealms": [ ... ],
  "extraAnniversaryRegions": [ ... ]
}
```

All realm array values are `RealmEntry[]`. See the game version mapping table
below for which key corresponds to which WoW version.

`version_str` values carry a leading `v` (e.g. `v4.14.76`). `appVersion` is
documented here for completeness but is **not** present in the live response, so
clients fall back to their own build number. `realms-BCC` / `regions-BCC` are
returned alongside `realms-Progression` / `regions-Progression` and carry the
same payload.

**Account-scoped keys vs catalogue keys.** This is the distinction that decides
whether a client has to filter the list itself:

| Key | Scope | Rows (measured 2026-08-27) |
| --- | --- | --- |
| `realms` / `regions` | the account's registered realms | 1 |
| `realms-Progression` / `regions-Progression` | the account's registered realms | 3 |
| `extraClassicRealms` / `extraClassicRegions` | full catalogue | 240 / 12 |
| `extraAnniversaryRealms` / `extraAnniversaryRegions` | full catalogue | 10 / 4 |

Retail and Progression already come back narrowed to the account, so a client
must not filter them further. The `extra*` keys return every realm in every
region and do need narrowing to whatever the user chose to add.

Region strings within one catalogue key are not interchangeable prefixes of a
common region: `extraClassicRealms` carries `Classic-EU`, `HC-EU` and `SoD-EU`
side by side, and `extraAnniversaryRealms` uses `Fresh-EU` / `Fresh-US` rather
than an `Anniversary-` prefix. Matching on the trailing two-letter code merges
game modes that are genuinely separate.

**RealmEntry** (realm or region object):

```json
{
  "id": 1234,
  "name": "Tarren Mill",
  "region": "EU",
  "appDataStrings": {
    "AUCTIONDB_NON_COMMODITY_DATA": {
      "url": "https://cdn.tradeskillmaster.com/...",
      "lastModified": 1710000000
    },
    "AUCTIONDB_REGION_STAT": {
      "url": "https://cdn.tradeskillmaster.com/...",
      "lastModified": 1710000000
    }
    // ... more tags
  }
}
```

Region entries use the same structure but `name` contains the region identifier
(e.g. `"EU"`, `"US"`) and `region` may be absent.

**Game version mapping:**

| Status key                                           | WoW directory   | API `game_version` |
| ---------------------------------------------------- | --------------- | ------------------ |
| `realms` / `regions`                                 | `_retail_`      | `retail`           |
| `realms-Progression` / `regions-Progression`         | `_classic_`     | `bcc`              |
| `extraClassicRealms` / `extraClassicRegions`         | `_classic_era_` | `classic`          |
| `extraAnniversaryRealms` / `extraAnniversaryRegions` | `_anniversary_` | `anniversary`      |

Display name transform for Progression realms: `BCC-EU` becomes `Progression-EU`.

---

### `GET /v2/addon/{name}`

Download an addon zip file.

| Parameter | Description                                          |
| --------- | ---------------------------------------------------- |
| `name`    | Addon name including the game-version suffix         |
| `channel` | _(optional)_ `"release"` or `"beta"`                 |

`name` carries the same suffix the status response uses for that game version:
`""` (retail), `-Classic`, `-Progression`, `-Anniversary`. The status response
also exposes `addons-Classic` and `addons-BCC` lists whose names already include
a suffix; both `-Progression` and `-BCC` are accepted for the `_classic_` client.

**No `tsm_version` parameter.** The endpoint is called without it in the original
client. As of 2026-08 the server tolerates one, but sending the version of the
addon being requested was never correct.

Response: `application/zip` - raw bytes of the zip archive. The endpoint has also
answered with a JSON `{"url": "..."}` CDN redirect (seen 2026-05), so a client
must handle both. The zip's top-level folder is the addon name **without** the
suffix, so all four packages extract to e.g. `TradeSkillMaster_AppHelper/`.

---

### `GET /v2/realms2/list`

List the **full catalogue** of realms the API knows about, not the account's own
realms. Measured 2026-08-27: 558 retail realms across EU/KR/TW/US and 226 bcc
realms. This is the source for the Add Realm dropdown.

Response:

```json
{
  "success": true,
  "retail": [ ... ],
  "bcc": [ ... ]
}
```

Both arrays contain `RealmEntry[]`, but with a **bare** region and an integer id:

```json
{ "id": 1, "masterId": 1, "name": "Anathema-Alliance", "region": "US" }
```

Note the region differs from what `/v2/status` reports for the same realm. A bcc
realm listed here as `region: "EU"` appears in `realms-Progression` as
`region: "BCC-EU"` with a string id such as `"106-BCC"`. Do not use a region
string from this endpoint as a key against status data.

---

### `GET /v2/realms2/add/{game_version}/{realm_id}`

Register a realm to the user's account.

| Parameter      | Description                               |
| -------------- | ----------------------------------------- |
| `game_version` | `retail`, `bcc`, `classic`, `anniversary` |
| `realm_id`     | Integer realm ID                          |

Response: confirmation object (structure varies).

---

### `GET /v2/realms2/remove/{game_version}/{region}/{realm}`

Remove a realm from the user's account.

| Parameter      | Description                               |
| -------------- | ----------------------------------------- |
| `game_version` | `retail`, `bcc`, `classic`, `anniversary` |
| `region`       | Region string, e.g. `EU`                  |
| `realm`        | Realm name slug, e.g. `Tarren Mill`       |

Response: confirmation object (structure varies).

---

## AppData Download Flow

This is the core data sync flow, equivalent to what `MainThread.pyc` does on a
regular interval.

```
1. GET /v2/status
       |
       v
2. For each game version where TSM_AppHelper is installed:
       |
       v
3. For each realm/region in the status response:
   a. Read local AppData.lua to get stored lastModified per tag
   b. Compare with lastModified values in appDataStrings
   c. If remote lastModified > local: add to pending downloads
       |
       v
4. For each pending (tag, realm) pair:
   - Download blob from appDataStrings[tag].url (CDN, no auth required)
   - If blob starts with gzip magic bytes (0x1f 0x8b): decompress
   - Otherwise: decode as UTF-8
   - Check that response is not an HTML error page
       |
       v
5. Write all downloaded blobs into AppData.lua using LoadData() format
6. Save snapshot to local SQLite cache
```

### AppData.lua format

Each data blob is written as a Lua `LoadData()` call:

```lua
select(2, ...).LoadData("TAG","RealmOrRegion",[[return {downloadTime=N,...}]])
```

The data blob received from the CDN is the verbatim content of the Lua expression
inside `[[...]]`. The `downloadTime` field within the blob is the `lastModified`
timestamp from the API.

---

## AppData Tags

Tags observed in real `AppData.lua` files:

| Tag                                  | Scope      | Description                                         |
| ------------------------------------ | ---------- | --------------------------------------------------- |
| `APP_INFO`                           | Global     | App version, last sync timestamp, broadcast message |
| `AUCTIONDB_NON_COMMODITY_DATA`       | Per-realm  | Current item prices (non-commodity auctions)        |
| `AUCTIONDB_NON_COMMODITY_HISTORICAL` | Per-realm  | Historical price data                               |
| `AUCTIONDB_NON_COMMODITY_SCAN_STAT`  | Per-realm  | Scan statistics                                     |
| `AUCTIONDB_COMMODITY_DATA`           | Per-region | Commodity (stackable) item prices                   |
| `AUCTIONDB_COMMODITY_HISTORICAL`     | Per-region | Commodity historical prices                         |
| `AUCTIONDB_COMMODITY_SCAN_STAT`      | Per-region | Commodity scan statistics                           |
| `AUCTIONDB_REGION_STAT`              | Per-region | Region-wide item statistics                         |
| `AUCTIONDB_REGION_SALE`              | Per-region | Region-wide sale data                               |
| `AUCTIONDB_REGION_HISTORICAL`        | Per-region | Region-wide historical data                         |

The key tags used for staleness detection:

- **Realm data:** `AUCTIONDB_NON_COMMODITY_DATA` - `lastModified` is used as the
  realm's "last updated" display timestamp.
- **Region data:** `AUCTIONDB_REGION_STAT` - same purpose for region rows.

---

## Scheduled Jobs

The original app runs these jobs on a timer:

| Job                | Interval         | Description                               |
| ------------------ | ---------------- | ----------------------------------------- |
| Auction data sync  | Every 60 minutes | Full status + download cycle              |
| Auth token refresh | Every 25 minutes | Re-exchanges OIDC token to extend session |

The Linux port refreshes auth every 5 minutes instead, because the session no
longer lives 25 minutes. See the note below.
| WoW install scan   | Every 5 minutes  | Detects new/removed WoW installs          |
| Addon update check | Every 6 hours    | Checks `addons` list from status response |

---

## Known Limitations and Observations

- **No HTTPS for API calls.** All `/v2/` calls use plain HTTP. Only the OIDC step
  uses HTTPS.
- **Shared HMAC secret.** The secret `3FB1CC5EDC5B43F21CB8ACC23B42B703` is
  hardcoded in the distributed app binary and is the same for all users.
- **Session tokens last about 10 minutes.** Measured 2026-08-27 by polling a
  single session: `/v2/status` and `/v2/addon` both answered normally at 9m07s
  after login and both returned `{"success": false, "error": "Invalid request."}`
  at 10m07s. The original app's 25 minute refresh interval is no longer short
  enough, and a rejected session never recovers on its own: the same token keeps
  being sent until the client logs in again.
- **CDN URLs require no authentication.** The blob download URLs returned by the
  status endpoint are public CDN URLs and can be fetched without any credentials.
- **AppHelper detection is required.** If `TSM_AppHelper/AppData.lua` is not found
  in a WoW install directory, the server's realm list is still fetched but no data
  is written. The UI shows no realms.
- **Gzip handling is dual-path.** The aiohttp client auto-decompresses
  `Content-Encoding: gzip`, but the CDN sometimes returns raw gzip bytes without
  the header. The client checks the magic bytes (`\x1f\x8b`) and decompresses
  manually if needed.
- **HTML error detection.** The client checks whether the downloaded blob contains
  `<html>` and discards it if so, treating it as an error response from an
  intermediate proxy.
- **`realms2` and `auth` always use `app-server`.** These endpoints are not
  remapped by `endpointSubdomains`; the subdomain is hardcoded in the client.
- **`endpointSubdomains` is per session.** `addon` and `auctiondb` are handed out
  as `app-server4` or `app-server5` and can differ between two logins seconds
  apart. A long-running client that holds one session keeps whatever mapping it
  was given, so a rejected call needs a fresh login rather than a plain retry.
