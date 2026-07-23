# Handoff — Comparison Statistics Provider Stage 1

## Repozytorium

`autoklinika/can-research-tool`

## Gałąź robocza

`agent/comparison-statistics-provider-stage1`

Gałąź jest stacked na:

- `agent/comparison-sets-stage1`,
- PR #44,
- commit bazowy `5f8522da066eedacfe9a1a237ddc5250a8e3c56b`.

PR etapu: #45, nadal draft. Sprawdź aktualny HEAD gałęzi przed wykonaniem jakichkolwiek zmian, ponieważ dokumentacja walidacyjna została dopisana po pierwotnym commicie implementacyjnym.

## Aktualny status walidacji

Ręczne uruchomienie w VS Code zostało potwierdzone przez użytkownika 22 lipca 2026 — funkcja działa.

W chwili przygotowania tego handoffu:

- PR #45 był otwarty, mergeable i draft,
- nie było submitted reviews,
- nie było review threads,
- workflowy GitHub Actions dla wcześniejszego HEAD pozostawały w kolejce,
- końcowa walidacja techniczna nie została jeszcze zamknięta.

Nie oznaczaj PR jako ready i nie wykonuj merge bez wyraźnego polecenia użytkownika.

## Co zostało wykonane

Dodano pierwszy deterministyczny `Comparison Provider` CRT:

- `crt.comparison.statistics`,
- typ manifestu `comparison`,
- porównanie wielu zapisanych sesji względem jawnej lub domyślnej bazy,
- nowe i brakujące klucze CAN ID,
- różnice liczby ramek i udziału,
- różnice średniej częstotliwości,
- trwały artefakt `comparison-statistics.json`,
- źródła z SHA-256 i rolą sesji,
- aplikacyjny `ComparisonAnalysisService`,
- katalog artefaktów dla zestawu,
- asynchroniczny dialog analizy i prezentacja wyników,
- testy jednostkowe i smoke GUI,
- kroki CI na Linuxie i Windows.

## Ważna decyzja architektoniczna

Nie rejestrowano providera porównawczego jako zwykłego `ANALYSIS`.

Extension API zostało rozszerzone o:

- `ComparisonProvider`,
- `get_comparison()`,
- `execute_comparison()`,
- `ComparisonContext`.

Dzięki temu kolejne porównania payloadów, protokołów, transferów i napraw korzystają z właściwego kontraktu typu `COMPARISON`.

Dotychczasowe API analiz pojedynczej sesji pozostaje kompatybilne.

## Granice Stage 1

Stage 1 porównuje całe sesje bez synchronizacji osi czasu.

Provider celowo odrzuca `synchronization_mode` inny niż `none`. Nie dodawaj cichego wsparcia `manual`, `marker` ani przesuwania timestampów bez osobnego projektu kontraktu synchronizacji.

Stage 1 nie porównuje jeszcze:

- payloadów bajt po bajcie,
- PGN i protokołów,
- UDS/DTC,
- transferów,
- znaczników i osi zdarzeń.

## Pliki kluczowe

- `app/extensions/builtin/comparison_statistics.py`
- `app/comparison_analysis_service.py`
- `app/extensions/contracts.py`
- `app/extensions/registry.py`
- `app/extensions/runner.py`
- `app/artifact_catalog.py`
- `gui/comparison_analysis_dialog.py`
- `gui/comparison_sets_analysis_view.py`
- `tests/test_comparison_statistics_provider.py`
- `tests_gui/comparison_statistics_smoke.py`

Pełny opis znajduje się w:

`docs/reports/COMPARISON_STATISTICS_PROVIDER_STAGE1_IMPLEMENTATION_REPORT_PL.md`

Plan kolejnego etapu znajduje się w:

`docs/reports/PAYLOAD_DIFFERENCE_PROVIDER_STAGE2_PLAN_PL.md`

## Walidacja do wykonania w następnym czacie

1. Sprawdź aktualny HEAD PR #45.
2. Sprawdź status stacked PR #44 i PR #45, diff, review threads, reviews i CI.
3. Zweryfikuj workflowy dla aktualnego HEAD, a nie dla starszego commita.
4. Jeżeli CI nie jest zielone, odczytaj dokładny job i log przed modyfikacją kodu.
5. Jeżeli CI jest zielone, zapisz końcowy status w raporcie implementacyjnym.
6. Zweryfikuj szczególnie Windows teardown po zamknięciu dialogu i `project.sqlite`.
7. Potwierdź testem automatycznym, że ponowne uruchomienie analizy daje identyczną treść i SHA-256 artefaktu.
8. Nie rozpoczynaj implementacji Stage 2 na gałęzi Stage 1. Po zielonym CI utwórz osobną gałąź stacked na aktualnym HEAD PR #45.

## Nienaruszalne kontrakty

Nie zmieniaj:

- `CaptureService`,
- Kvasera i lifecycle CANlib,
- CAN TX/RX,
- formatu sesji,
- kolejności pełnego zapisu ramek,
- trwałych indeksów wyszukiwania,
- schematu `.crt/project.sqlite`,
- kontraktów Project Properties i Project Catalog,
- artefaktu `session-statistics.json`.

Surowe ramki i pliki sesji pozostają niezmiennym źródłem prawdy.

## Następny proponowany etap

Po ręcznej akceptacji i zielonym CI rozpocznij na osobnej gałęzi:

`Payload Difference Provider Stage 2`

Zakres powinien objąć warianty payloadów dla wspólnych kluczy wiadomości, bajty stałe i zmienne oraz wartości występujące tylko w części sesji. Wynik nadal musi być deterministycznym artefaktem z pełnym śladem źródłowym.
