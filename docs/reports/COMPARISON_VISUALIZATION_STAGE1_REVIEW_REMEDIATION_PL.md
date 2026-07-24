# Comparison Visualization Stage 1 — domknięcie uwag review

Data: 2026-07-24

Gałąź: `agent/comparison-visualization-stage1`

PR: `#49`

Commit techniczny: `39741c5fbfb6a2680e45aa7cf6ae89f97bedc36e`

## Cel

Zweryfikować wszystkie nierozwiązane uwagi Copilot Review i poprawić wyłącznie potwierdzone problemy techniczne bez rozszerzania zakresu etapu.

## Wprowadzone poprawki

- defensywne parsowanie CAN ID używanego przez sortowanie; niepoprawna lub pusta wartość nie powoduje `ValueError`,
- walidacja zakresu CAN ID zależnie od formatu: `STD <= 0x7FF`, `EXT <= 0x1FFFFFFF`,
- stabilne sortowanie z pełnym kluczem wiadomości jako rozstrzygnięciem remisu,
- zachowanie poprawnego mapowania zaznaczenia po sortowaniu i stronicowaniu przez wyłączenie natywnego sortowania `QTableWidget` w używanym widoku,
- poprawione nagłówki `Ramki bazowe` i `Ramki porównywane`,
- użycie stałych statusów w Inspektorze zamiast powtarzanych literałów,
- dokładne mapowanie zmian sekwencji po pełnych kluczach wiadomości zamiast dopasowania podciągu,
- bezpieczny lifecycle zadań `QRunnable`: zadania nie są automatycznie kasowane i pozostają przechowywane do sygnału `finished`, także po anulowaniu,
- spójne polskie komunikaty błędów lokalizacji dowodów,
- poprawiona obsługa kolejnych akcji odzyskiwania okna po błędzie (`continue` zamiast przedwczesnego `break`),
- jawne raportowanie błędów integralności, odczytu i schematu trwałych artefaktów zamiast cichego pomijania danych,
- testy regresyjne dla zakresu STD/EXT, bezpiecznego parsowania wartości hex i dokładnego dopasowania kluczy sekwencji.

## Uwagi zweryfikowane bez zmian

Nazwy schematów artefaktów zostały sprawdzone względem providerów i pozostają poprawne:

- `crt.comparison_statistics`,
- `crt.payload_differences`,
- `crt.message_sequence_differences`.

Nie zmieniono niemodalnego modelu okna porównania. Po otwarciu dowodu okno pozostaje dostępne, może zostać zminimalizowane, a główne CRT przejmuje fokus zgodnie z wcześniejszym ręcznym potwierdzeniem.

Nie wprowadzono zmian kosmetycznych, które nie usuwały regresji lub ryzyka technicznego.

## Zachowane kontrakty

Bez zmian pozostają:

- `CaptureService`,
- backend Kvaser,
- lifecycle CANlib,
- kod CAN TX/RX,
- format sesji,
- kolejność i kompletność pełnego zapisu surowych ramek,
- schemat trwałych indeksów,
- bounded/stronicowany model zapisanych sesji,
- schemat `.crt/project.sqlite`,
- istniejące schematy artefaktów.

## Walidacja

Pełna walidacja jest wykonywana przez GitHub Actions dla finalnego HEAD gałęzi. Obejmuje workflowy:

- `Tests`,
- `GUI Regressions`,
- `Live Preview Capacity`,
- `Windows GitHub-Hosted CI`,
- `Windows Self-Hosted CI`.

PR pozostaje draftem. Nie należy oznaczać go jako Ready for Review ani wykonywać merge bez wyraźnego polecenia właściciela projektu.
