# Wunderground PWS – Home Assistant Custom Integration

Ez a custom integration lehetővé teszi, hogy bármely [Weather Underground](https://www.wunderground.com/) személyes időjárás-állomás (PWS) adatait megjelenítsd a Home Assistantban.

## Funkciók

- **Változtatható URL**: bármely PWS dashboard URL megadható
- **Állítható frissítési időköz**: 1–60 perc
- **Weather entity**: kompatibilis a HA időjárás kártyákkal
- **Sensor entitások**: hőmérséklet, páratartalom, szél, csapadék, UV, napenergia, stb.
- **Options Flow**: URL és frissítés menet közben módosítható, újraindítás nélkül

## Telepítés

### HACS (ajánlott)

1. HACS → Integrations → `+` → `Custom repositories`
2. Add hozzá ezt a repo URL-t: `https://github.com/aiasz/ha-wunderground-pws`
3. Kategória: `Integration`
4. Telepítés után indítsd újra a HA-t

### Manuális

1. Másold a `custom_components/wunderground_pws` mappát a HA `config/custom_components/` könyvtárába
2. Indítsd újra a Home Assistantot

## Beállítás

1. **Settings → Devices & Services → Add Integration**
2. Keress rá: `Wunderground PWS`
3. Add meg az URL-t (alapértelmezett: `https://www.wunderground.com/dashboard/pws/IKAPOS27`)
4. Add meg a frissítési időközt percben (1–60)

## Sensor entitások

| Entitás | Leírás | Egység |
|---|---|---|
| `sensor.temperature` | Hőmérséklet | °C |
| `sensor.humidity` | Páratartalom | % |
| `sensor.pressure` | Légnyomás | hPa |
| `sensor.wind_speed` | Szélsebesség | km/h |
| `sensor.wind_gust` | Széllökés | km/h |
| `sensor.wind_bearing` | Szélirány | ° |
| `sensor.precipitation` | Napi csapadék | mm |
| `sensor.precipitation_rate` | Csapadék intenzitás | mm/h |
| `sensor.solar_radiation` | Napsugárzás | W/m² |
| `sensor.uv_index` | UV index | UV |
| `sensor.dew_point` | Harmatpont | °C |
| `sensor.feels_like` | Érzett hőmérséklet | °C |

## Időjárás kártya

```yaml
type: weather-forecast
entity: weather.wunderground_pws_ikapos27
```

## Beállítások módosítása

Settings → Devices & Services → Wunderground PWS → **Configure** gomb → URL és frissítési időköz módosítható.

## Licenc

MIT
