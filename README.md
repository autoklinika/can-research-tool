# CAN Research Tool (CRT)

CRT to niezależne narzędzie do **reverse engineeringu komunikacji CAN**. Nie jest kopią ECU Platform i nie zawiera procedur diagnostycznych konkretnych sterowników.

## Aktualny zakres

- wykrywanie interfejsów i kanałów Kvaser,
- odbiór surowych ramek CAN bez udostępniania metod `write` / `send`,
- dwa tryby elektryczne odbioru:
  - `BENCH` — kontroler potwierdza poprawne ramki bitem ACK; wymagany na stole, gdy obserwowane ECU jest jedynym nadajnikiem,
  - `LISTEN_ONLY` — sprzętowy `SILENT`, bez TX i bez ACK; do kompletnej sieci, w której inne aktywne węzły zapewniają ACK,
- zapis kompletnej sesji z metadanymi,
- import istniejących logów Kvaser CSV,
- neutralna analiza ramek: ID, częstotliwość, okresowość, DLC i zmienność bajtów,
- rekonstrukcja J1939 TP oraz ISO-TP,
- klasyfikacja UDS i zachowanie nierozpoznanych wiadomości jako `UNKNOWN`,
- opcjonalne reguły dla protokołów autorskich,
- strumieniowy zapis sesji i ograniczony bufor podglądu GUI.

Znane logi z SAC służą wyłącznie jako materiał testowy do sprawdzania kompatybilności importu, transportu i zapisu Kvaser.

## Struktura

- `app/` — modele, rejestrator, strumieniowy zapis, transport i neutralny silnik analizy,
- `kvaser/` — izolowana integracja z Kvaser CANlib oraz import logów,
- `gui/` — Qt Widgets; wyłącznie prezentacja i sterowanie usługami rdzenia,
- `sessions/` — lokalne sesje badawcze, pomijane przez Git,
- `docs/` — architektura i decyzje projektowe,
- `tests/` — testy parserów, transportu, zapisu i ograniczonego bufora live.

## Instalacja środowiska developerskiego

```powershell
python -m pip install -e ".[dev,kvaser,gui]"
```

## GUI

Uruchomienie:

```powershell
python .\crt_gui.py
```

albo po ponownej instalacji projektu:

```powershell
crt-gui
```

GUI używa dwóch niezależnych torów danych:

```text
Kvaser
  ├─ pełny strumień → *.crt.jsonl + indeks + CSV
  └─ ostatnie 20 000 ramek → bufor live → QAbstractTableModel → QTableView
```

Właściwości pierwszej wersji GUI:

- odbiór CAN, zapis i składanie transportu działają poza wątkiem interfejsu,
- tabela jest odświeżana paczkami co 100 ms, nie osobnym sygnałem dla każdej ramki,
- tabela przechowuje maksymalnie 20 000 najnowszych ramek,
- `Pauza widoku` nie zatrzymuje odbioru ani zapisu,
- duże zapisane sesje są indeksowane i otwierane w wątku roboczym,
- przy otwieraniu sesji ładowany jest tylko ostatni widoczny fragment, a nie cały plik.

## Rejestracja sesji z terminala

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

Klasyczny rejestrator CLI tworzy:

- `*.crt.jsonl` — pełną sesję CRT,
- `*.crt.jsonl.idx.json` — rzadki indeks do stronicowania dużej sesji,
- `*.frames.csv` — surowe ramki,
- `*.summary.csv` — statystykę według CAN ID,
- `*.messages.csv` — zrekonstruowane wiadomości logiczne,
- `*.messages.summary.csv` — statystykę wiadomości logicznych.

## Analiza zapisanej sesji

```powershell
python .\analyze_session.py .\sessions\pierwszy_test.crt.jsonl
```

## Uruchomienie testów

```powershell
python -m pytest -q
```

Sterownik Kvaser i pakiet `canlib` są wymagane dopiero do nasłuchu online. PySide6 jest opcjonalną zależnością wymaganą przez GUI.
