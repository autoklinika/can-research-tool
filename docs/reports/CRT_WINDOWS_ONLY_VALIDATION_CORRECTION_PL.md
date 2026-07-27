# Korekta procesu walidacji CRT — wyłącznie Windows

Data: 2026-07-27

## Decyzja właściciela projektu

CAN Research Tool jest aplikacją przeznaczoną i używaną wyłącznie na Windows.

Od tej decyzji obowiązuje zasada:

> Testy aplikacji CRT, GUI, integracji i zachowania użytkowego wykonujemy wyłącznie na Windows.

Ubuntu oraz inne systemy nie są platformami docelowymi CRT i nie mogą być używane jako wymagany ani autorytatywny checkpoint aplikacji.

## Korekta wcześniejszego procesu

Wcześniejsze etapy Comparison Visualization oraz Help Center uruchamiały część workflowów także na Ubuntu. Było to zbędne i niezgodne z rzeczywistym środowiskiem użytkownika.

Wyniki tych historycznych przebiegów pozostają informacją techniczną, ale od teraz:

- nie są wymagane,
- nie są raportowane jako checkpoint CRT,
- nie wpływają na decyzję o gotowości funkcji,
- nie będą ponownie uruchamiane przez aktywne workflowy aktualnego stosu.

## Obowiązująca macierz

### GitHub-hosted

Podstawowa automatyczna walidacja:

`windows-latest`

### Windows self-hosted

Używany tylko do testów wymagających:

- fizycznego Kvasera,
- CANlib,
- rzeczywistego interfejsu CAN,
- innego sprzętu niedostępnego na runnerze GitHub-hosted.

Nie należy blokować pasywnych etapów GUI i analizy z powodu braku self-hosted runnera.

### Test ręczny

Każde zachowanie użytkowe zatwierdzamy ręcznie na rzeczywistym Windows użytkownika.

## Zmiany w workflowach

Na gałęzi `agent/comparison-visualization-stage2d2-uds-timeline` przepisano na Windows wszystkie aktywne workflowy aplikacji w aktualnym stosie:

- ogólne testy,
- GUI Regressions,
- Live Preview Capacity,
- Comparison Dashboard,
- Comparison Timeline,
- Stage 2B Persistent Alignment,
- Stage 2C1 Timing i jitter,
- Stage 2C2 Latencja UDS,
- Stage 2D1 Eksplorator transakcji UDS,
- Stage 2D2 Oś UDS,
- Help Center.

Usunięto macierze Ubuntu/Windows oraz kroki instalujące pakiety systemowe przez `apt-get`.

## Help Center

`Help Center: nie dotyczy — korekta dotyczy wyłącznie CI i procesu walidacji, bez zmiany zachowania programu dla użytkownika.`

## Status Stage 2D2

Stage 2D2 pozostaje draftem i bez merge.

Pełny test ręczny osi UDS nadal oczekuje na odpowiednie logi zawierające rzeczywiste transakcje request/response UDS. Na obecnych logach potwierdzono poprawne wczytanie wyrównania i obsługę pustego artefaktu transakcji.
