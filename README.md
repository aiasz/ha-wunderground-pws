# Wunderground PWS - Home Assistant Custom Integration

**Készítő: Aiasz | Verzió: 1.2.0**

Ez a custom integration lehetővé teszi, hogy bármelyik [Weather Underground](https://www.wunderground.com/) személyes időjárás-állomás (PWS) adatait megjelenítsd a Home Assistantban — közvetlenül az **official WU API**-n keresztül, imperial → metrikus konverzióval.

---

## Funkciók

- **Állítható állomás azonosító**: bármely WU PWS állomás azonosító megadható (pl. IKAPOS27)
- **API kulcs**: a WU API kulcs a UI-ban kérhető be
- **Állítható frissítési időköz**: 1–60 perc között, menet közben is módosítható
- **Weather entity**: kompatibilis a HA időjárás kártyákkal
- **12 sensor entitás**: hőmérséklet, érzett hőmérséklet, harmatpont, páratartalom, légnyomás, szélerősség, széllökés, szélirány (fokkal és égtájjal), csapadék, csapadék-intenzitás, napsugárzás, UV-index
- **Imperiális → metrikus konverzió**: F→C, mph→km/h, inHg→hPa, inch→mm
- **Options Flow**: beállítások újraindítás nélkül módosíthatóak

---

## Adatok forrása

Az integráció a WU PWS "Current Observations" API végpontját használja:
```
https://api.weather.com/v2/pws/observations/current
```
Parameterek: `stationId`, `format=json`, `units=e` (imperial, majd konvertálva metrikusra), `apiKey`

---

## Telepítés

### HACS (ajánlott)
1. HACS -> Integrations -> `+` -> `Custom repositories`
2. Add hozzá: `https://github.com/aiasz/ha-wunderground-pws` (kategória: Integration)
3. Telepítés után indítsd újra a HA-t

### Manuális
1. Másold a `custom_components/wunderground_pws` mappát a HA `config/custom_components/` könyvtárába
2. Indítsd újra a Home Assistantot

---

## Beállítás

1. **Settings -> Devices & Services -> Add Integration**
2. Keresd: `Wunderground PWS`
3. Add meg az **Állomás azonosítót** (pl. `IKAPOS27`)
4. Add meg az **API kulcsot** (WU fiókodban található)
5. Add meg a **frissítési időközt** percben (1–60)

### Beállítások módosítása
**Settings -> Devices & Services -> Wunderground PWS -> Configure**

---

## Időjárás kártya

```yaml
type: weather-forecast
entity: weather.wunderground_pws_ikapos27
```

---

## Verziótörténet

### v1.2.0 (2026-02-27)
- **API-alapú adatlekérdezés** (többé nincs HTML scraping)
- Imperiális → metrikus konverzió (F→C, mph→km/h, inHg→hPa, inch→mm)
- Szélirány fokkal és égtájjal (pl. SE)
- API kulcs bekerült a UI beállításába
- BeautifulSoup függőség eltávolítva
- Készítő: Aiasz

### v1.0.0
- Első kiadás - HTML dashboard scraping

---

## Licenc

MIT License - Készítő: Aiasz
