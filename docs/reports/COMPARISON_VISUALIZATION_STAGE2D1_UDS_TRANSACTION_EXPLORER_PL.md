# Comparison Visualization Stage 2D1 — eksplorator transakcji UDS

## Cel

Dodać do produkcyjnego przepływu porównywania logów interaktywny eksplorator
transakcji UDS, który pracuje na trwałym artefakcie Stage 2C2 i nie wykonuje
kolejnego skanowania surowych sesji.

Stage 2D1 ma umożliwiać szybkie filtrowanie, korelację protokołową, grupowanie,
porównanie usług, analizę rozkładu latencji, eksport oraz przejście do dokładnych
ramek dowodowych.

## Architektura

Źródłem danych jest najnowszy zgodny artefakt:

- typ: `comparison_uds_latency`,
- schemat: `crt.comparison_uds_latency` v1,
- dostarczony przez Stage 2C2.

Karta `Transakcje UDS` używa
`ComparisonUdsLatencyService.load_latest_compatible()`. Odczyt artefaktu jest
wykonywany w `QThreadPool`, poza wątkiem GUI. Po wczytaniu wszystkie filtry,
grupowania, wykresy i eksporty działają na modelu artefaktu w pamięci.

Stage 2D1:

- nie otwiera `SessionPagedReader`,
- nie rekonstruuje ponownie ISO-TP,
- nie zmienia reguł parowania request/response,
- nie tworzy nowego analysis run ani artefaktu,
- nie zmienia schematu projektu.

## Nowa karta GUI

W produkcyjnym dialogu `Porównanie logów` dodano kartę:

`Transakcje UDS`

Karta zawiera:

- wczytanie najnowszego artefaktu Stage 2C2,
- filtry,
- wybór sposobu grupowania,
- wykres p50–p95 first/final latency,
- tabelę grup protokołowych,
- tabelę porównań względem sesji bazowej,
- tabelę przefiltrowanych transakcji,
- szczegóły payloadów i ramek dowodowych,
- eksport CSV,
- nawigację do request, first response i final response.

Po otwarciu karta automatycznie próbuje wczytać najnowszy zgodny artefakt.
Jeżeli Stage 2C2 nie został wcześniej uruchomiony, wyświetla jednoznaczny
komunikat bez traktowania braku artefaktu jako awarii aplikacji.

## Filtry

Dostępne są filtry:

- sesja,
- SID usługi,
- status transakcji,
- finalny NRC,
- tekst/payload,
- początek i koniec czasu względnego,
- minimalna i maksymalna final response latency.

Wyszukiwanie tekstowe obejmuje:

- nazwę sesji,
- SID i nazwę usługi,
- status,
- automatyczną etykietę korelacji,
- payload żądania,
- payload pierwszej odpowiedzi,
- payload odpowiedzi końcowej,
- kod i nazwę NRC.

Czas względny jest liczony osobno dla każdej sesji od pierwszej zachowanej
transakcji dowodowej tej sesji. Filtry czasowe i latencji są podawane w
milisekundach.

## Korelacja protokołowa

Stage 2D1 nie zmienia parowania transakcji wykonanego przez Stage 2C2. Dla
każdej zachowanej pary analizuje wyłącznie payload żądania i wyznacza klucz
korelacji.

### SID

Każda grupa zachowuje bazowy SID i nazwę usługi.

### DID

DID jest odczytywany z pierwszych dwóch bajtów danych żądania dla usług:

- `0x22 ReadDataByIdentifier`,
- `0x24 ReadScalingDataByIdentifier`,
- `0x2A ReadDataByPeriodicIdentifier`,
- `0x2E WriteDataByIdentifier`,
- `0x2F InputOutputControlByIdentifier`.

Przykład:

`22 F1 90` → `SID 0x22 / DID 0xF190`

### Subfunkcja

Dla usług z subfunkcją odczytywany jest drugi bajt z wyzerowanym bitem
suppress-positive-response.

Przykład:

`19 82 FF` → `SID 0x19 / subfunkcja 0x02`

### Routine ID

Dla `0x31 RoutineControl` odczytywane są:

- subfunkcja,
- dwubajtowy Routine ID.

