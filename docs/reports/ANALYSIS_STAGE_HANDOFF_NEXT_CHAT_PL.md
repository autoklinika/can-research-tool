# CAN Research Tool — zakończenie etapu analiz i handoff do następnej rozmowy

Data: 2026-07-22

## Status

Etap podstawowych analiz zapisanej sesji został zakończony i ręcznie potwierdzony jako działający.

Aktualna gałąź końcowa:

`agent/minimal-analysis-chrome-stage8`

Aktualny HEAD przed dodaniem tego raportu:

`7f2530349e726f0787321c663e227a52a6e16913`

Powiązany draft PR:

`#34 Hide idle analysis chrome and single-result selector`

PR pozostaje draftem i nie został scalony.

## Zakres wykonanych prac

### 1. Fundament domenowy

Dodano trwały model danych projektu CRT dla:

- profili ECU,
- referencji do ramek i zakresów ramek,
- zestawów porównawczych,
- uruchomień analiz,
- artefaktów,
- findings,
- migracji addytywnego schematu SQLite w `.crt/project.sqlite`.

Źródłowe pliki sesji pozostają niezmienne i są traktowane jako źródło prawdy.

### 2. Extension API

Dodano bezpieczny fundament rozszerzeń:

- jawny registry providerów,
- manifest rozszerzenia,
- read-only `ProjectContext`, `SessionSource` i `FrameQuery`,
- cancellation i progress,
- atomowy `ArtifactWriter`,
- `FindingWriter`,
- granicę wyjątków runnera,
- brak automatycznego ładowania kodu z katalogów projektu.

Nie dodano AI, CAN TX ani aktywnych funkcji sterujących magistralą.

### 3. Provider statystyk sesji

Dodano provider:

`crt.analysis.session_statistics`

Provider generuje deterministyczny artefakt:

`artifacts/<analysis_run_id>/session-statistics.json`

Artefakt zawiera między innymi:

- liczbę ramek i bajtów payloadu,
- liczbę unikalnych CAN ID i kluczy wiadomości,
- rozkład STD/EXT, DATA/RTR/ERROR, DLC i kanałów,
- zakres czasu i statystyki interwałów,
- statystyki per `(kanał, CAN ID, EXT, RTR, ERROR)`,
- średnią częstotliwość, jitter, minimalne i maksymalne okresy,
- SHA-256 sesji źródłowej i provenance.

Analiza nie tworzy findings, ponieważ dane są opisowe, a nie hipotezami.

### 4. Warstwa aplikacyjna analiz

Dodano serwis uruchamiania analiz zapisanych sesji:

- provider wybierany z Extension Registry,
- wykonanie poza wątkiem GUI,
- anulowanie,
- trwały katalog artefaktów,
- weryfikacja SHA-256 przed odczytem,
- obsługa ponownego otwarcia sesji,
- brak ponownego skanowania sesji przez GUI.

### 5. GUI analiz

Dodano zakładkę `Analizy` w zapisanej sesji.

Obecny finalny układ:

- użytkownik wybiera provider i uruchamia analizę,
- pasek postępu oraz status są widoczne tylko podczas pracy, błędu, anulowania lub niedostępności,
- przy jednym artefakcie dashboard jest wyświetlany bez dodatkowego selektora,
- dropdown wyników pojawia się dopiero od dwóch artefaktów,
- informacje techniczne o artefakcie są dostępne w zwijanej sekcji,
- nie ma dużej tabeli artefaktów ani stałego komunikatu `Oczekiwanie/Gotowe`.

### 6. Podsumowanie graficzne

Dodano lekkie elementy wizualne bez rozbudowanego dashboardu:

- KPI: ramki, CAN ID, czas sesji, średnia częstotliwość, anomalie czasu,
- Top 5 najaktywniejszych CAN ID,
- subtelne paski udziału,
- tabela `Statystyki CAN ID`,
- filtrowanie po CAN ID, typie ramki, formacie STD/EXT i kanale,
- sortowanie kolumn.

Twarde dane i tabela pozostają podstawą; grafika jest wyłącznie warstwą pomocniczą.

## Etapy i PR-y

- PR #26 — fundament domenowy,
- PR #27 — Extension API,
- PR #28 — provider statystyk sesji,
- PR #29 — poprawka układu paska Live Capture,
- PR #30 — workflow analiz zapisanej sesji,
- PR #31 — tabela statystyk CAN ID,
- PR #32 — lekkie podsumowanie graficzne,
- PR #33 — kompaktowy wybór artefaktu,
- PR #34 — minimalny chrome zakładki Analizy.

PR-y są stacked. Nic nie zostało scalone do `main` w ramach tego etapu.

## Walidacja

Dla końcowego funkcjonalnego HEAD Stage 8 potwierdzono:

- `Tests` — success,
- `GUI Regressions` — success,
- `Live Preview Capacity` — success,
- `Windows GitHub-Hosted CI` — success,
- ręczne uruchomienie przez użytkownika — poprawne działanie.

Dedykowane smoke testy obejmują:

- uruchomienie analizy z GUI,
- wykonanie w tle,
- anulowanie,
- trwały artefakt,
- ponowne otwarcie sesji,
- tabelę i filtrowanie CAN ID,
- KPI i Top CAN ID,
- wiele artefaktów,
- ukrywanie zbędnego UI,
- niezmienność SHA-256 sesji źródłowej.

## Zachowane kontrakty

Nie zmieniono:

- `CaptureService`,
- backendu Kvaser,
- lifecycle CANlib,
- formatu sesji,
- kolejności ani kompletności pełnego zapisu surowych ramek,
- źródłowych plików `*.crt.jsonl`,
- działania filtrów Live i zapisanych sesji,
- dekoderów,
- mechanizmu DBC,
- funkcji CAN TX.

Jedna instancja projektu CRT nadal odpowiada jednemu badanemu ECU.

## Następny obszar prac

Następna rozmowa ma wrócić do tworzenia i edytowania projektów CRT.

Pierwszy krok powinien obejmować audyt obecnego przepływu:

- `Nowy projekt`,
- `Otwórz projekt`,
- formularz danych projektu,
- trwałość metadanych,
- edycję istniejącego projektu,
- walidację ścieżek i nazwy,
- zachowanie zgodności ze strukturą `.crt` i `project.sqlite`.

Należy najpierw przeczytać ten raport, sprawdzić aktualny HEAD gałęzi Stage 8 i dopiero potem utworzyć nową, osobną gałąź stacked.

## Ograniczenia dla następnego etapu

- nie zmieniać `CaptureService`, Kvasera ani CANlib,
- nie zmieniać formatu sesji ani zapisu ramek,
- nie modyfikować działającej warstwy analiz bez wyraźnej potrzeby,
- nie scalać stacked PR-ów bez decyzji użytkownika,
- pełne testy wykonywać na GitHub-hosted Actions,
- po większym etapie wykonać checkpoint: commit, push i raport/handoff.
