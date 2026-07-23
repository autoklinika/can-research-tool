# Plan — Message Sequence Comparison Provider Stage 3

## Cel

Dodać trzeci deterministyczny provider porównawczy CRT, który porównuje kolejność sąsiadujących wiadomości CAN w wielu zapisanych sesjach bez modyfikowania sesji i bez wymagania synchronizacji między logami.

Stage 3 jest stackowany na `Payload Difference Exact Variants Stage 2.1`.

## Provider i artefakt

- provider: `crt.comparison.message_sequences`
- wersja providera: `1.0.0`
- wersja algorytmu: `1`
- artefakt: `message-sequence-differences.json`
- typ artefaktu: `message_sequence_differences`
- schemat: `crt.message_sequence_differences` v1

## Definicja klucza wiadomości

Element sekwencji jest identyfikowany przez:

- kanał,
- CAN ID,
- format STD/EXT,
- typ ramki: data, remote albo error.

Payload nie należy do klucza Stage 3. Jego zmiany pozostają domeną providera Stage 2.1.

## Analizowane sekwencje

Provider analizuje dokładnie:

- pary sąsiednich wiadomości `A → B`,
- trójki sąsiednich wiadomości `A → B → C`.

Dla każdej sesji tworzone są dwa niezależne widoki:

1. `raw` — pełna kolejność zakwalifikowanych ramek,
2. `collapsed` — kolejno powtarzające się identyczne klucze są zwijane do jednego zdarzenia.

Dzięki temu można rozróżnić:

- rzeczywiste przejścia między różnymi komunikatami,
- serie powtórzeń jednego CAN ID,
- cykle `A → B → A`,
- samoprzejścia `A → A`.

## Metryki

Dla każdej sekwencji zapisywane są:

- liczba wystąpień,
- udział wśród wszystkich okien tej samej długości i trybu,
- pierwszy i ostatni wiersz źródłowy,
- timestamp pierwszego i ostatniego wystąpienia według kolejności źródłowej,
- minimalny, średni i maksymalny czas od początku do końca sekwencji.

## Porównanie z sesją bazową

Provider wykrywa:

- `new_sequence`,
- `missing_sequence`,
- wzrost lub spadek liczby wystąpień,
- wzrost lub spadek udziału,
- wzrost lub spadek średniego czasu wykonania sekwencji.

Ranking jest deterministyczny i ogranicza wyłącznie liczbę pozycji prezentowanych jako najważniejsze. Pełna macierz sekwencji pozostaje kompletna.

## Zarządzanie pamięcią

Zliczanie używa magazynu:

```text
ograniczony bufor RAM → tymczasowe SQLite → deterministyczny JSON
```

Parametr `memory_sequence_threshold` jest progiem opróżnienia bufora, a nie limitem analizy. Żadna sekwencja nie jest pomijana.

Tymczasowa baza:

- jest tworzona poza projektem,
- nie korzysta z `.crt/project.sqlite`,
- istnieje tylko podczas jednego analysis run,
- jest usuwana po sukcesie, błędzie i anulowaniu.

## Parametry

- `occurrence_change_threshold_percent`, domyślnie `10.0`,
- `share_change_threshold_percentage_points`, domyślnie `0.5`,
- `mean_span_change_threshold_percent`, domyślnie `20.0`,
- `maximum_ranked_changes`, domyślnie `500`,
- `memory_sequence_threshold`, domyślnie `50000`,
- `include_non_data_frames`, domyślnie `false`.

## Granice Stage 3

Stage 3 nie obejmuje:

- synchronizacji sesji według znaczników,
- dopasowywania sekwencji z przesunięciem czasowym między logami,
- dekodowania J1939, ISO-TP ani UDS,
- korelacji request/response na poziomie protokołu,
- automatycznych findings,
- automatycznej oceny poprawności naprawy ECU,
- sekwencji dłuższych niż trzy elementy.

## Nienaruszalne kontrakty

Nie zmieniać:

- `CaptureService`,
- Kvasera i lifecycle CANlib,
- CAN TX/RX,
- formatu sesji,
- kolejności i kompletności pełnego zapisu surowych ramek,
- trwałych indeksów wyszukiwania,
- schematu `.crt/project.sqlite`,
- Project Properties i Project Catalog.
