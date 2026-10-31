# Köszönet és forrásmegjelölés / Credits

Szerző / Author: **Aiasz** – licenc / licence: MIT (`LICENSE`).

## Ötletgazdák és hasonló projektek

A projekt **kódot nem vesz át** más projektekből; az alábbiak *ötletforrások*. Ahol egy
megoldás más ötletén alapul, a forráskódban `Ötlet:` / `Idea:` megjegyzés jelzi.

| Funkció | Ötletgazda / projekt | Licenc | Mi származik tőle |
|---|---|---|---|
| Angol nyelvű változat, óránkénti előrejelzés, csapadék/pollen/levegőminőség | **ztarsoly (Zoli)** – [#1 issue](https://github.com/aiasz/ha-wunderground-pws/issues/1) | – | a három kért funkció |
| Kulcs nélküli megfigyelés-fallback (F09, v1.6.1) – a nyilvános WU városi oldal ötlete és élő ellenőrzése | **Aiasz** (a felhasználó saját tesztje a `wunderground.com/weather/hu/…` oldalon) | – | a fallback-forrás azonosítása és a kulcsot/hitelesítést nem igénylő megoldás iránya |
| HU+EN felület, tartós előrejelzés-tár, figyelmeztetés-szenzorok (terv) | [ztarsoly/ha-idokep-weather-and-forecast](https://github.com/ztarsoly/ha-idokep-weather-and-forecast) | MIT | csak funkcióötlet (az Időkép-adatot nem használjuk) |
| HungaroMet közeli állomások, radar (terv) | [FabianGabor/HA-HungaroMet](https://github.com/FabianGabor/HA-HungaroMet), [ztarsoly/ha-hungaromet-weather-and-forecast](https://github.com/ztarsoly/ha-hungaromet-weather-and-forecast) | nincs megadva / MIT | csak ötlet |
| Figyelmeztetések (terv) | [amaximus/met_alerts_hu](https://github.com/amaximus/met_alerts_hu) | MIT | csak ötlet |
| WU PWS: előrejelzési termék (`5day`), `daypart` szerkezet, újrahitelesítés, nyelv | [cytech/Home-Assistant-wundergroundpws](https://github.com/cytech/Home-Assistant-wundergroundpws) | nem megállapítható | megfigyelések a dokumentációjából; kódot nem vettünk át |

## Adatforrások és kötelező jelölések

| Forrás | Jelölés / feltétel |
|---|---|
| Weather Underground / The Weather Company | a megfigyelések és az előrejelzés forrása; saját PWS-tulajdonosi API kulcs ajánlott |
| MET Norway | Locationforecast 2.0, **CC BY 4.0**; kötelező azonosító `User-Agent`, `Expires`/`If-Modified-Since` betartása – az integráció így működik |
| Open-Meteo | **CC BY 4.0**, <https://open-meteo.com/>; ingyenes, nem kereskedelmi használat (600/perc, 5 000/óra, 10 000/nap) |
| HungaroMet (tervezett) | *„Database: Meteorological Database, HungaroMet Nonprofit Zrt.”*; módosítatlan adat, a figyelmeztetések csak módosítás nélkül |

## Képletek

- Szélhűtés: Environment Canada / NWS (2001) · Nedves hőmérséklet: Stull (2011), *J. Appl. Meteor. Climatol.* ·
  Felhőalap: Espy-közelítés (125 m/°C) · Derült égbolti sugárzás: Kasten & Czeplak (1980) ·
  Nap magassága: NOAA General Solar Position Calculations.
