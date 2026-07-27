# Comparison Visualization Stage 2C1 — inter-frame timing i jitter

## Cel

Dodać do produkcyjnego przepływu porównywania logów pasywną analizę czasową
jednego dokładnego klucza wiadomości CAN. Analiza ma mierzyć regularność transmisji,
wykrywać długie przerwy, porównywać sesje oraz zachowywać dokładne odwołania do
ramek źródłowych bez zmiany formatu sesji, indeksów ani schematu projektu.

## Zakres dostarczony

- nowa karta `Timing i jitter` w oknie `Porównanie logów`,
- analiza dokładnego klucza w formacie
  `kanał:STD/EXT:CAN_ID:data/remote/error`,
- osobne statystyki dla każdej sesji zestawu porównawczego,
- porównanie każdej sesji z sesją bazową,
- wykrywanie długich odstępów i zachowanie ramek tworzących każdy dowód,
- trwały, wersjonowany artefakt wyników,
- automatyczne odtworzenie ostatniego zgodnego wyniku bez ponownego skanowania
  sesji,
- praca w tle i możliwość anulowania,
- brak transmisji CAN.

## Model obliczeniowy

Analiza wykonuje dwa sekwencyjne, pasywne przebiegi po każdej sesji.

### Pierwszy przebieg

Dla kolejnych wystąpień wybranego klucza obliczane są dokładnie:

- liczba wystąpień,
- liczba dodatnich odstępów,
- liczba odstępów niemonotonicznych,
- minimum i maksimum,
- średnia,
- odchylenie standardowe metodą online,
- pierwszy i ostatni `source_row`.

Pełna lista odstępów nie jest materializowana. Do wyznaczania percentyli używana
jest deterministyczna próbka rezerwuarowa ograniczona domyślnie do 100 000
odstępów na sesję. Ograniczenie dotyczy wyłącznie percentyli; liczności, średnia,
minimum, maksimum i odchylenie standardowe są liczone ze wszystkich prawidłowych
odstępów.

### Drugi przebieg

Na podstawie mediany z pierwszego przebiegu wykonywane są:

- dokładne zliczenie wszystkich przerw przekraczających próg,
- obliczenie RMS odchylenia od mediany,
- wybranie maksymalnie 100 najdłuższych dowodów na sesję,
- zachowanie obu dokładnych wierszy źródłowych tworzących odstęp.

## Metryki

Dla każdej sesji dostępne są:

- p05, p25, mediana, p75, p95 i p99 odstępu,
- jitter `p95 - p05`,
- RMS odchylenia odstępu od mediany,
- współczynnik zmienności `odchylenie standardowe / średnia`,
- nominalna częstotliwość `1 / mediana odstępu`,
- liczba przerw,
- liczba odstępów niemonotonicznych.

Próg przerwy jest konfigurowalny jako:

`odstęp >= mediana × współczynnik`

Domyślny współczynnik wynosi `3,0`.

## Porównanie z sesją bazową

Dla każdej sesji niebazowej obliczane są:

- procentowa zmiana średniego odstępu,
- procentowa zmiana mediany,
- procentowa zmiana jitteru `p95-p05`,
- procentowa zmiana nominalnej częstotliwości,
- zmiana współczynnika zmienności w punktach procentowych,
- różnica liczby wykrytych przerw.

Wartość procentowa nie jest wyznaczana, gdy wartość bazowa jest zerowa albo brak
wystarczających danych.

## Dowody i nawigacja

Każdy zachowany dowód przerwy zawiera:

- identyfikator i nazwę sesji,
- dokładny klucz wiadomości,
- `previous_source_row`,
- `current_source_row`,
- oba timestampy,
- długość odstępu,
- próg przerwy,
- stosunek odstępu do mediany.

GUI pozwala osobno otworzyć początek i koniec odstępu. Nawigacja korzysta z
istniejącego bounded navigatora zapisanych sesji i przekazuje dokładny
`source_row`; nie wyszukuje ponownie wiadomości po jej treści.

## Trwały artefakt

