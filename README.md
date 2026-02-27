# Wunderground PWS - Home Assistant Custom Integration

**Keszito: Aiasz | Verzio: 1.1.0**

Ez a custom integration lehetove teszi, hogy barmelyik [Weather Underground](https://www.wunderground.com/) szemelyes idojaras-allomas (PWS) adatait megjelenitsed a Home Assistantban — kozvetlenul az **official WU API**-n keresztul, imperial -> metrikus konverzioVal.

---

## Funkciok

- **Allitható allomas azonosito**: barmely WU PWS allomas azonosito megadhato (pl. IKAPOS27)
- **API kulcs**: a WU API kulcs a UI-ban kerheto be
- **Allithato frissitesi idokoz**: 1-60 perc kozott, menet kozben is modosithato
- **Weather entity**: kompatibilis a HA idojaras kartyakkal
- **12 sensor entitas**: homerseklet, erzett homerseklet, harmatpont, paratartalom, legnyomas, szelsebesség, szellokes, szelfok (fokkal es egtajjal), csapadek, csapadek-intenzitas, napenergia, UV-index
- **Imperial -> metrikus konverzio**: F->C, mph->km/h, inHg->hPa, inch->mm
- **Options Flow**: beallitasok ujrainditas nelkul modosíthatoak

---

## Adatok forrasa

Az integracioa a WU PWS "Current Observations" API vegpontot hasznáalja:
```
https://api.weather.com/v2/pws/observations/current
```
Parameterek: `stationId`, `format=json`, `units=e` (imperial, majd konvertalva metrikusra), `apiKey`

---

## Telepites

### HACS (ajanlo tt)
1. HACS -> Integrations -> `+` -> `Custom repositories`
2. Add hozza: `https://github.com/aiasz/ha-wunderground-pws` (kategoria: Integration)
3. Telepites utan inditsd ujra a HA-t

### Manualis
1. Masold a `custom_components/wunderground_pws` mappat a HA `config/custom_components/` konyvtaraba
2. Inditsd ujra a Home Assistantot

---

## Beallitas

1. **Settings -> Devices & Services -> Add Integration**
2. Keresd: `Wunderground PWS`
3. Add meg az **Allomas azonositot** (pl. `IKAPOS27`)
4. Add meg az **API kulcsot** (WU fiokodban talalhato)
5. Add meg a **frissitesi idokozt** percben (1-60)

### Beallitasok modositasa
**Settings -> Devices & Services -> Wunderground PWS -> Configure**

---

## Idojaras kartya

```yaml
type: weather-forecast
entity: weather.wunderground_pws_ikapos27
```

---

## Verziotortenet

### v1.1.0 (2026-02-27)
- **API-alapu adatlekerdes** (tobbe nincs HTML scraping)
- Imperial -> metrikus konverzio (F->C, mph->km/h, inHg->hPa, inch->mm)
- Szelirany fokkal ES egtajjal (pl. SE)
- API kulcs bekerult a UI beallitasba
- BeautifulSoup fuggoseg eltavolitva
- Keszito: Aiasz

### v1.0.0
- Elso kiadás - HTML dashboard scraping

---

## Licenc

MIT License - Keszito: Aiasz
