# CAN Research Tool — raport końcowy Etapu 6

Data: 2026-07-20

## Stan

- repozytorium: `autoklinika/can-research-tool`
- gałąź: `agent/filter-engine-v2-static`
- PR: `#21 — Global Filter Engine v2 — complete static filter Stage 6A`
- baza: `main` na `6364e9429fb74a879ec9c633a91fa7eda7932b0e`
- aktualny head przed raportem: `13c6b048457dee82344a0fec11ba4667eade9da3`
- PR jest otwarty, draft i niescalony

Etap 6 jest zakończony implementacyjnie. Przed merge pozostaje ostatnia lokalna walidacja aktualnego headu i jawna decyzja użytkownika o scaleniu.

## Zrealizowany zakres

### 6A.1 — wzorce statyczne

Dodano `CanIdPattern` i `PayloadPattern` z obsługą:

- dokładnego CAN ID,
- wildcardów `?` i `*`,
- postaci `value/mask`,
- payload exact, prefix i contains,
- wildcardów bajtu `??` i `**`,
- masek bitowych,
- walidacji 29-bitowego CAN ID i limitu 64 bajtów.

### 6A.2 — silnik

Dodano:

- `StaticCanFrameRecord`,
- `StaticFilterContext`,
- `StaticFilterCompiler`,
- pola kanał, RTR, error frame i payload,
- wspólne grupy AND/OR/NOT dla warunków v1 i v2,
- zgodność z istniejącymi presetami `format_version=1`,
- neutralne `UNAVAILABLE` dla pól niedostępnych w danym kontekście.

### 6A.3 — GUI

Dodano pola i operatory statyczne, opisy składni, walidację, ręczny test presetu i łączenie presetów Include przez AND/OR.

Najważniejsze poprawki końcowe:

- usunięto autosave,
- edycja odbywa się na kopii roboczej,
- `Zastosuj zmiany` zapisuje całość po walidacji,
- `Odrzuć zmiany` przywraca zapisany stan,
- zamknięcie okna wymaga zastosowania, odrzucenia albo powrotu do edycji,
- skróty presetów są blokowane przy niezastosowanych zmianach,
- naprawiono uciekanie kursora na koniec pola `Wartość / wartości`,
- test presetu jest domyślnie zwinięty,
- wyniki testu są po polsku: `PASUJE`, `NIE PASUJE`, `NIEDOSTĘPNE`,
- po próbie reorganizacji wizualnej przywrócono wcześniejszy układ trzech kolumn.

### 6A.4 — Live i zapisane sesje

Dodano:

- adapter `static_frame_record()`,
- `StaticCombinedActiveFilterSet`,
- wspólne wykonanie filtrów dla Live i stored-session,
- jednorazowe parsowanie masek po zmianie konfiguracji,
- bezpośredni resolver pól na hot path,
- pełny skan bufora Live poza wątkiem GUI,
- przyrostowe filtrowanie nowych ramek,
- filtrowanie zapisanej sesji w executorze,
- deterministyczne stronicowanie,
- brak modyfikacji pliku źródłowego sesji.

## Zachowane kontrakty

1. `CaptureService`, Kvaser i lifecycle CANlib pozostają bez zmian.
2. Ramka jest zapisywana przed oceną filtra.
3. Format `*.crt.jsonl` i indeks sesji pozostają bez zmian.
4. Filtr nie modyfikuje payloadu ani dekodowania.
5. Stare presety pozostają odczytywalne.
6. GUI nie implementuje własnej semantyki masek.
7. Niezastosowana kopia robocza nie wpływa na Live, stored-session ani skróty.

## Walidacja

Na commicie `9d7aa2d` wykonano:

- `python -m compileall -q app kvaser gui` — sukces,
- `python -m pytest -q` — `177 passed in 3.79s`,
- cztery smoke testy GUI — sukces.

Później wprowadzono poprawki GUI opisane wyżej. Użytkownik potwierdził ręcznie ich działanie. Aktualny head wymaga jeszcze pełnego lokalnego przebiegu przed merge.

GitHub Actions kończy obecnie joby przed pierwszym krokiem. Prawdopodobną przyczyną jest wykorzystany miesięczny limit GitHub-hosted Actions. Ustalono, że testy będą wykonywane lokalnie; self-hosted runner nie jest teraz konfigurowany.

## Walidacja przed scaleniem

```powershell
cd C:\CAN\can-research-tool
git switch agent/filter-engine-v2-static
git pull --ff-only
python -m compileall -q app kvaser gui
python -m pytest -q

$env:QT_QPA_PLATFORM="offscreen"
python .\tests_gui\static_filter_editor_smoke.py
python .\tests_gui\filter_manager_window_smoke.py
python .\tests_gui\static_filter_live_stored_smoke.py
python .\tests_gui\live_filter_worker_smoke.py
python .\tests_gui\live_buffer_performance_smoke.py
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
```

Następnie należy krótko sprawdzić ręcznie: brak autosave, `Odrzuć zmiany`, kursor w polu wartości, polskie wyniki testu, Live Capture i jedną zapisaną sesję.

## Następny krok

1. wykonać ostatnią walidację,
2. oznaczyć PR #21 jako gotowy do review,
3. scalić dopiero po jawnej decyzji użytkownika,
4. zaktualizować lokalny `main`.

Potencjalny kolejny zakres to 6B: częstotliwość, okres, jitter, zmiana wartości, missing-frame timeout i wykrywanie liczników. Nie rozpoczynać 6B przed formalnym zamknięciem PR #21.
