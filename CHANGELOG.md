# Changelog

Minden lényeges változás ebben a fájlban szerepel. A formátum a
[Keep a Changelog](https://keepachangelog.com/hu/1.1.0/) szerint készült, a verziózás
[SemVer](https://semver.org/lang/hu/). Szerző: **Aiasz**; az ötletgazdák a `CREDITS.md`-ben.

A `B##` / `F##` / `M#` / `S#` azonosítók a fejlesztési terv (`PLAN.md`) tételeire hivatkoznak.

## [1.6.1] – 2026-10-31

Kulcs nélküli megfigyelés-tartalék (F09): nyilvános Weather Underground városi oldal.

### Hozzáadva
- **Megfigyelés-fallback kulcs nélkül (F09):** ha a hivatalos WU API nem elérhető (nincs kulcs, a
  kulcs elutasítva, az automatikus kulcskeresés kimerült), és be van állítva egy előrejelzési
  **város**, az integráció a WU **nyilvános, bejelentkezés nélküli** városi oldaláról
  (`wunderground.com/weather/{ország}/{város}`) olvassa ki az aktuális mérést – ez egy valódi,
  szerveren renderelt oldal (ellenőrizve: a `/dashboard/pws/{állomás}` oldallal szemben, amely
  JavaScript nélkül üres „no-data" vázat ad vissza, a városi oldal nyers HTTP-válasza tartalmazza
  a tényleges hőmérsékletet, páratartalmat, légnyomást, szelet, harmatpontot, csapadékot).
  **Fontos:** ez a WU saját választása szerinti *legközelebbi* állomás (pl. Kaposvárnál jelenleg
  `IKAPOS10`), **nem feltétlenül** a beállított állomás – ez mindig átlátszóan jelzett az
  `observation_source` és `fallback_source_station` attribútumban/szenzorban, soha nem keveredik
  össze a beállított állomás saját adatával.
- Az összes származtatott érték (érzett hőmérséklet, felhőalap, abszolút páratartalom, nedves
  hőmérséklet) a tartalék forrásnál is a megszokott, közös képletekkel számolódik.
- Új diagnosztikai szenzorok: `observation_source` (melyik forrás válaszolt), `source_station_id`
  (a tartalék forrás állomása; alapból kikapcsolt).
- Ötletgazda / ellenőrizte élesben: a felhasználó saját tesztje a `wunderground.com/weather/hu/…`
  oldalon (2026-10-31).

### Megjegyzés
Ez **nem** a WU weboldal belső JavaScript-API-jának vagy sütijének felhasználása – a nyilvános,
bejelentkezés nélküli oldal nyers, szerver által renderelt HTML-tartalmát olvassa, pontosan azt,
amit egy látogató a böngészőjében „Oldal forráskódja" nézetben lát. A `/dashboard/pws/{id}` oldal
(amely JavaScript-futtatást igényelne a saját állomás adatához) továbbra sem használt.

## [1.6.0] – 2026-10-31

Óránkénti előrejelzés, külön előrejelzés-koordinátor és stabilitás. **Visszafelé kompatibilis**
(új entitások új kulccsal; a meglévők azonosítói változatlanok).

### Hozzáadva
- **Óránkénti előrejelzés (M2)** – a `weather` entitás `hourly` előrejelzést is ad (72 óra, nappal/éjszaka
  tudatos állapottal): Open-Meteo (elsődleges) → MET Norway. A WU PWS API-nak nincs óránkénti előrejelzése;
  „csak Weather Underground” módban az óránkénti adat az Open-Meteóból/MET Norway-ből érkezik.
  Ötletgazda: **ztarsoly** ([#1](https://github.com/aiasz/ha-wunderground-pws/issues/1)).
- **Blend (konszenzus) előrejelzés (F02)** – új `blend` forrás: az összes forrás egyesítve (hőmérséklet
  medián, csapadék/szél átlag, állapot többségi szavazás); a `sources` mező mutatja a résztvevőket.
- **Előrejelzés-pontozás a saját állomással (F21)** – blend módban minden forrás „holnapi” előrejelzését
  összeveti a mért napi max/min hőmérséklettel (gördülő 14 nap); a blend a pontosabb forrást nagyobb
  súllyal veszi figyelembe. Diagnosztikai szenzorok: `Forecast error: …` (alapból kikapcsolva).
- **Open-Meteo modellválasztás (F03)** – `best_match`, ECMWF IFS (9 km), DWD ICON-EU, ICON seamless.
- **Mai szélsőértékek (F11)** – mai max/min hőmérséklet és max széllökés (éjfélig; újraindítás után is megmarad).
- **Légnyomás-tendencia (F12)** – 3 órás változás (hPa) és `rising / steady / falling` állapot.
- **Diagnosztika (F19)** – letölthető, kiredaktált diagnosztika (API kulcs, város, koordináták nélkül);
  `wunderground_pws.refresh` szolgáltatás; szenzorok: előrejelzés frissítve, használt forrás,
  Weather Underground API hívások ma.
- **Tartós előrejelzés-gyorsítótár (F20)** – az utolsó jó előrejelzés újraindítás és API-kiesés után is látszik
  (`forecast_stale` jelzéssel).
- **Újrapróbálkozás és megszakító (S5, S6)** – átmeneti hibánál (időtúllépés, 5xx) egy újrapróbálkozás
  növekvő, szórt várakozással; 3 egymás utáni hiba után a forrást 10 percre kihagyja.

### Módosítva
- **Kaposvár (a készítő otthona) kiemelten támogatott:** a beállító űrlap az `IKAPOS27` állomást és a `Kaposvár` várost javasolja; a város geokódolása (46.3667, 17.8) valós adatokkal ellenőrizve, és minden forrás (WU, MET Norway, Open-Meteo) ezekkel a koordinátákkal kérdez.
- A **mai előrejelzés tartománya nem lehet szűkebb**, mint amit az állomás már mért (a MET Norway csak a nap hátralévő óráit adja).
- Az előrejelzés **saját koordinátorba** került (S1): lassú vagy hibás forrás sosem lassítja a méréseket,
  és a beállítás sem hiúsul meg miatta. A megfigyelés frissítése háttérfeladatként indítja.
- Az éjszakai „jelenlegi állapot” az aktuális óra előrejelzett állapotából jön (ha van óránkénti adat).
- Az előrejelzés-forrás választó új értéke: `blend`.

### Javítva
- Az opciók mentése új beállítással (Open-Meteo modell) nem indít felesleges újratöltést kulcscserénél.

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