- typ: `comparison_interframe_timing`,
- schemat: `crt.comparison_interframe_timing`,
- wersja schematu: 1,
- provider: `crt.comparison.interframe_timing`,
- algorytm: wersja 1.

Artefakt przechowuje:

- konfigurację analizy,
- fingerprinty i kolejność sesji,
- statystyki sesji,
- różnice względem bazy,
- bounded dowody przerw,
- ostrzeżenia.

Zgodność jest sprawdzana przez identyfikatory i kolejność sesji, `frame_count`
oraz SHA-256. Uszkodzony albo nieaktualny artefakt jest pomijany. Zapis używa
istniejącego `ArtifactWriter` oraz `source_kind="session"`; nie dodano tabeli ani
migracji `.crt/project.sqlite`.

## GUI

Karta `Timing i jitter` zawiera:

- pole dokładnego klucza wiadomości,
- ustawienie mnożnika progu przerwy,
- `Analizuj timing`, `Wczytaj ostatni` i `Anuluj`,
- wykres p05–p95 z zakresem p25–p75 i medianą,
- tabelę statystyk sesji,
- tabelę zmian względem sesji bazowej,
- tabelę najdłuższych przerw,
- przejście do początku lub końca wybranego odstępu.

## Testy automatyczne

Dodano:

- `tests/test_comparison_interframe_timing.py`,
- `tests_gui/comparison_interframe_timing_smoke.py`,
- workflow `Comparison Inter-Frame Timing Stage 2C1 Validation` dla Ubuntu i
  Windows GitHub-hosted.

Testy obejmują:

- średnią, medianę, częstotliwość i jitter,
- wykrycie dokładnej przerwy,
- zachowanie obu `source_row`,
- różnice względem sesji bazowej,
- round-trip artefaktu,
- odrzucenie zmienionego fingerprintu,
- obecność karty w produkcyjnym dialogu,
- zapis i ponowne otwarcie bez skanowania,
- przekazanie dokładnego wiersza dowodu do istniejącej nawigacji.

## Walidacja funkcjonalnego checkpointu

Funkcjonalny checkpoint:

`497c5a352837ea4fe5ab42624e5b6bb408707256`

Dla tego commitu zakończyły się sukcesem:

- dedykowany Stage 2C1 na Ubuntu i Windows — compile, rdzeń, artefakt i GUI,
- pełny `pytest`,
- Windows GitHub-hosted CI,
- GUI Regressions,
- Comparison Dashboard Validation,
- Comparison Timeline Validation,
- Comparison Timeline Stage 2B Validation,
- Live Preview Capacity.

Ogólny job `Tests/gui-smoke` może kończyć się niezależnie dłużej niż dedykowane
smoki. Self-hosted Windows nie jest wymagany dla tego pasywnego etapu bez
sprzętu CAN.

## Potwierdzenie ręczne

Dnia 2026-07-27 właściciel projektu uruchomił Stage 2C1 na Windows i potwierdził
pełny przepływ produkcyjny:

`analiza klucza → statystyki i jitter → wykryte przerwy → nawigacja do obu ramek → zapis artefaktu → ponowne otwarcie bez skanowania`

Potwierdzono poprawne wyświetlenie metryk, działanie nawigacji do obu dokładnych
`source_row` tworzących odstęp oraz automatyczne odtworzenie trwałego artefaktu
bez ponownego skanowania źródłowych sesji.

## Zachowane kontrakty

Bez zmian pozostają:

- `CaptureService`,
- backend Kvaser i lifecycle CANlib,
- CAN TX/RX,
- format sesji i markerów,
- kolejność i kompletność pełnego zapisu surowych ramek,
- schemat trwałych indeksów,
- bounded/stronicowany model zapisanych sesji,
- schemat `.crt/project.sqlite`,
- artefakty i zachowanie wcześniejszych etapów porównań.

## Świadomie poza zakresem Stage 2C1

- automatyczne parowanie request/response,
- rozpoznawanie transakcji UDS,
- `0x78 ResponsePending`,
- request/response latency,
- czasy odpowiedzi UDS,
- korelacja wielu różnych kluczy wiadomości,
- agregacja wykresu zależna od zoomu.