Przykład:

`31 01 F0 22` → `SID 0x31 / Routine 0xF022 / subfunkcja 0x01`

## Tryby grupowania

Dostępne są:

- `Automatycznie` — najbardziej szczegółowy bezpieczny klucz: Routine ID,
  następnie DID, następnie subfunkcja, a na końcu SID,
- `SID usługi`,
- `DID`,
- `Subfunkcja`,
- `Routine ID`.

Tryby jawne zachowują SID również wtedy, gdy wartość korelacyjna nie występuje.
Dzięki temu transakcje różnych usług nie są łączone tylko dlatego, że posiadają
taki sam drugi lub trzeci bajt.

## Metryki grup

Dla każdej grupy i każdej sesji wyznaczane są:

- liczba zachowanych transakcji,
- odpowiedzi pozytywne,
- odpowiedzi negatywne,
- timeouty,
- transakcje zakończone końcem logu,
- brak odpowiedzi zgodny z suppress-positive-response,
- liczba transakcji zawierających `0x78`,
- łączna liczba `0x78`,
- skuteczność zakończenia,
- p50 i p95 first response latency,
- p50 i p95 final response latency.

Dla każdej sesji niebazowej dostępne jest porównanie z sesją bazową:

- różnica liczby transakcji,
- różnica skuteczności w punktach procentowych,
- procentowa zmiana p50 first latency,
- procentowa zmiana p50 final latency,
- procentowa zmiana p95 final latency,
- różnica timeoutów,
- różnica odpowiedzi negatywnych,
- różnica liczby `0x78`.

Grupy nieobecne w danej sesji otrzymują jawny wiersz zerowy. Pozwala to odróżnić
brak usługi od braku wiersza w GUI.

## Wykres latencji

Wykres pokazuje dla każdej sesji widocznej po filtrach:

- zakres p50–p95 first response latency,
- zakres p50–p95 final response latency,
- liczbę transakcji dowodowych użytych przez widok.

Wykres jest zależny od aktywnych filtrów. Umożliwia szybkie zauważenie sytuacji,
w której mediana pozostaje podobna, ale pogarsza się ogon p95.

## Szczegóły transakcji

Po zaznaczeniu wiersza panel szczegółów pokazuje:

- sesję i czas względny,
- SID i nazwę usługi,
- automatyczną etykietę korelacji,
- status,
- liczbę `0x78`,
- first i final response latency,
- finalny NRC wraz z nazwą,
- zakresy `source_row`, timestampy, klucze wiadomości i payloady request,
  first response i final response,
- bounded listę zachowanych odpowiedzi `0x78`.

## Nawigacja dowodowa

Dostępne są przyciski:

- `Otwórz żądanie`,
- `Otwórz pierwszą odpowiedź`,
- `Otwórz odpowiedź końcową`.

Nawigacja przekazuje istniejącemu navigatorowi:

- identyfikator sesji,
- dokładny pierwszy `source_row` komunikatu logicznego,
- dokładny klucz wiadomości CAN.

Podczas nawigacji blokowane są wszystkie interaktywne karty:

- oś czasu,
- timing i jitter,
- latencja UDS,
- transakcje UDS.

Po sukcesie albo błędzie wszystkie karty są ponownie aktywowane.

## Lifecycle selekcji

Pierwszy smoke GUI wykrył problem Qt: po zastosowaniu filtra tabela mogła
zachować selekcję wiersza `0`, podczas gdy model wybranego rekordu i panel
szczegółów zostały wyczyszczone. Ponowne zaznaczenie tego samego wiersza nie
emitowało wtedy `itemSelectionChanged`.

Widok produkcyjny jawnie czyści selekcję przed wymianą przefiltrowanego modelu i
przed wyzerowaniem wyniku. Zapewnia to zgodność:

- wiersza tabeli,
- rekordu domenowego,
- panelu szczegółów,
- aktywności przycisków nawigacji.

Przypadek jest pokryty pełnym smoke GUI.

## Semantyka bounded

Stage 2C2 zachowuje bounded listę transakcji dowodowych, przy jednoczesnym
utrzymaniu dokładnych globalnych liczników i percentyli sesji. Stage 2D1
świadomie pracuje na tej liście dowodowej.

