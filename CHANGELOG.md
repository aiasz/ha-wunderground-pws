# Changelog

Minden lényeges változás ebben a fájlban szerepel. A formátum a
[Keep a Changelog](https://keepachangelog.com/hu/1.1.0/) szerint készült, a verziózás
[SemVer](https://semver.org/lang/hu/). Szerző: **Aiasz**; az ötletgazdák a `CREDITS.md`-ben.

A `B##` / `F##` / `M#` / `S#` azonosítók a fejlesztési terv (`PLAN.md`) tételeire hivatkoznak.

## [1.7.0] – 2026-10-31

**Sürgős javítás**, élő Home Assistant tesztpéldányban megerősítve: a beállítás saját API kulcs
nélkül teljesen elakadt, és a kulcs nélküli tartalék forrásnál (1.6.1) több adat is hiányzott.

### Javítva (kritikus)
- **A beállítás nem fejeződött be API kulcs nélkül, még beállított tartalék-várossal sem**
  (`P0`): a beállítási folyamat minden esetben megkövetelte egy *valóban működő* WU API kulcs
  sikeres ellenőrzését, mielőtt elmentette a bejegyzést — függetlenül attól, hogy be volt-e
  állítva előrejelzési város a tartalékhoz (F09, 1.6.1). Mivel a demo módban kinyert kulcsot a
  WU ma elutasítja, a beállítás **sosem tudott sikerrel lezárulni** saját kulcs nélkül. Mostantól:
  ha az automatikusan talált/megadott kulcs ellenőrzése sikertelen, **de van beállított város**,
  a bejegyzés mégis létrejön — a koordinátor saját ütemezése szerint újra próbálja a kulcsot
  (S12), eközben a városi tartalékra támaszkodik (F09). Ha nincs kulcs és nincs város sem, a
  beállítás továbbra is hibát jelez — ekkor tényleg nincs honnan adatot szerezni.
  Élőben, valódi Home Assistant példányban megerősítve.
- **Üres állomásazonosítóval is el lehetett menteni a beállítást**, ami egy zsákutcás
  folyamatba vitte a felhasználót hibaüzenet nélkül. Mostantól az üres/csak szóközt tartalmazó
  azonosító egyértelmű hibát ad.

### Javítva (adathiány a kulcs nélküli tartalék forrásnál, 1.6.1 óta)
Élő teszt alapján a `wu_citypage` tartalék forrás több mezőt is kihagyott, amit a valódi WU API
megadna. Ahol **becsületesen pótolható volt valódi adatból**, pótoltuk:
- **Koordináták (lat/lon):** a már amúgy is geokódolt város helyéből.
- **Szélirány fokban:** a 22,5°-os iránytű-szektor középértékéből (jelölve: ±11,25° becslés).
- **Hőérzet index (heat_index):** új, szabványos NWS Rothfusz-képlet — ezentúl bármelyik
  forrásnál számolódik, ha a forrás maga nem adja meg (a WU API-nál is, tartalék funkcióként).
- **UV-index:** a már lekért előrejelzésből (ha az Open-Meteo a használt forrás — lásd lent).

**Amit tudatosan nem pótoltunk kitalált adattal** (a megfelelő szenzor „nem elérhető" marad):
széllökés, csapadék-intenzitás (pillanatnyi ráta), napsugárzás — ezekre a tartalék oldalon
nincs semmilyen valós alapadat. **Ismert korlát:** az UV-pótlás csak akkor működik, ha az
Open-Meteo a ténylegesen használt előrejelzés-forrás; ha a MET Norway válaszol előbb (ennek
API-ja nem ad UV-adatot), az UV-index is „nem elérhető" marad. Ez szándékos: egy hiányzó
érték jobb, mint egy kitalált szám.

### Hozzáadva (levegőminőség, pollen, UV — `M3`, opcionális)
A `#1` hibajegyben kért funkció: légszennyezettség, pollen és UV-kockázat, ingyenes,
kulcs nélküli forrásból (Open-Meteo Air Quality API, CAMS Europe/Global modellek, CC BY 4.0).
**Alapértelmezetten kikapcsolva** (plusz API-hívás/frissítés) — bekapcsolás a bejegyzés
**beállításaiban** (`Levegőminőség- és pollenszenzorok`); minden egyes szenzor emellett
egyenként is engedélyezendő az entitás-listában (ugyanaz a minta, mint az előrejelzés
pontosság-szenzoroknál) — ezek niche, diagnosztikai jellegű adatok.
- **Légszennyezettség-index:** európai (EEA) és amerikai (US EPA) AQI, mindkettő a saját
  hivatalos sávbeosztásával (`level` attribútum: jó/közepes/rossz stb.).
- **Szennyezőanyagok:** PM2.5, PM10, nitrogén-dioxid, kén-dioxid, ózon, szén-monoxid (µg/m³).
- **Pollen (6 faj):** éger, nyír, fűfélék, üröm, olajfa, **parlagfű** — Magyarország
  legjelentősebb késő-nyári allergénje, ez a funkció fő motivációja. A terhelési
  kategóriákhoz (alacsony/közepes/magas/nagyon magas) a svájci meteorológiai szolgálat
  (MeteoSwiss) fajspecifikus, hivatalos küszöbértékeit használjuk — ez volt az egyetlen
  olyan egységes, forrásként megnevezhető táblázat, amit találtunk. **Az olajfa pollenre
  tudatosan nincs kategória** (csak nyers érték): nem találtunk egyetlen, megbízhatóan
  hivatkozható európai skálát rá (a spanyol/portugál regionális tanulmányok 4-10x-es
  eltéréssel adnak eltérő küszöböket) — egy hiányzó kategória jobb, mint egy kitalált.
- **UV-szint (WHO kategória):** a meglévő UV-index (`uv_index`) WHO "Global Solar UV Index"
  kategóriája (alacsony/közepes/magas/nagyon magas/extrém) — új szenzor, **alapértelmezetten
  bekapcsolva**, nem az opcionális levegőminőség-funkció része.
- **UV-védelem szükséges (bináris szenzor):** `on`, ha az UV-index eléri a WHO által
  ajánlott védelmi küszöböt (3) — **alapértelmezetten bekapcsolva**.
- 25 új teszt (253 összesen), ruff clean.

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
