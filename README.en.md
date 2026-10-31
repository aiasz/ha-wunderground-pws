# Wunderground PWS – Home Assistant integration

**Author: Aiasz · Version 1.6.1 · [Magyar README](README.md)**

Shows the data of any [Weather Underground](https://www.wunderground.com/) personal weather station (PWS)
in Home Assistant through the **official WU API**, in metric units, and adds a **multi-provider forecast**
(Weather Underground, MET Norway, Open-Meteo) with an automatic fallback chain. Available in English and Hungarian.

> Roadmap and release notes: [CHANGELOG](CHANGELOG.md). Credits and idea sources: [CREDITS](CREDITS.md).

## Features

- **Your own station's measurements**: temperature, feels-like, dew point, heat index / wind chill, humidity,
  pressure, wind (speed, gust, bearing, compass), precipitation (daily, rate), solar radiation, UV and derived
  values (cloud base, absolute humidity, wet-bulb temperature).
- **Weather entity** with a daily (7 days) **and hourly (72 h)** forecast.
- **Multi-source forecast with fallback**: Weather Underground → MET Norway → Open-Meteo (or a single chosen source).
- **Blend (consensus) mode**: all sources together; the integration scores each source against *your own station's measurements* and weights the more accurate one higher.
- **Open-Meteo model choice**: automatic, ECMWF IFS, DWD ICON-EU.
- **Today's min/max** temperature and gust, **pressure tendency** (rising / steady / falling).
- **Diagnostics**: downloadable (redacted) diagnostics and a `wunderground_pws.refresh` service.
- **English and Hungarian UI** – follows the Home Assistant language (entity names, options, wind direction).
- **Station health**: `Station online` and `Observation age` diagnostic entities; glitchy readings are filtered out.
- **Better "current condition"**: `clear-night`, snow/sleet, fog, strong wind, sky state from solar radiation.
- **Resilient**: a failing forecast never blocks the measurements; the last good forecast is kept; the forecast
  and the city geocoding are cached (fewer API calls).
- **Demo mode** (optional API key): see below.
- **No-key observation fallback**: if the WU API is unavailable and a forecast city is set, the
  integration reads the nearest station's data from WU's public location page instead -
  transparently marked (`observation_source`, `fallback_source_station`).

## Installation

**HACS (recommended):** HACS → Integrations → `⋮` → *Custom repositories* → `https://github.com/aiasz/ha-wunderground-pws`
(category *Integration*) → install → restart Home Assistant.
**Manual:** copy `custom_components/wunderground_pws` into `config/custom_components/` and restart.
Minimum Home Assistant version: **2024.12.0**.

## Setup

*Settings → Devices & services → Add integration → "Wunderground PWS"*

| Field | Description |
|---|---|
| Station ID | e.g. `IKAPOS27` (cannot be changed later – add a new entry for another station) |
| API key | your key from the [WU account](https://www.wunderground.com/member/api-keys); **empty = demo mode** |
| Update interval | 1–60 minutes (5 recommended) |
| Forecast city | optional (e.g. `Kaposvár`); empty = the station's coordinates |
| Forecast source | `auto` / `blend` / WU only / MET Norway only / Open-Meteo only |
| Open-Meteo model | (options) automatic / ECMWF IFS / DWD ICON-EU / ICON seamless |

### Demo mode (no API key)
With an empty key the integration tries to extract a public key embedded in the WU website and **validates it
with a real call** before saving it. After a failed attempt it waits 15 minutes (max. 3 attempts), then Home Assistant
asks you to re-authenticate. A key you typed yourself is never replaced automatically.

> **Important:** the shared key can be refused by WU at any time (on 2026-10-31 the key extracted from the website
> was already rejected by the observation endpoint). **For reliable, long-term use get your own API key** – WU gives it
> free to PWS owners: <https://www.wunderground.com/member/api-keys>. Without a key the forecast can still come from
> MET Norway / Open-Meteo (`metno` / `openmeteo` source); if a forecast **city** is also set, observations work
> without a key too - from WU's own public location page (see "No-key observation fallback" below).

### No-key observation fallback (works without an API key or demo mode)
When the WU API is unavailable (no key, demo-mode key rejected) **and** a forecast **city** is set, the
integration reads current conditions (temperature, humidity, pressure, wind, dew point, precipitation) from
`wunderground.com/weather/hu/{city}` - a genuinely server-rendered public page (unlike `/dashboard/pws/{id}`,
which only fills in after JavaScript runs and therefore cannot be used here).

**Known limits, worth knowing:**
- This is WU's own choice of the *nearest* station for that city - **not necessarily** your own configured
  station. For Kaposvár it is currently `IKAPOS10`, not `IKAPOS27`. The actual source is always visible via the
  `observation_source` (`wunderground_api` / `wu_citypage`) and `fallback_source_station` attribute/sensor - it
  is never silently merged with your own station's identity.
- It scrapes an undocumented, unofficial page; if WU redesigns it this source can stop working (the integration
  degrades gracefully when that happens, it does not crash).
- A few values (wind gust, UV, solar radiation, exact wind degrees) are not on this page.

## Data sources

| Data | Source | Key |
|---|---|---|
| Current measurements | Weather Underground `v2/pws/observations/current` | yes |
| Current measurements (fallback, nearest station) | WU public location page (`weather/hu/…`), unofficial | no |
| Forecast | WU `v3/wx/forecast/daily/5day` (fallback: `7day`) | yes |
| Forecast | MET Norway Locationforecast 2.0 (CC BY 4.0) | no |
| Forecast, geocoding | Open-Meteo (CC BY 4.0) | no |

Required attributions: see [CREDITS](CREDITS.md). Hourly data comes from Open-Meteo or MET Norway (the WU PWS API has no hourly forecast). The `forecast_source_used` attribute shows which source answered.

## Kaposvár and Hungary
The defaults are tuned to the author's home town, **Kaposvár**: the setup form suggests station `IKAPOS27` and forecast city
`Kaposvár` (both editable). The geocoding runs once and is cached; verified against live data, Kaposvár resolves to
(46.3667, 17.8) and both Open-Meteo (automatic, ECMWF IFS, ICON-EU) and MET Norway forecasts parse correctly for it.
Other Hungarian towns work the same way; official HungaroMet data is planned for v1.8.

## Weather card

```yaml
type: weather-forecast
entity: weather.wunderground_pws_ikapos27_weather
forecast_type: hourly   # or: daily
```

## Upgrading
Existing entries migrate automatically (config version 3); entity ids do not change.

## Development & licence
See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Report bugs and ideas on [GitHub Issues](https://github.com/aiasz/ha-wunderground-pws/issues).
MIT – Author: Aiasz ([LICENSE](LICENSE)).
