# Comparison Visualization Stage 2A — fundament osi czasu

## Cel

Dodać pierwszy bezpieczny etap analizy czasowej wielu zapisanych sesji bez zmiany
formatu sesji, surowych ramek ani trwałych indeksów CRT.

## Zakres dostarczony

- nowa karta `Oś czasu` w produkcyjnym oknie `Porównanie logów`,
- wspólna względna skala czasu dla wszystkich sesji zestawu,
- osobny tor wizualny dla każdej sesji,
- synchronizacja względem początku sesji,
- synchronizacja względem pierwszego dokładnego wystąpienia klucza wiadomości,
- dokładny klucz obejmujący kanał, STD/EXT, CAN ID i typ ramki,
- jawne ostrzeżenie, gdy sesja nie zawiera kotwicy,
- bounded, równomierne próbkowanie maksymalnie 2000 punktów na sesję,
- zachowanie rzeczywistego `source_row` każdego prezentowanego punktu,
- przejście z punktu osi czasu do dokładnej ramki zapisanej sesji,
- anulowalne budowanie osi czasu w `QThreadPool`,
- anulowanie pracy po ponownym uruchomieniu, zamknięciu dialogu lub zmianie projektu.

## Semantyka synchronizacji

### Początek sesji

Pierwsza ramka każdej sesji przyjmuje `t = 0`. Pozwala to porównać przebieg
logów od rozpoczęcia rejestracji, nawet gdy bezwzględne timestampy pochodzą z
różnych uruchomień.

### Klucz wiadomości

Pierwsze wystąpienie podanego klucza w każdej sesji przyjmuje `t = 0`.
Przykład:

`0:EXT:1AFFB680:data`

Sesja bez takiej ramki nie jest sztucznie wyrównywana. Jej tor pozostaje jawnie
oznaczony jako niesynchronizowany.

## Nawigacja do źródła

Każdy punkt osi czasu zachowuje:

- identyfikator sesji,
- numer `source_row`,
- sekwencję,
- timestamp,
- pełny klucz wiadomości,
- DLC i payload.

Dwukrotne kliknięcie punktu albo przycisk `Otwórz ramkę źródłową` przekazuje
bezpośredni `source_row` do istniejącego bounded navigatora zapisanych sesji.
Sukces jest zgłaszany dopiero po potwierdzeniu rzeczywistego zaznaczenia wiersza.

## Wydajność

Źródłowa sesja jest skanowana sekwencyjnie w zadaniu tła. GUI nie materializuje
pełnej liczby ramek. Dla każdej sesji wyznaczany jest deterministyczny krok
próbkowania tak, aby prezentacja była ograniczona do 2000 punktów i obejmowała
cały czas trwania sesji.

## Testy

Dodano:

- `tests/test_comparison_timeline.py`,
- `tests_gui/comparison_timeline_smoke.py`,
- workflow `Comparison Timeline Validation` na Ubuntu i Windows GitHub-hosted.

Testy obejmują:

- wyrównanie do początku sesji,
- wyrównanie do dokładnego klucza wiadomości,
- brak kotwicy bez fałszywej synchronizacji,
- bounded sampling,
- zachowanie `source_row`,
- anulowanie,
- obecność karty w produkcyjnym dialogu,
- handoff dokładnego wiersza do nawigacji dowodowej.

## Zachowane kontrakty

Bez zmian pozostają:

- `CaptureService`,
- backend Kvaser i lifecycle CANlib,
- CAN TX/RX,
- format sesji,
- kolejność i kompletność pełnego zapisu surowych ramek,
- schemat trwałych indeksów,
- bounded/stronicowany model zapisanych sesji,
- schemat `.crt/project.sqlite`,
- istniejące formaty artefaktów porównawczych.

## Świadomie poza zakresem Stage 2A

- trwały artefakt konfiguracji wyrównania,
- synchronizacja według znacznika operatora,
- automatyczne kotwice zdarzeń protokołu,
- jitter i rozkład odstępów międzyramkowych,
- pomiar czasu odpowiedzi UDS,
- grupowanie milionów punktów zależne od poziomu zoomu.
