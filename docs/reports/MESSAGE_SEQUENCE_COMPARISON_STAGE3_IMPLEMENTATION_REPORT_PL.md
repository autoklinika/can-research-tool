# Message Sequence Comparison Provider — Stage 3

## Status

Implementacja funkcjonalna została zapisana na osobnej gałęzi stackowanej na Stage 2.1. Pełna walidacja GitHub Actions pozostaje do potwierdzenia.

## Repozytorium i gałąź

- repozytorium: `autoklinika/can-research-tool`
- gałąź: `agent/message-sequence-comparison-stage3`
- baza: `agent/payload-difference-exact-variants-stage2-1`
- bazowy HEAD: `30e12ed9ea707536d3a24e81834d7be3ef37b6f5`

## Kontrakt providera

- ID: `crt.comparison.message_sequences`
- wersja: `1.0.0`
- algorytm: `1`
- typ: `ExtensionType.COMPARISON`
- wejście: `comparison_set`
- wyjście: `message_sequence_differences`
- artefakt: `message-sequence-differences.json`
- schemat: `crt.message_sequence_differences` v1

## Zaimplementowane funkcje

Provider czyta wszystkie sesje strumieniowo w ich niezmiennej kolejności źródłowej i analizuje:

- pary wiadomości,
- trójki wiadomości,
- pełny strumień `raw`,
- strumień `collapsed`, w którym kolejne powtórzenia jednego klucza są zwijane,
- samoprzejścia `A → A`,
- cykle `A → B → A`.

Dla sekwencji zapisywane są:

- liczba wystąpień,
- udział procentowy,
- pierwszy i ostatni source row,
- pierwszy i ostatni timestamp według kolejności źródłowej,
- minimalny, średni i maksymalny czas sekwencji.

Porównanie z bazą obejmuje:

- nowe sekwencje,
- brakujące sekwencje,
- zmianę liczby wystąpień,
- zmianę udziału,
- zmianę średniego czasu sekwencji,
- deterministyczny ranking zmian,
- pełną macierz obecności i statystyk wszystkich sekwencji.

## Dokładny magazyn RAM/SQLite

Unikalne sekwencje są agregowane w ograniczonym buforze RAM. Po osiągnięciu `memory_sequence_threshold` bufor jest łączony z run-scoped SQLite przez UPSERT.

Próg nie ogranicza analizy. Metadane artefaktu deklarują:

- `sequence_tracking_complete = true`,
- `untracked_sequence_count = 0`,
- `mode = bounded_memory_sqlite_exact`.

Dodatkowa warstwa `message_sequence_exact.py` zachowuje semantykę source order także dla logów z niemonotonicznym timestampem:

- pierwszy timestamp pochodzi z pierwszego wystąpienia w pliku,
- ostatni timestamp pochodzi z ostatniego wystąpienia w pliku,
- wartości czasu nie są zastępowane przez `MIN/MAX`.

## GUI

Dodano renderer artefaktu Stage 3 w oknie analiz porównawczych.

Widok sesji pokazuje między innymi:

- liczbę ramek,
- liczbę unikalnych par i trójek raw,
- liczbę unikalnych par i trójek po zwinięciu,
- nowe i brakujące sekwencje,
- liczbę cykli.

Tabela zmian pokazuje:

- sesję,
- tryb,
- długość,
- tekst sekwencji,
- typ zmiany,
- liczby i udziały bazowe/bieżące,
- średni czas bazowy/bieżący.

Cykle i samoprzejścia są jawnie oznaczone.

## Testy

Dodano:

- `tests/test_message_sequence_provider.py`,
- `tests_gui/message_sequence_comparison_smoke.py`.

Test jednostkowy obejmuje:

- identyczny JSON i SHA-256 dwóch uruchomień,
- wymuszone wielokrotne opróżnianie bufora przy progu `1`,
- dokładne pary i trójki raw/collapsed,
- nowe i brakujące sekwencje,
- samoprzejście,
- cykl,
- source row i metryki czasu,
- pełny ślad źródeł i niezmienność SHA-256 sesji,
- brak automatycznych findings,
- walidację parametrów,
- odrzucenie nieobsługiwanej synchronizacji,
- usunięcie tymczasowego katalogu SQLite po anulowaniu.

Zaktualizowano również:

- test rejestru providerów,
- smoke statystyk porównawczych,
- smoke payload differences,
- workflow `GUI Regressions`.

## Granice

Provider działa tylko dla `synchronization_mode = none`. Porównuje rozkłady sekwencji w poszczególnych sesjach, ale nie próbuje wyrównywać ich osi czasu.

Nie dodano:

- J1939/UDS/ISO-TP sequence semantics,
- marker alignment,
- request/response pairing,
- automatycznych findings,
- werdyktu naprawy ECU.

## Nienaruszone kontrakty

Bez zmian pozostają:

- `CaptureService`,
- Kvaser i lifecycle CANlib,
- CAN TX/RX,
- format sesji,
- zapis surowych ramek,
- indeksy wyszukiwania,
- `.crt/project.sqlite`,
- Project Properties i Project Catalog.

## Znane ograniczenie

Zliczanie jest ograniczone pamięciowo, lecz pełna macierz i końcowy JSON są materializowane przed zapisem. Przy ekstremalnej liczbie unikalnych sekwencji sam artefakt może być duży. Strumieniowy writer albo artefakt SQLite wymaga osobnego kontraktu i nie należy do Stage 3.
