# Wunderground PWS – Home Assistant integráció

**Készítő: Aiasz · Verzió: 1.7.1 · [English README](README.en.md)**

Bármelyik [Weather Underground](https://www.wunderground.com/) személyes időjárás-állomás (PWS) adatait
megjeleníti a Home Assistantban – az **official WU API**-n keresztül, metrikus egységekkel – és mellé
**több szolgáltatóból** (Weather Underground, MET Norway, Open-Meteo) ad előrejelzést automatikus
tartalék-lánccal. Magyar és angol nyelven használható.

> A fejlesztés iránya és ütemterve: lásd a [CHANGELOG](CHANGELOG.md)-ot. Köszönet az ötletgazdáknak: [CREDITS](CREDITS.md).

---

## Funkciók

- **Saját állomás mérései**: hőmérséklet, érzett hőmérséklet, harmatpont, hőérzet/szélhűtési index, páratartalom,
  légnyomás, szél (sebesség, lökés, irány fokban és égtájban), csapadék (napi, intenzitás), napsugárzás, UV,
  számított értékek (felhőalap, abszolút páratartalom, nedves hőmérséklet).
- **Weather entitás** napi (7 nap) **és óránkénti (72 óra)** előrejelzéssel.
- **Többforrású előrejelzés fallback-kel**: Weather Underground → MET Norway → Open-Meteo (vagy egy kiválasztott forrás).
- **Blend (konszenzus) mód**: az összes forrás együtt; a rendszer a *saját állomásod méréseivel* pontozza a forrásokat, és a pontosabbat nagyobb súllyal veszi.
- **Open-Meteo modellválasztás**: automatikus, ECMWF IFS, DWD ICON-EU.
- **Mai max/min** hőmérséklet és széllökés, **légnyomás-tendencia** (emelkedő/állandó/csökkenő).
- **Diagnosztika**: letölthető (kiredaktált) diagnosztika, `wunderground_pws.refresh` szolgáltatás.
- **Magyar és angol felület** – a Home Assistant nyelvét követi (entitásnevek, beállítások, szélirány).
- **Állomás-állapot**: `Station online` és `Observation age` diagnosztikai entitás; kiugró mérések szűrése.
- **Pontosabb állapotjelzés**: éjszaka `clear-night`, hó/ónos eső, köd, erős szél, derültség a napsugárzásból.
- **Stabil működés**: a hibás előrejelzés nem érinti a mérések frissítését; az utolsó jó előrejelzés megmarad;
  az előrejelzés és a város-geokódolás gyorsítótárazott (kevesebb API-hívás).
- **Demo mód** (opcionális API kulcs): lásd lent.
- **Megfigyelés-tartalék kulcs nélkül**: ha a WU API nem elérhető és be van állítva egy előrejelzési
  város, az integráció a WU nyilvános, bejelentkezés nélküli városi oldaláról olvassa ki a legközelebbi
  állomás mérését – átlátszóan jelölve (`observation_source`, `fallback_source_station`).
- **UV-szint (WHO kategória) és UV-védelem riasztás**: az UV-indexből számolt kategória
  (alacsony…extrém) és egy bináris szenzor, amely jelzi, ha védelem ajánlott – alapból bekapcsolva.
- **Levegőminőség és pollen (opcionális)**: európai és amerikai AQI, 6 szennyezőanyag, 6 pollenfaj
  (köztük a parlagfű) az Open-Meteóból, kulcs nélkül – lásd lent.
- **Napfénytartam (ma) szenzor**, és a hiányzó mérések (széllökés, csapadék-intenzitás,
  napsugárzás, UV) automatikus pótlása egy mindig aktív, kulcs nélküli Open-Meteo
  kiegészítő lekérésből, amikor a saját mérés nem adja meg – átlátszóan jelölve
  (`estimated` attribútum) – lásd lent.
- **Beállítások újraindítás nélkül** módosíthatók (Configure).

## Telepítés

**HACS (ajánlott):** HACS → Integrations → `⋮` → *Custom repositories* → `https://github.com/aiasz/ha-wunderground-pws`
(kategória: *Integration*) → telepítés → Home Assistant újraindítása.

**Manuálisan:** másold a `custom_components/wunderground_pws` mappát a `config/custom_components/` alá, indítsd újra a HA-t.

Minimum Home Assistant verzió: **2024.12.0**.

## Beállítás

*Settings → Devices & services → Add integration → „Wunderground PWS”*

| Mező | Leírás |
|---|---|
| Állomás azonosító | pl. `IKAPOS27` (az azonosító később nem módosítható – másik állomáshoz vegyél fel új bejegyzést) |
| API kulcs | saját kulcs a [WU fiókodból](https://www.wunderground.com/member/api-keys); **üresen hagyva demo mód** |
| Frissítési időköz | 1–60 perc (ajánlott: 5) |
| Előrejelzési város | opcionális (pl. `Kaposvár`); üresen az állomás koordinátái |
| Előrejelzés forrása | `auto` / `blend` / csak WU / csak MET Norway / csak Open-Meteo |
| Open-Meteo modell | (opciókban) automatikus / ECMWF IFS / DWD ICON-EU / ICON seamless |

Az API kulcs és a többi beállítás később: *Configure*. Az üresen hagyott kulcs automatikus keresést indít.

### Demo mód (API kulcs nélkül)
Üres kulcs esetén az integráció megpróbál egy, a WU weboldalába ágyazott nyilvános kulcsot kinyerni; a talált kulcsot
egy valódi hívással **ellenőrzi**, mielőtt elmenti. Sikertelen keresés után 15 perc várakozás van (legfeljebb 3 próba),
utána a Home Assistant újrahitelesítést kér. A kézzel megadott kulcsot az integráció soha nem cseréli le.

> **Fontos:** a megosztott kulcsot a WU bármikor elutasíthatja (a 2026-10-31-i ellenőrzéskor a weboldalról kinyert kulcsot
> már a megfigyelés végpont sem fogadta el). **Megbízható, tartós működéshez saját API kulcs kell** – a WU PWS-tulajdonosoknak
> ingyen adja: <https://www.wunderground.com/member/api-keys>. Kulcs nélkül az előrejelzést a MET Norway / Open-Meteo is tudja
> adni (forrás: `metno` vagy `openmeteo`); ha emellett egy előrejelzési **város** is be van állítva, a megfigyelés is
> működik kulcs nélkül – a WU nyilvános városi oldaláról, a WU által kiválasztott legközelebbi állomás adatával
> (lásd lent: „Megfigyelés-tartalék").

### Megfigyelés-tartalék kulcs nélkül (API kulcs és demo mód nélkül is)
Ha a WU API átmenetileg vagy tartósan nem elérhető (nincs kulcs, a demo mód kulcsa elutasítva), **és** be van
állítva egy **előrejelzési város**, az integráció a `wunderground.com/weather/hu/{város}` nyilvános,
bejelentkezés nélküli oldaláról olvassa ki az aktuális hőmérsékletet, páratartalmat, légnyomást, szelet,
harmatpontot és csapadékot – ez egy valódi, a szerver által renderelt oldal (nem a `/dashboard/pws/{állomás}`
oldal, amely csak JavaScript-tel töltődik fel, és amelyet ezért az integráció nem tud használni).

**Fontos korlátok, amiket érdemes tudni:**
- Ez a WU saját választása szerinti **legközelebbi** állomás az adott városhoz – **nem feltétlenül** a
  beállított saját állomásod. Kaposvárnál ez jelenleg például `IKAPOS10`, nem `IKAPOS27`. A ténylegesen
  használt forrás mindig látszik az `observation_source` (`wunderground_api` / `wu_citypage`) és a
  `fallback_source_station` attribútumban/szenzorban – soha nem keveredik össze a sajáttal.
- Nem hivatalos, nem dokumentált oldalszerkezetre épül; ha a WU átalakítja az oldalt, ez a forrás
  átmenetileg leállhat (az integráció ekkor a szokásos hibakezeléssel jelez, nem omlik össze).
- **Amit pótolunk valódi adatból:** koordináták (a város geokódolásából), szélirány fokban
  (iránytű-szektor középértéke, ±11,25° becslés), hőérzet index (szabványos képlet). A
  széllökés, csapadék-intenzitás, napsugárzás és UV-index pótlását lásd lent (M3b) – ezek
  mostantól a forráskiválasztástól függetlenül is pótolhatók, nem csak itt.

### Levegőminőség, pollen és UV (opcionális, `M3`)

A `#1` hibajegyben kért funkció: légszennyezettség, pollen és UV-kockázat egy ingyenes,
kulcs nélküli forrásból (Open-Meteo Air Quality API, CAMS Europe/Global modellek, CC BY 4.0).

**Alapértelmezetten kikapcsolva** (plusz API-hívás frissítésenként) – bekapcsolás a bejegyzés
**Configure** menüjében (*„Levegőminőség- és pollenszenzorok"*). Bekapcsolás után a 14 új
szenzor megjelenik az entitáslistában, de – az előrejelzés-pontosság szenzorokhoz hasonlóan –
**egyenként is engedélyezni kell** őket (niche, diagnosztikai jellegű adatok, alapból kikapcsolva,
hogy ne terheljék feleslegesen a frissítést és az entitáslistát).

- **Légszennyezettség-index:** európai (EEA) és amerikai (US EPA) AQI, saját hivatalos
  sávbeosztással (`level` attribútum).
- **Szennyezőanyagok:** PM2.5, PM10, nitrogén-dioxid, kén-dioxid, ózon, szén-monoxid (µg/m³).
- **Pollen (6 faj):** éger, nyír, fűfélék, üröm, olajfa, **parlagfű** – ez utóbbi Magyarország
  legjelentősebb késő-nyári allergénje, a funkció fő motivációja. A terhelési kategóriákhoz
  (alacsony/közepes/magas/nagyon magas) a svájci meteorológiai szolgálat (MeteoSwiss)
  fajspecifikus, hivatalos küszöbértékeit használjuk. **Az olajfa pollenre tudatosan nincs
  kategória** (csak nyers érték): nem találtunk rá egyetlen, megbízhatóan hivatkozható európai
  skálát sem – egy hiányzó kategória jobb, mint egy kitalált.

### Napsugárzás-kiegészítő és hiányzó adatok pótlása (`M3b`, mindig aktív)

Egy új, **mindig aktív** (nem kapcsolható ki), kulcs nélküli Open-Meteo lekérés – független attól,
melyik `forecast_source` van beállítva – pótolja a hiányzó mérési mezőket, és egy új szenzort ad:

- **`sunshine_duration` (Napfénytartam, ma):** a mai nap eddigi/becsült teljes napfénytartama
  percben.
- **Pótlás, csak ha a saját mérés valóban hiányzik** (sosem írja felül a valódi értéket):
  **széllökés**, **csapadék-intenzitás**, **napsugárzás**, **UV-index**. Mindegyik szenzoron
  az `estimated` attribútum jelzi, ha az érték ebből a forrásból lett pótolva.
- Ez **megszünteti a korábbi UV-korlátot**: az UV-pótlás eddig csak akkor működött, ha az
  Open-Meteo volt a tényleges előrejelzés-forrás (a MET Norway-nek nincs UV-adata) – ez a
  lekérés attól függetlenül mindig fut.
- Ugyanazt az Open-Meteo forrást használja, mint az előrejelzés (nincs új forrásmegjelölés).

## Adatforrások

| Adat | Forrás | Kulcs |
|---|---|---|
| Aktuális mérés (PWS) | Weather Underground `v2/pws/observations/current` | igen |
| Aktuális mérés (tartalék, legközelebbi állomás) | WU nyilvános városi oldal (`weather/hu/…`), nem hivatalos | nem |
| Előrejelzés | WU `v3/wx/forecast/daily/5day` (tartalék: `7day`) | igen |
| Előrejelzés | MET Norway Locationforecast 2.0 (CC BY 4.0) | nem |
| Előrejelzés, geokódolás | Open-Meteo (CC BY 4.0) | nem |
| Levegőminőség, pollen (opcionális) | Open-Meteo Air Quality API, CAMS (CC BY 4.0) | nem |

Az **óránkénti** adat Open-Meteóból, vagy MET Norway-ből jön (a WU PWS API-nak nincs óránkénti előrejelzése). Az `auto` mód az első sikeres forrást használja; melyiket, azt a `forecast_source_used` attribútum mutatja.
A kötelező forrásmegjelölések: [CREDITS](CREDITS.md).

## Entitások

| Entitás (kulcs) | Egység | Megjegyzés |
|---|---|---|
| `temperature`, `dew_point`, `heat_index`, `wind_chill` | °C | |
| `feels_like` | °C | hidegben szélhűtés, melegben hőindex, egyébként a hőmérséklet |
| `wet_bulb` | °C | alapból kikapcsolt |
| `humidity` / `absolute_humidity` | % / g/m³ | |
| `pressure` | hPa | |
| `wind_speed`, `wind_gust` | km/h | |
| `wind_bearing` | ° | |
| `wind_compass` | enum | N…NNW / É…ÉÉNy – a nyelvnek megfelelően |
| `wind_compass_hu` | szöveg | régi, magyar égtáj (kompatibilitás) |
| `precipitation_rate` / `precipitation_today` | mm/h / mm | |
| `solar_radiation` / `uv_index` / `cloud_base` | W/m² / – / m | |
| `temperature_max_today`, `temperature_min_today`, `wind_gust_max_today` | °C, km/h | mai szélsőértékek (éjfélig) |
| `pressure_change_3h` / `pressure_tendency` | hPa / enum | 3 órás légnyomás-változás és tendencia |
| `observation_age` | perc | diagnosztika |
| `wu_api_calls_today`, `forecast_updated`, `forecast_source` | – | diagnosztika |
| `forecast_mae_*` | °C | előrejelzés-hiba forrásonként (blend módban; alapból kikapcsolt) |
| `uv_level` | enum | WHO UV-kategória (alacsony…extrém) |
| `sunshine_duration` | perc | napfénytartam, ma (M3b, mindig aktív) |
| `european_aqi`, `us_aqi` | – | AQI, `level` attribútummal (opcionális, alapból kikapcsolt) |
| `pm2_5`, `pm10`, `nitrogen_dioxide`, `sulphur_dioxide`, `ozone`, `carbon_monoxide` | µg/m³ | opcionális, alapból kikapcsolt |
| `pollen_alder`, `pollen_birch`, `pollen_grass`, `pollen_mugwort`, `pollen_olive`, `pollen_ragweed` | grains/m³ | opcionális, alapból kikapcsolt; `level` attribútum (az olajfa kivételével) |
| `station_online` | be/ki | diagnosztika: friss-e az utolsó mérés |
| `uv_protection_needed` | be/ki | UV-index ≥ 3 (WHO ajánlás) |
| `weather` | – | aktuális állapot + napi előrejelzés |

## Kaposvár és Magyarország
Az integráció alapértelmezései **Kaposvárra** vannak hangolva (fejlesztési/teszt referenciaként): a beállítás az `IKAPOS27` állomást és a
`Kaposvár` előrejelzési várost javasolja (a mezők átírhatók). A város geokódolása egyszer fut le és tartósan tárolódik;
valós adatokkal ellenőrizve Kaposvár a (46.3667, 17.8) koordinátára oldódik fel, és az Open-Meteo (automatikus, ECMWF IFS,
ICON-EU) valamint a MET Norway előrejelzés is hibátlanul feldolgozható rá. Más magyar városnál ugyanígy működik
(pl. `Budapest`, `Pécs`); hazai hivatalos adat (HungaroMet) a tervezett v1.8-ban jön.

## Időjárás kártya

```yaml
type: weather-forecast
entity: weather.wunderground_pws_ikapos27_weather
forecast_type: hourly   # vagy: daily
```
(Régebbi telepítéseknél az entitás azonosítója változatlan marad, pl. `weather.wunderground_pws_ikapos27`.)

## Frissítés régebbi verzióról
A bejegyzés automatikusan migrálódik (konfig-verzió 3); az entitások azonosítói nem változnak. Ha az opciókban
korábban módosítottad az állomásazonosítót, az a bejegyzés adatává válik, így az entitások megmaradnak.

## Fejlesztés
Lásd: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) (tesztek, új szolgáltató hozzáadása).
Hibát vagy ötletet a [GitHub Issues](https://github.com/aiasz/ha-wunderground-pws/issues)-ben jelezz.

## Licenc
MIT – Készítő: Aiasz ([LICENSE](LICENSE))
