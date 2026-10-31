# Changelog

Minden lényeges változás ebben a fájlban szerepel. A formátum a
[Keep a Changelog](https://keepachangelog.com/hu/1.1.0/) szerint készült, a verziózás
[SemVer](https://semver.org/lang/hu/). Szerző: **Aiasz**; az ötletgazdák a `CREDITS.md`-ben.

A `B##` / `F##` / `M#` / `S#` azonosítók a fejlesztési terv (`PLAN.md`) tételeire hivatkoznak.

## [1.5.0] – 2026-10-31

Alapok, hibajavítások és az angol nyelvű változat. **Visszafelé kompatibilis**: a meglévő
entitások `unique_id`-ja és `entity_id`-ja nem változik, a beállítások automatikusan migrálódnak.

### Hozzáadva
- **Angol nyelvű változat (M1)** – minden entitásnév és a teljes beállítófelület fordítható
  (`strings.json` az angol forrás, `translations/en.json`, `translations/hu.json`).
  Ötletgazda: **ztarsoly** ([#1 issue](https://github.com/aiasz/ha-wunderground-pws/issues/1)).
- **Szolgáltató-réteg (F01)** – `providers/` csomag egységes hibatípusokkal (`ProviderError`,
  `ProviderAuthError`, `ProviderNoDataError`, `ProviderRateLimitError`) és közös HTTP-segéddel.
- **Állomás online / offline (F08)** – `binary_sensor.…_station_online` és `…_observation_age`
  diagnosztikai szenzor; hihetőségi tartományok: egy kiugró mérés helyett az előző jó érték marad.
- **Újrahitelesítés (F18)** – ha az API kulcs nem használható és az automatikus keresés sem segít,
  a Home Assistant újrahitelesítést kér (üresen hagyva újra próbálja az automatikus keresést).
- **Nyelvfüggetlen szélirány-szenzor** (`wind_compass`, enum): a felületen a nyelvnek megfelelő
  felirat (N/NE… vagy É/ÉK…). A régi „Szélirány (magyar)” szenzor változatlanul megmaradt.
- **Nedves hőmérséklet szenzor (F13)** – Stull (2011) képlet; alapból kikapcsolt.
- `weather` entitás: érzett hőmérséklet, harmatpont, széllökés, csapadék-valószínűség, UV,
  felhőzet az előrejelzésben; `forecast_stale` és `forecast_updated` attribútum.
- Forrásmegjelölés (`attribution`) a használt adatforrásokról.
- Tesztek (146), CI (hassfest, HACS, ruff, pytest), `LICENSE` (MIT), `CHANGELOG`, `CREDITS`.

### Javítva
- **WU előrejelzés (B01, B02):** a nappali/éjszakai (`daypart`) tömbök indexelése hibás volt – a 2.
  naptól kezdve rossz nap ikonja jelent meg; az ikonkód → állapot leképezés a Weather Company
  táblája szerint javítva (pl. „tiszta éjszaka” már nem „napos”). A végpont: a PWS-kulcsokkal
  használható **`5day`** termék elsőként, **`7day`** tartalékként (korábban csak `7day`, amit az ilyen
  kulcsokkal a WU elutasíthatott, így az előrejelzés csendben a következő forrásra esett vissza).
- **MET.no csapadék (B03):** az átfedő 6 órás ablakok többszörösen összegződtek (akár 6× túlbecslés);
  a nulla érték is érvényes mennyiség.
- **Helyi napok (B04):** a MET.no napi min/max UTC helyett a Home Assistant időzónája szerint.
- **Éjszakai állapot (B05, F15):** a jelenlegi állapot éjszaka mindig „felhős” volt; mostantól a
  Nap állása (`clear-night`), hó/ónos eső, köd, erős szél és a napsugárzás alapú derültség-becslés.
- **Opciók felülírták a kulcsot (B06):** egy üresen elmentett `api_key` opció minden újratöltéskor
  újabb kulcskeresést indított; a beállítások egyetlen helyre (`entry.data`) kerülnek (konfig-verzió 3).
- **Előrejelzés elvesztése (B07):** hiba esetén az utolsó jó előrejelzés megmarad (legfeljebb 12 óráig),
  a megfigyelés frissítését a lassú/hibás előrejelzés nem érinti.
- **Felesleges hívások (B08):** az előrejelzés külön, 30 perces gyorsítótárral frissül; a város
  geokódolása egyszer fut és tartósan tárolódik; a MET.no az `Expires` / `If-Modified-Since` szerint.
- **Előrejelzés-kártya frissülése (B09), RFC 3339 időbélyegek (B10).**
- **Érzett hőmérséklet (B11):** hidegben szélhűtés, melegben hőindex, egyébként a levegő hőmérséklete.
- **Beállítási hibák (B12):** külön hibaüzenet rossz kulcsra, ismeretlen állomásra és hálózati hibára.
- **Állomás módosítása az opciókban (B13):** az állomásazonosító nem szerkeszthető (árva entitásokat
  okozott); a korábban így módosított bejegyzések a migráció során megtartják az entitásaikat.
- **Hard-code-olt verziószöveg és magyar nevek (B14), felhőalap-képlet (B18).**

### Megjegyzés – demo mód (D1)
A demo mód (üres API kulcs → automatikus kulcskeresés) **megmaradt**, megerősítve: a talált kulcs
mentés előtt egy valódi hívással ellenőrzésre kerül, sikertelen keresés után várakozási idő van
(15 perc, legfeljebb 3 próba), a kézzel megadott kulcsot a rendszer soha nem cseréli le csendben.
**Ismert korlát:** az automatikusan kinyert (megosztott) kulcsot a Weather Underground bármikor
elutasíthatja – a 2026-10-31-i ellenőrzéskor a weboldalról kinyert kulcsot már a megfigyelés
végpontja sem fogadta el (`apikey is not authorized for this product`). Megbízható működéshez
saját API kulcs szükséges: <https://www.wunderground.com/member/api-keys>.

### Eltávolítva / módosítva
- A `manifest.json`-ból az `aiohttp` követelmény kikerült (a Home Assistant része).
- Minimum Home Assistant verzió: **2024.12.0**.

## [1.4.1] – 2026-04-07
- Javítás: NaN km/h szélsebesség az előrejelzés kártyán. Készítő: Aiasz

## [1.4.0] – 2026-04-07
- Többforrású előrejelzés (WU → MET.no → Open-Meteo) automatikus fallback-kel. Készítő: Aiasz

## [1.3.0] – 2026-03-02
- Demo mód, automatikus kulcs-beszerzés és -újrabeszerzés. Készítő: Aiasz

## [1.2.0] – 2026-02-27
- API-alapú lekérdezés, 7 napos előrejelzés, előrejelzési város, számított szenzorok. Készítő: Aiasz

## [1.1.0] / [1.0.0]
- API-alapú megközelítés; az első kiadás HTML-scrape alapú volt. Készítő: Aiasz
