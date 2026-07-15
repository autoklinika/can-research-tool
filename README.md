# CAN Research Tool (CRT)

CRT to niezależne narzędzie do **reverse engineeringu komunikacji CAN**. Nie jest kopią ECU Platform i nie zawiera procedur diagnostycznych konkretnych sterowników.

## Faza 1 — odbiór bez ramek aplikacyjnych TX

- wykrywanie interfejsów i kanałów Kvaser,
- odbiór surowych ramek CAN bez udostępniania metod `write` / `send`,
- dwa tryby elektryczne odbioru:
  - `BENCH` — kontroler potwierdza poprawne ramki bitem ACK; wymagany na stole, gdy obserwowane ECU jest jedynym nadajnikiem,
  - `LISTEN_ONLY` — sprzętowy `SILENT`, bez TX i bez ACK; do kompletnej sieci, w której inne aktywne węzły zapewniają ACK,
- wyłączenie lokalnego echa transmisji innych uchwytów CANlib,
- zapis kompletnej sesji z metadanymi,
- import istniejących logów Kvaser CSV,
- neutralna analiza ramek: ID, częstotliwość, okresowość, DLC i zmienność bajtów,
- filtrowanie, oznaczanie i porównywanie sesji,
- opcjonalne dekodery protokołów dodawane później jako osobne moduły.

Znane logi z SAC służą wyłącznie jako materiał testowy do sprawdzania kompatybilności importu i zapisu Kvaser.

## Struktura

- `app/` — modele sesji, rejestrator i neutralny silnik analizy,
- `kvaser/` — izolowana integracja z Kvaser CANlib oraz import logów,
- `sessions/` — lokalne sesje badawcze, pomijane przez Git,
- `docs/` — architektura i decyzje projektowe,
- `tests/` — testy parserów i analizy.

## Rejestracja sesji Kvaser

Domyślny zapis 10 sekund na kanale 0, 250 kbit/s, w trybie stanowiskowym `BENCH`:

```powershell
python .\capture_session.py
```

Sesja o własnej nazwie i czasie 30 sekund:

```powershell
python .\capture_session.py --duration 30 --name ecu_startup
```

Nasłuch bez limitu czasu, kończony przez `Ctrl+C`:

```powershell
python .\capture_session.py --duration 0 --name long_capture
```

Podgląd każdej ramki w terminalu:

```powershell
python .\capture_session.py --duration 10 --live
```

Tryb pełnego listen-only dla kompletnej sieci:

```powershell
python .\capture_session.py --mode listen-only
```

Po zakończeniu w katalogu `sessions/` powstają trzy pliki:

- `*.crt.jsonl` — pełna sesja CRT z metadanymi,
- `*.frames.csv` — surowe ramki w czytelnym formacie CSV,
- `*.summary.csv` — statystyka według CAN ID.

Po ponownej instalacji projektu dostępna jest również komenda:

```powershell
crt-capture --duration 10 --name bench_test
```

## Uruchomienie testów

```powershell
python -m pip install -e ".[dev,kvaser]"
python -m pytest -q
```

Sterownik Kvaser i pakiet `canlib` są zależnościami opcjonalnymi wymaganymi dopiero do nasłuchu online.
