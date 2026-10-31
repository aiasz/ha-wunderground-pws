# Wunderground PWS – Home Assistant integration

**Author: Aiasz · Version 1.5.0 · [Magyar README](README.md)**

Shows the data of any [Weather Underground](https://www.wunderground.com/) personal weather station (PWS)
in Home Assistant through the **official WU API**, in metric units, and adds a **multi-provider forecast**
(Weather Underground, MET Norway, Open-Meteo) with an automatic fallback chain. Available in English and Hungarian.

> Roadmap and release notes: [CHANGELOG](CHANGELOG.md). Credits and idea sources: [CREDITS](CREDITS.md).

## Features

- **Your own station's measurements**: temperature, feels-like, dew point, heat index / wind chill, humidity,
  pressure, wind (speed, gust, bearing, compass), precipitation (daily, rate), solar radiation, UV and derived
  values (cloud base, absolute humidity, wet-bulb temperature).
- **Weather entity** with a daily forecast (7 days, or what the source provides).
- **Multi-source forecast with fallback**: Weather Underground → MET Norway → Open-Meteo (or a single chosen source).
- **English and Hungarian UI** – follows the Home Assistant language (entity names, options, wind direction).
- **Station health**: `Station online` and `Observation age` diagnostic entities; glitchy readings are filtered out.
- **Better "current condition"**: `clear-night`, snow/sleet, fog, strong wind, sky state from solar radiation.
- **Resilient**: a failing forecast never blocks the measurements; the last good forecast is kept; the forecast
  and the city geocoding are cached (fewer API calls).
- **Demo mode** (optional API key): see below.

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
| Forecast source | `auto` / WU only / MET Norway only / Open-Meteo only |

### Demo mode (no API key)
With an empty key the integration tries to extract a public key embedded in the WU website and **validates it
with a real call** before saving it. After a failed attempt it waits 15 minutes (max. 3 attempts), then Home Assistant
asks you to re-authenticate. A key you typed yourself is never replaced automatically.

> **Important:** the shared key can be refused by WU at any time (on 2026-10-31 the key extracted from the website
> was already rejected by the observation endpoint). **For reliable, long-term use get your own API key** – WU gives it
> free to PWS owners: <https://www.wunderground.com/member/api-keys>. Without a key the forecast can still come from
> MET Norway / Open-Meteo (`metno` / `openmeteo` source), but the station's measurements need a key.

## Data sources

| Data | Source | Key |
|---|---|---|
| Current measurements | Weather Underground `v2/pws/observations/current` | yes |
| Forecast | WU `v3/wx/forecast/daily/5day` (fallback: `7day`) | yes |
| Forecast | MET Norway Locationforecast 2.0 (CC BY 4.0) | no |
| Forecast, geocoding | Open-Meteo (CC BY 4.0) | no |

Required attributions: see [CREDITS](CREDITS.md). The `forecast_source_used` attribute shows which source answered.

## Weather card

```yaml
type: weather-forecast
entity: weather.wunderground_pws_ikapos27_weather
forecast_type: daily
```

## Upgrading
Existing entries migrate automatically (config version 3); entity ids do not change.

## Development & licence
See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Report bugs and ideas on [GitHub Issues](https://github.com/aiasz/ha-wunderground-pws/issues).
MIT – Author: Aiasz ([LICENSE](LICENSE)).
