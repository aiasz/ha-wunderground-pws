# Wunderground PWS - Home Assistant Custom Integration

**Készítő: Aiasz | Verzió: 1.3.0**

Ez a custom integration lehetővé teszi, hogy bármelyik [Weather Underground](https://www.wunderground.com/) személyes időjárás-állomás (PWS) adatait megjelenítsd a Home Assistantban — közvetlenül az **official WU API**-n keresztül, imperial → metrikus konverzióval.  
Az előrejelzés adatokat a **[Open-Meteo](https://open-meteo.com/)** ingyenes API-ja biztosítja egy opcionálisan megadott város alapján.

---

## Funkciók

- **Állítható állomás azonosító**: bármely WU PWS állomás azonosító megadható (pl. IKAPOS27)
- **API kulcs (opcionális)**: saját kulcs megadható, de **nem kötelező** — ha üresen hagyod, az integráció automatikusan beszerez egy működő kulcsot (demo/tesztelési mód)
- **Automatikus kulcs-újrabeszerzés**: ha a kulcs lejár vagy érvénytelenné válik, az integráció futás közben önállóan beszerez egy újat és elmenti
- **Állítható frissítési időköz**: 1–60 perc között, menet közben is módosítható
- **Opcionális előrejelzési város**: a HA időjárás kártyán 7 napos előrejelzés jelenik meg (pl. Kaposvár)
- **Weather entity**: kompatibilis a HA időjárás kártyákkal, 7 napos előrejelzéssel
- **16 sensor entitás**: hőmérséklet, érzett hőmérséklet, harmatpont, hőérzet index, szélhűtési index, páratartalom, légnyomás, szélerősség, széllökés, szélirány (fokkal), szélirány (magyar égtáj), csapadék, csapadék-intenzitás, napsugárzás, abszolút páratartalom, felhőalap, UV-index
- **Imperiális → metrikus konverzió**: F→C, mph→km/h, inHg→hPa, inch→mm
- **Options Flow**: beállítások újraindítás nélkül módosíthatóak

---

## Demo / tesztelési mód (API kulcs nélkül)

Az integráció **API kulcs megadása nélkül is elindítható**. Ilyen esetben az első inicializáláskor az integráció automatikusan beszerez egy nyilvánosan elérhető kulcsot, és azt elmenti — így a következő újraindításkor már azt használja, nem kér le újat feleslegesen.

| Helyzet | Mi történik? |
|---|---|
| API kulcs nincs megadva | Első induláskor automatikusan beszerzi és elmenti |
| Saját kulcs van megadva | Azt használja, auto-keresés nem fut |
| A kulcs lejár / érvénytelen lesz (401/403 hiba) | Automatikusan new kulcsot szerez és elmenti |
| Auto-keresés sikertelen (max. 3 kísérlet) | Hibaüzenet, manuális megadás szükséges |

> **Megjegyzés:** A demo módban szerzett kulcs egy nyilvánosan elérhető, megosztott kulcs. Tartós, megbízható használathoz ajánlott saját WU API kulcsot igényelni a [Weather Underground](https://www.wunderground.com/member/api-keys) oldalán.

---

## Adatok forrása

| Adat | Forrás | API |
|---|---|---|
| Jelenlegi időjárás (PWS mérés) | Weather Underground | WU API kulccsal (auto vagy saját) |
| 7 napos előrejelzés | Open-Meteo | ingyenes, kulcs nélkül |
| Geocoding (város → koordináta) | Open-Meteo Geocoding | ingyenes, kulcs nélkül |

WU megfigyelés végpontja:
```
https://api.weather.com/v2/pws/observations/current
```
Open-Meteo előrejelzés:
```
https://api.open-meteo.com/v1/forecast
```
Open-Meteo Geocoding:
```
https://geocoding-api.open-meteo.com/v1/search
```

---

## Telepítés

### HACS (ajánlott)
1. HACS -> Integrations -> `+` -> `Custom repositories`
2. Add hozzá: `https://github.com/aiasz/ha-wunderground-pws` (kategória: Integration)
3. Telepítés után indítsd újra a HA-t

### Manuális
1. Másold a `custom_components/wunderground_pws` mappát a HA `config/custom_components/` könyvtárába
2. Töröld a `__pycache__` mappát ha létezik
3. Indítsd újra a Home Assistantot

---

## Beállítás

1. **Settings -> Devices & Services -> Add Integration**
2. Keresd: `Wunderground PWS`
3. Add meg az **Állomás azonosítót** (pl. `IKAPOS27`)
4. Az **API kulcs** mező **opcionális**:
   - **Üresen hagyva** → az integráció automatikusan beszerzi és elmenti a kulcsot (demo mód), majd megerősítő képernyőn mutatja a talált kulcsot
   - **Saját kulcs megadva** → azt használja közvetlenül
5. Add meg a **frissítési időközt** percben (1–60)
6. Add meg az **előrejelzési várost** *(opcionális)* — pl. `Kaposvár` vagy `Budapest`  
   _(Ha üresen hagyod, az állomás koordinátái alapján töltődik be az előrejelzés.)_

### Beállítások módosítása
**Settings -> Devices & Services -> Wunderground PWS -> Configure**

> Az API kulcs mező itt is üresen hagyható — az integráció újratöltéskor automatikusan beszerzi az új kulcsot.

---

## Időjárás kártya (7 napos előrejelzéssel)

```yaml
type: weather-forecast
entity: weather.wunderground_pws_ikapos27
forecast_type: daily
```

---

## Szenzor lista

| Szenzor | Egység | Leírás |
|---|---|---|
| Hőmérséklet | °C | Mért hőmérséklet |
| Érzett hőmérséklet | °C | Hőérzet (heat index) |
| Harmatpont | °C | Harmatpont hőmérséklet |
| Hőérzet index | °C | Heat index |
| Szélhűtési index | °C | Wind chill (ha temp < 10°C) |
| Páratartalom | % | Relatív páratartalom |
| Abszolút páratartalom | g/m³ | Számított abszolút páratartalom |
| Légnyomás | hPa | Tengerszinti légnyomás |
| Szélerősség | km/h | Szélsebesség |
| Széllökés | km/h | Maximális széllökés |
| Szélirány (fok) | ° | Szélirány fokokban |
| Szélirány (magyar) | — | Magyar égtáj (pl. ÉK, DNy) |
| Csapadék (ma) | mm | Napi csapadék összesen |
| Csapadék intenzitás | mm/h | Aktuális csapadék intenzitás |
| Napsugárzás | W/m² | Globális napsugárzás |
| Felhőalap | m | Számított felhőalap magasság |
| UV-index | — | UV sugárzás indexe |

---

## Verziótörténet

### v1.3.0 (2026-03-02)
- **Demo / tesztelési mód**: API kulcs megadása nélkül is működik
- **Automatikus kulcs-beszerzés**: ha nincs megadva kulcs, az integráció induláskor automatikusan beszerzi
- **Automatikus kulcs-újrabeszerzés**: 401/403 API hiba esetén futás közben is megújítja a kulcsot és elmenti
- **Kétlépéses telepítési folyamat**: API kulcs nélkül egy megerősítő képernyő jelenik meg a talált kulccsal
- Készítő: Aiasz

### v1.2.0 (2026-02-27)
- **API-alapú adatlekérdezés** (nincs HTML scraping)
- **7 napos előrejelzés** az időjárás kártyán (Open-Meteo, ingyenes)
- **Előrejelzési város** megadható a UI-ban (Open-Meteo geocoding)
- **Szélirány (magyar égtáj)** önálló szenzorként visszakerült
- Imperiális → metrikus konverzió (F→C, mph→km/h, inHg→hPa, inch→mm)
- Új számított szenzorök: felhőalap, abszolút páratartalom, szélhűtési index
- API kulcs bekerült a UI beállításába
- Készítő: Aiasz

### v1.1.0
- API-alapú megközelítés, BeautifulSoup függőség eltávolítva

### v1.0.0
- Első kiadás - HTML dashboard scraping

---

## Licenc

MIT License - Készítő: Aiasz
