# Comparison Visualization Stage 2A — handoff do kolejnej rozmowy

## Repozytorium i gałąź

- repozytorium: `autoklinika/can-research-tool`,
- gałąź: `agent/comparison-visualization-stage2a-timeline`,
- baza stacked: `agent/comparison-visualization-stage1`, PR #49.

Gałąź Stage 2A została utworzona osobno. Nie wykonano merge PR #49 ani Stage 2A.
Nie oznaczać PR jako ready i nie scalać bez wyraźnego polecenia właściciela.

## Aktualny zakres

W produkcyjnym oknie porównań znajduje się karta `Oś czasu`, która obsługuje:

- wspólną względną skalę czasu,
- tor dla każdej sesji,
- synchronizację do początku sesji,
- synchronizację do pierwszego dokładnego klucza wiadomości,
- bounded sampling całego przebiegu,
- przejście z punktu do dokładnej ramki źródłowej.

## Najważniejsze pliki

- `app/comparison_timeline.py`,
- `gui/comparison_timeline_view.py`,
- `gui/comparison_visualization_hardened.py`,
- `gui/comparison_evidence_navigation.py`,
- `gui/comparison_sets_analysis_view.py`,
- `gui/comparison_sets_shell.py`,
- `tests/test_comparison_timeline.py`,
- `tests_gui/comparison_timeline_smoke.py`.

## Test ręczny na Windows

1. Uruchom CRT z gałęzi Stage 2A.
2. Otwórz zestaw porównawczy i okno `Porównanie logów`.
3. Wejdź do karty `Oś czasu`.
4. Zbuduj oś dla trybu `Początek każdej sesji`.
5. Kliknij punkt i wybierz `Otwórz ramkę źródłową`.
6. Potwierdź otwarcie właściwej sesji i dokładnego wiersza.
7. Przywróć okno porównania.
8. Wybierz tryb klucza wiadomości, np. `0:EXT:1AFFB680:data`.
9. Sprawdź `t = 0` dla każdej sesji zawierającej kotwicę oraz ostrzeżenie dla
   sesji bez kotwicy.

## Następny rekomendowany etap

`Comparison Visualization Stage 2B — trwałe wyrównania i kotwice zdarzeń`

Proponowany zakres:

- wersjonowany artefakt wyrównania czasu,
- kotwica znacznika operatora,
- kotwica zdarzenia protokołu lub wyniku analizy,
- trwałe `source_row` kotwic i ostrzeżenia,
- ponowne otwarcie gotowego wyrównania bez skanowania sesji,
- przygotowanie danych pod jitter, latencję i czasy odpowiedzi UDS.

## Stałe ograniczenia

Nie zmieniać bez osobnej decyzji architektonicznej:

- `CaptureService`,
- Kvasera i CANlib,
- CAN TX/RX,
- formatu sesji,
- kompletności i kolejności surowego zapisu,
- schematu indeksów,
- bounded modelu GUI,
- schematu `.crt/project.sqlite`.
