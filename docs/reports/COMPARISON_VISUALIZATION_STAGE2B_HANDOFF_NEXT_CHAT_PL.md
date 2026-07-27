# Comparison Visualization Stage 2B — handoff do kolejnej rozmowy

## Repozytorium i gałąź

- repozytorium: `autoklinika/can-research-tool`,
- gałąź: `agent/comparison-visualization-stage2b-persistent-alignment`,
- baza stacked: `agent/comparison-visualization-stage2a-timeline`, PR #50.

Nie wykonywać merge ani nie oznaczać PR jako ready bez wyraźnego polecenia
właściciela.

## Dostarczony zakres

Stage 2B dodaje wersjonowany artefakt osi czasu, automatyczne odtwarzanie bez
skanowania sesji oraz kotwice:

- początku sesji,
- N-tego dokładnego klucza wiadomości,
- N-tego znacznika operatora,
- ręcznie wybranego dokładnego zdarzenia per sesja.

## Najważniejsze pliki

- `app/comparison_timeline.py`,
- `app/comparison_timeline_artifacts.py`,
- `gui/comparison_timeline_view.py`,
- `tests/test_comparison_timeline.py`,
- `tests/test_comparison_timeline_artifacts.py`,
- `tests_gui/comparison_timeline_smoke.py`,
- `.github/workflows/comparison-timeline-stage2b.yml`.

## Test ręczny na Windows

1. Uruchom CRT z gałęzi Stage 2B.
2. Otwórz zestaw porównawczy i kartę `Oś czasu`.
3. Zbuduj oś względem początku sesji.
4. Wybierz po jednym punkcie z każdej sesji i kliknij
   `Ustaw jako kotwicę sesji`.
5. Wybierz `Wybrane dokładne zdarzenia` i zbuduj oś.
6. Kliknij `Zapisz wyrównanie`.
7. Zamknij i ponownie otwórz okno porównania.
8. Potwierdź automatyczne wczytanie osi bez skanowania sesji.
9. Wybierz tryb znacznika operatora, podaj dokładną nazwę i sprawdź `t = 0`.
10. Otwórz punkt osi i potwierdź właściwą sesję oraz dokładny `source_row`.

## Następny rekomendowany etap

`Comparison Visualization Stage 2C — jitter, latencja i transakcje UDS`

Proponowany zakres:

- artefakt statystyk inter-frame timing,
- rozkład i percentyle jitteru dla klucza wiadomości,
- deterministyczne parowanie request/response,
- czasy odpowiedzi UDS i obsługa `0x78 ResponsePending`,
- porównanie latencji między sesjami,
- wykresy i nawigacja do par dowodowych.

## Stałe ograniczenia

Nie zmieniać bez osobnej decyzji architektonicznej:

- `CaptureService`,
- Kvasera i CANlib,
- CAN TX/RX,
- formatu sesji i markerów,
- kompletności i kolejności surowego zapisu,
- schematu indeksów,
- bounded modelu GUI,
- schematu `.crt/project.sqlite`.
