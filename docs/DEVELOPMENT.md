# Fejlesztői útmutató

## Környezet

A Home Assistant core **Linuxot** igényel (Windowson a tesztek nem futnak), ezért a teszteket
Linux alatt, pl. Dockerben futtasd.

```bash
# egyszer: tesztkép építése
docker build -t wu-pws-test - <<'EOF'
FROM python:3.14
RUN pip install --no-cache-dir pytest-homeassistant-custom-component ruff
WORKDIR /work
EOF

# tesztek + lint a repó gyökeréből
docker run --rm -v "$PWD:/work" wu-pws-test sh -c \
  "ruff check custom_components tests && ruff format --check custom_components tests && pytest"
```

Linuxon/WSL-ben elég: `pip install -r requirements_test.txt && pytest`.

## Szerkezet

| Fájl | Szerep |
|---|---|
| `coordinator.py` | megfigyelés + előrejelzés frissítése, demo mód (kulcskeresés), adatellenőrzés |
| `providers/` | egy szolgáltató = egy adapter: `wunderground.py`, `open_meteo.py`, `metno.py`, `wu_citypage.py` (kulcs nélküli megfigyelés-fallback, F09), közös `_http.py`, `breaker.py`, `base.py` (hibatípusok) |
| `calculations.py`, `conditions.py` | **tiszta** függvények (átváltás, származtatott értékek, állapot-leképezések) – Home Assistant nélkül tesztelhetők |
| `models.py` | a providerek közös, normalizált adatalakja |
| `settings.py` | tényleges beállítás = opció › adat (B06) |
| `config_flow.py` | beállítás, opciók, újrahitelesítés |
| `sensor.py`, `binary_sensor.py`, `weather.py`, `entity.py` | megjelenítés (csak olvasnak a koordinátorból) |

## Új szolgáltató hozzáadása

1. `providers/<név>.py`: `INFO = ProviderInfo(...)`, `fetch_*` függvények; hiba esetén `ProviderError`-t dobj
   (ne `[]`-t), az eredmény a `models.py` alakjára normalizálva.
2. Állapotkódok → `conditions.py` (paraméteres teszttel).
3. Rögzíts valós, anonimizált mintaválaszt a `tests/fixtures/` alá, és írj parser-tesztet.
4. Jegyezd fel a `CREDITS.md`-ben a kötelező forrásmegjelölést és a használati feltételeket –
   **ToS-ellenőrzés nélkül nem kerül be provider.**

## Szabályok

- Entitás `key` és `unique_id` **nem változhat** (visszafelé kompatibilitás); új entitás új kulccsal.
- Minden hibajavításhoz előbb regressziós teszt (`B##` a CHANGELOG-ban).
- A verzió egyetlen forrása a `manifest.json`; a `v<verzió>` tag-nek egyeznie kell vele (CI ellenőrzi).
- Docstringek/kommentek angolul; felhasználói szöveg a `strings.json` → `translations/*.json`-ban.
- `SERVER.md` és `PLAN.md` belső fájlok, **nem publikálhatók** (`.gitignore`).
