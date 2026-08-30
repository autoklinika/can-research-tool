# CRT — Comparison Visualization stack integration pre-merge checkpoint

Data: 2026-08-30

## Cel

Ten dokument zapisuje stan porządkowania repozytorium przed integracją zaakceptowanego stacka Comparison Visualization do `main`.

## Zakres integration PR

Integration PR obejmuje skumulowany, ręcznie zaakceptowany stan:

- Comparison Visualization Stage 1,
- Comparison Timeline Stage 2A,
- Persistent Alignment Stage 2B,
- Inter-Frame Timing Stage 2C1,
- UDS Latency Stage 2C2,
- UDS Transaction Explorer Stage 2D1,
- Help Center Stage 1.

Historyczne stacked PR-y: #49–#55.

## Cel porządkowy

Po końcowej walidacji jeden integration PR ma zastąpić historyczny łańcuch stacked PR-ów jako jedyny kandydat do integracji z `main`.

Stare PR-y #49–#55 należy zamknąć jako superseded dopiero po bezpiecznym zakończeniu integracji.

## Poza zakresem

Nie włączamy do tego integration PR:

- Stage 2D2 UDS Timeline z PR #56,
- korekty Windows-only i teardown fixes dodanych później w #56,
- near-term roadmap Signal Discovery / Heavy-Duty z PR #57.

Stage 2D2 pozostaje odłożony do pełnego ręcznego odbioru na logach zawierających rzeczywistą komunikację UDS.

Korektę Windows-only należy wydzielić z #56 jako niezależną zmianę procesowo-testową, bez włączania nieodebranej funkcji Stage 2D2.

## Baza i checkpoint

- baza `main`: `f6c21c6ebd4da081035b1b2a671fccd1bee5ab0e`,
- zaakceptowany HEAD #55: `ba7dae36f0dbe92b5771c5c7faf53e9a27e8b502`,
- integration branch: `integration/comparison-through-help-center`,
- integration PR: #58.

Przed dodaniem tego dokumentu integration branch był dokładną kopią zaakceptowanego HEAD #55.

## Walidacja historycznego HEAD #55

Na zaakceptowanym HEAD zakończyły się sukcesem między innymi:

- Windows GitHub-Hosted CI,
- GUI Regressions,
- Live Preview Capacity,
- Comparison Dashboard Validation,
- Comparison Timeline Validation,
- Comparison Timeline Stage 2B Validation,
- Comparison Inter-Frame Timing Stage 2C1 Validation,
- Comparison UDS Latency Stage 2C2 Validation,
- Comparison UDS Transaction Explorer Stage 2D1 Validation,
- Help Center Validation.

Historyczny ogólny workflow `Tests` został anulowany. Próba jego ponownego uruchomienia 2026-08-30 została odrzucona przez GitHub, ponieważ run miał ponad miesiąc.

## Powód tego commit-a

Ten commit jest wyłącznie dokumentacyjny i nie zmienia zachowania CRT. Jego celem jest:

1. utrwalenie stanu integracji,
2. wywołanie świeżej walidacji integration PR na aktualnym HEAD,
3. uzyskanie jednoznacznego checkpointu przed ewentualnym merge.

## Zachowane kontrakty

Bez zmian pozostają:

- `CaptureService`,
- Kvaser i lifecycle CANlib,
- CAN TX/RX,
- format sesji i markerów,
- kompletność i kolejność pełnego zapisu surowych ramek,
- trwałe indeksy,
- bounded/stronicowany model zapisanych sesji,
- schemat `.crt/project.sqlite`.

## Warunek integracji

Nie wykonywać merge do `main` bez:

1. świeżej, zakończonej sukcesem walidacji integration PR,
2. sprawdzenia mergeability względem aktualnego `main`,
3. osobnej, jednoznacznej zgody właściciela projektu.
