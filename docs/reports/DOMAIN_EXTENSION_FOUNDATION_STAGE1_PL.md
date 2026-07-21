# CRT Domain & Extension Foundation — Stage 1

## Status

Pierwsza część fundamentu modelu danych opisanego w
`docs/CRT_RESEARCH_PLATFORM_MASTER_PLAN_PL.md`.

Etap nie dodaje nowych funkcji analitycznych użytkownika. Przygotowuje trwałe
kontrakty i schemat danych, na których będą budowane Extension Registry,
Analysis Providers, Artifact Writer i Finding Writer.

## Zakres

Dodano niezależne od GUI modele domenowe dla:

- profilu jednego badanego ECU,
- twierdzeń profilu wraz z pochodzeniem i statusem weryfikacji,
- zestawów porównawczych wielu sesji,
- wejść i uruchomień analiz,
- wersjonowanych artefaktów,
- źródeł artefaktów,
- znalezisk i historii ich statusu,
- referencji do pojedynczych ramek i zakresów ramek.

Dodano `ProjectDomainStore`, który zapisuje te obiekty wyłącznie w
`.crt/project.sqlite`.

## Referencje dowodowe

Podstawowa referencja ramki zawiera:

```text
session_id
source_row
sequence
timestamp_ns
```

`session_id + source_row` jest trwałym odwołaniem do pozycji ramki w
niezmiennej sesji. `sequence` i `timestamp_ns` stanowią dodatkowy materiał
kontrolny i nawigacyjny.

Zakres ramek zapisuje:

```text
session_id
start_source_row
end_source_row
```

Repozytorium sprawdza, czy wskazane sesje istnieją i czy indeksy ramek mieszczą
się w zarejestrowanej liczbie ramek sesji.

## Migracje projektu

Dodano addytywny schemat domenowy w wersji `1` oraz tabelę
`schema_migrations`.

Migracja tworzy:

- `ecu_profiles`,
- `ecu_profile_claims`,
- `comparison_sets`,
- `comparison_set_sessions`,
- `analysis_runs`,
- `analysis_inputs`,
- `artifacts`,
- `artifact_sources`,
- `findings`,
- `finding_evidence`,
- `finding_status_history`.

Migracje są wykonywane transakcyjnie przez `BEGIN IMMEDIATE`. Niepełna migracja
jest wycofywana. Ponowne otwarcie warstwy domenowej nie wykonuje tej samej
migracji drugi raz.

Build CRT odmawia pracy z bazą o wersji schematu nowszej niż wersja przez niego
obsługiwana.

## Pochodzenie danych

Twierdzenie profilu ECU zapisuje:

- pole profilu,
- wartość w kanonicznym JSON,
- źródło: użytkownik, diagnostyka, analiza deterministyczna albo przyszłe AI,
- status weryfikacji,
- opcjonalny poziom pewności,
- referencje dowodowe.

Dane rozpoznane automatycznie nie nadpisują po cichu potwierdzonego profilu.
Mogą istnieć jako osobne twierdzenia do zweryfikowania.

## Analizy i artefakty

Uruchomienie analizy zapisuje:

- identyfikator i wersję providera,
- wersję API CRT,
- wersję algorytmu,
- wejścia analizy,
- parametry w kanonicznym JSON,
- stan wykonania,
- czas rozpoczęcia i zakończenia,
- błąd wykonania.

Dozwolone przejścia stanu są jawne. Zakończone, anulowane lub nieudane
uruchomienie nie może zostać ponownie uruchomione przez zmianę samego rekordu.

Artefakt zapisuje:

- typ i wersję schematu,
- źródłowe uruchomienie analizy,
- provider i wersję algorytmu,
- względną ścieżkę projektu,
- SHA-256,
- metadane,
- uporządkowane źródła sesyjne i zakresy ramek.

Ten etap zapisuje wyłącznie metadane artefaktu. Atomowy `ArtifactWriter` będzie
częścią następnego etapu API rozszerzeń.

## Znaleziska

Znalezisko posiada status:

- `hypothesis`,
- `to_verify`,
- `partially_confirmed`,
- `confirmed`,
- `rejected`.

Każda zmiana statusu jest dopisywana do historii wraz z komentarzem operatora.
Znalezisko bez dowodu nie może zostać utworzone.

Pola `ai_provider` i `ai_model` są wyłącznie metadanymi pochodzenia. Ten etap nie
uruchamia AI i nie zawiera AI Provider.

## Chronione kontrakty

Etap nie zmienia:

- `CaptureService`,
- backendu Kvaser,
- lifecycle CANlib,
- formatów sesji,
- `SessionStreamWriter`,
- `SessionPagedReader`,
- kolejności ani kompletności zapisu ramek,
- indeksów sesji,
- filtrów i grupowania GUI.

`ProjectDomainStore` nie posiada API zapisu do plików sesji. Operuje wyłącznie
na `project.sqlite`.

Test regresyjny oblicza SHA-256 plików sesji, wykonuje operacje domenowe i
potwierdza, że skróty pozostały identyczne.

## Świadomie poza zakresem

- Extension Registry,
- manifest rozszerzenia,
- dynamiczne ładowanie modułów,
- `ProjectContext` dostępny dla rozszerzeń,
- `FrameQuery` i `LogicalMessageQuery`,
- atomowy `ArtifactWriter`,
- `FindingWriter`,
- statystyki i analiza czasowa,
- CAN Intelligence Engine,
- AI Provider,
- aktywna transmisja CAN,
- integracja GUI.

## Następny etap

`CRT Extension API Foundation — Stage 2` powinien dodać:

1. wersjonowany `ExtensionManifest`,
2. `ExtensionRegistry`,
3. kontrakty tylko do odczytu: `ProjectContext`, `SessionSource`, `FrameQuery`,
4. `AnalysisContext`, `CancellationToken` i `ProgressReporter`,
5. atomowy `ArtifactWriter` i kontrolowany `FindingWriter`,
6. testowy provider zgodności bez ekspozycji w normalnym GUI,
7. odrzucenie modułów `requires_can_tx=true` przez pasywny runtime.
