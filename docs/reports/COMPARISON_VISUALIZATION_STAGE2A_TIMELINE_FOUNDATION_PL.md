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
- zachowanie pierwszego i ostatniego punktu oraz dokładnej kotwicy `t = 0`,
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
Rozpoznanie ścieżki sesji i odczyt SQLite odbywa się poza wątkiem GUI. Sukces
jest zgłaszany dopiero po potwierdzeniu rzeczywistego zaznaczenia wiersza.

## Wydajność

Źródłowa sesja jest skanowana sekwencyjnie w zadaniu tła. GUI nie materializuje
pełnej liczby ramek. Dla każdej sesji wyznaczana jest deterministyczna próbka
ograniczona do 2000 punktów. Próbka zawsze zachowuje początek i koniec sesji,
a w trybie klucza wiadomości także dokładny punkt kotwicy `t = 0`.

## Testy

Dodano:

- `tests/test_comparison_timeline.py`,
- `tests_gui/comparison_timeline_smoke.py`,
- workflow `Comparison Timeline Validation` na Ubuntu i Windows GitHub-hosted.

Testy obejmują:

- wyrównanie do początku sesji,
- wyrównanie do dokładnego klucza wiadomości,
- brak kotwicy bez fałszywej synchronizacji,
- bounded sampling z zachowaniem początku, końca i kotwicy,
- zachowanie `source_row`,
- anulowanie i odrzucanie spóźnionych wyników,
- czyszczenie starego zaznaczenia po błędzie,
- obecność karty w produkcyjnym dialogu,
- pełny handoff dokładnego wiersza do produkcyjnej nawigacji zapisanej sesji.

## Potwierdzenie ręczne właściciela

Dnia 2026-07-27 właściciel projektu uruchomił Stage 2A na Windows i potwierdził,
że funkcja działa w produkcyjnym GUI.

Ręcznie potwierdzony przepływ:

`Porównanie logów → Oś czasu → Zbuduj oś czasu → wybór punktu → Otwórz ramkę źródłową → właściwa sesja → dokładna ramka źródłowa`

Potwierdzenie obejmuje widoczność karty w GUI, poprawne zbudowanie osi czasu oraz
przejście z punktu osi do odpowiadającej mu ramki. Jest to funkcjonalny checkpoint
Stage 2A. Nie stanowi automatycznej zgody na oznaczenie PR jako ready ani na merge.

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
