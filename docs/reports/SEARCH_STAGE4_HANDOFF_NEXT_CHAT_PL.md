# CAN Research Tool — handoff po Etapie 4 wyszukiwania

## Stan repozytorium

```text
Repozytorium: autoklinika/can-research-tool
Gałąź: agent/log-search-stage1
Commit funkcjonalny przed raportem: e6303bf8b7365037ea55c2e1e097f7bac0de23b0
```

Dokument architektury i końcowego stanu:

```text
docs/reports/SEARCH_STAGE4_PERSISTENT_INDEX_PL.md
```

## Co jest ukończone

### Wyszukiwarka

- wspólny `QueryEngine`,
- wirtualny model wszystkich wyników bez limitu 5000,
- brak globalnego indeksowania tabel przy starcie aplikacji,
- leniwy indeks pamięciowy dla widoków nietrwałych,
- trwały indeks surowych ramek per projekt:

```text
<projekt>/.crt/indexes/search-v1.sqlite
```

- bezpośrednie wyszukiwanie wiadomości logicznych w istniejącym:

```text
<nazwa-sesji>.logical.sqlite
```

- gotowe indeksy nie są przebudowywane po ponownym uruchomieniu CRT.

### Trwałość indeksu surowych ramek

- stabilny `source_id` oparty na `session_id`,
- fingerprint sesji,
- kontrola SHA-256,
- zmiana samego `mtime` nie unieważnia indeksu,
- transakcje co 1000 ramek,
- wznawianie od `indexed_rows`,
- stany `pending`, `building`, `ready`, `failed`,
- usuwanie danych indeksu razem z sesją.

### GUI i wydajność

- dolny pasek przygotowania projektu,
- pasek nie pojawia się dla gotowych źródeł SQLite,
- zapisane sesje są stronicowane po maksymalnie 20 000 ramek,
- pełny log nie jest ponownie ładowany do modelu przy otwieraniu zakładki,
- wyszukiwarka wiadomości logicznych nie tworzy drugiego indeksu RAM.

### SQLite cleanup

- jawny helper `app/sqlite_connection.py`,
- połączenia zamykają uchwyty plików po wyjściu z `with`,
- usunięty import-time monkey patch,
- usunięty `app/sqlite_lifecycle.py`,
- `app/__init__.py` nie ma efektów ubocznych,
- polityka fingerprintu znajduje się bezpośrednio w `ProjectSearchIndex`.

## Kluczowa diagnoza z testów ręcznych

Pierwotnie wyglądało, jakby trwały indeks surowych ramek był przebudowywany przy każdym starcie. Raport diagnostyczny wykazał jednak:

```text
status = ready
indexed_rows = frame_count
IS CURRENT = True
```

Rzeczywistym źródłem powtarzanej pracy była tabela wiadomości logicznych. Miała gotowy `.logical.sqlite`, lecz rejestr wyszukiwarki tworzył dodatkowy indeks RAM. Po podłączeniu wyszukiwania bezpośrednio do cache logicznego problem zniknął. Użytkownik potwierdził ręcznie poprawne działanie.

## Testy

Najważniejsze testy:

```text
tests/test_search_engine.py
tests/test_project_search_index.py
tests/test_sqlite_architecture.py
tests_gui/project_preparation_progress_smoke.py
tests_gui/persistent_search_index_smoke.py
tests_gui/logical_search_cache_smoke.py
tests_gui/log_search_smoke.py
```

Workflow GUI zawiera smoke trwałego indeksu, wyszukiwania logicznego i architektury SQLite.

Przed kolejnymi zmianami uruchomić:

```powershell
& .\.venv\Scripts\Activate.ps1
python -m compileall -q app gui tests tests_gui
python -m pytest tests/test_search_engine.py tests/test_project_search_index.py tests/test_sqlite_architecture.py -q
python .\tests_gui\persistent_search_index_smoke.py
python .\tests_gui\logical_search_cache_smoke.py
python .\tests_gui\log_search_smoke.py
```

## Zachowane ograniczenia

Nie zmieniać:

- `CaptureService`,
- Kvasera ani lifecycle CANlib,
- formatu sesji,
- pełnego zapisu surowych ramek,
- kolejności zapisu ramek,
- semantyki Global Filter i Live Filter,
- istniejącego cache wiadomości logicznych poza koniecznymi adapterami odczytowymi.

## Następny zalecany etap

### Nawigacja z wyniku wyszukiwania do stronicowanej sesji

Obecnie trwały indeks może zwrócić wiersz znajdujący się poza aktualnie załadowaną stroną 20 000 ramek. Należy dodać bezpieczną nawigację:

```text
SearchHit.source_row
→ obliczenie numeru strony i lokalnego wiersza
→ żądanie strony w StoredSessionController
→ oczekiwanie na zakończenie ładowania
→ zaznaczenie i przewinięcie do ramki
```

Wymagania:

- nie zwiększać modelu do pełnej liczby ramek,
- zachować poprawność po filtrach i przełączaniu zakładek,
- anulować nieaktualne żądanie po zamknięciu zakładki lub zmianie celu,
- dodać smoke dla wyniku na innej stronie,
- wynik wyszukiwania wiadomości logicznych nadal ma działać bez indeksu RAM.

## Krótki prompt do nowej rozmowy

```text
Kontynuujemy CAN Research Tool po zakończeniu Etapu 4 trwałych indeksów wyszukiwania.
Repozytorium: autoklinika/can-research-tool
Gałąź: agent/log-search-stage1
Przeczytaj docs/reports/SEARCH_STAGE4_HANDOFF_NEXT_CHAT_PL.md i sprawdź aktualny HEAD.
Najpierw wykonaj końcową walidację Etapu 4, a następnie zacznij implementować nawigację z wyniku wyszukiwania do ramki znajdującej się na innej stronie zapisanej sesji. Nie zwiększaj modelu do pełnej liczby ramek i nie zmieniaj CaptureService, Kvasera, CANlib, formatu sesji ani kolejności pełnego zapisu surowych ramek.
```