Jeżeli `evidence_truncated` jest ustawione dla którejkolwiek sesji, karta
wyświetla ostrzeżenie, że:

- filtrowanie, grupowanie i eksport obejmują zachowane pary dowodowe,
- dokładne globalne liczniki pozostają w karcie `Latencja UDS`,
- liczności grup nie mogą być przedstawiane jako pełne statystyki całej sesji.

Stage 2D1 nie ukrywa tego ograniczenia i nie próbuje odtwarzać brakujących
transakcji przez ponowny skan logów.

## Eksport CSV

Dostępne są dwa eksporty:

- widoczne transakcje,
- aktualne grupy protokołowe.

Pliki są zapisywane jako:

- UTF-8 z BOM,
- separator `;`,
- wartości czasowe w milisekundach,
- identyfikatory SID, DID, subfunkcji, Routine ID i NRC w zapisie
  szesnastkowym.

Format jest przyjazny dla polskich ustawień arkusza kalkulacyjnego. Eksport
transakcji zachowuje także payloady, klucze wiadomości i dokładne `source_row`.

## Testy automatyczne

Dodano:

- `tests/test_comparison_uds_transaction_explorer.py`,
- `tests_gui/comparison_uds_transaction_explorer_smoke.py`,
- workflow `Comparison UDS Transaction Explorer Stage 2D1 Validation` na
  Ubuntu i Windows GitHub-hosted.

Testy rdzenia obejmują:

- ekstrakcję DID, subfunkcji i Routine ID,
- automatyczny klucz korelacji,
- filtry sesji, SID, statusu, NRC, tekstu, czasu i latencji,
- grupowanie i wiersze zerowe,
- porównanie z bazą,
- rozkłady first/final latency,
- ostrzeżenie bounded,
- szczegóły payloadów,
- eksport obu CSV.

Smoke GUI obejmuje:

- produkcyjny dialog i kartę,
- utworzenie artefaktu przez Stage 2C2,
- wczytanie Stage 2D1 bez skanowania sesji,
- grupowanie po DID,
- filtrowanie po payloadzie,
- panel szczegółów,
- nawigację do request, `0x78` i final response,
- spójny lifecycle blokowania kart,
- eksport CSV,
- ponowne otwarcie i automatyczne odtworzenie.

## Walidacja funkcjonalnego checkpointu

Funkcjonalny checkpoint:

`74dceb37ddc4b9d0dba355b69df35ca264de1e97`

Dla tego commitu zakończyły się sukcesem:

- Stage 2D1 Validation na Ubuntu i Windows — compile, rdzeń, CSV i GUI,
- pełny job `pytest`,
- Windows GitHub-hosted CI,
- GUI Regressions,
- Comparison Dashboard Validation,
- Comparison Timeline Validation,
- Comparison Timeline Stage 2B Validation,
- Comparison Inter-Frame Timing Stage 2C1 Validation,
- Comparison UDS Latency Stage 2C2 Validation,
- Live Preview Capacity.

Ogólny job `Tests/gui-smoke` wykonuje niezależny, długi test tworzenia workspace
i w chwili zapisu raportu pozostawał w trakcie. Dedykowane smoki produkcyjnych
przepływów Stage 2D1 i wcześniejszych etapów są zielone. Windows Self-Hosted CI
nie jest wymagany dla pasywnego etapu bez Kvasera i sprzętu CAN.

Copilot Code Review nie wykonał analizy z powodu wyczerpanego limitu konta. Nie
powstały wątki review. Wykonano własną kontrolę semantyki bounded, korelacji,
filtrów, eksportu, nawigacji i lifecycle GUI.

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
- artefakty i algorytmy Stage 1–2C2.

## Świadomie poza zakresem Stage 2D1

- nanoszenie transakcji UDS na trwałą oś czasu,
- przejście transakcja ↔ punkt osi czasu,
- trwała konfiguracja warstw korelacyjnych,
- aktywne wysyłanie UDS,
- automatyczne wykrywanie par request/response,
- functional addressing z wieloma ECU,
- niestandardowe adresowanie ISO-TP,
- DoIP.
