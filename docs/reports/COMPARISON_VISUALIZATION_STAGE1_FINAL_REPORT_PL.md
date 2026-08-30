# Comparison Visualization Stage 1 — raport końcowy

## Status

Etap został funkcjonalnie zakończony na gałęzi:

`agent/comparison-visualization-stage1`

Powiązany pull request:

`#49 Add graphical comparison dashboard`

PR pozostaje draftem. Nie należy oznaczać go jako ready ani wykonywać merge bez wyraźnego polecenia właściciela projektu.

## Cel etapu

Celem było dodanie czytelnej, graficznej prezentacji trwałych analiz porównawczych bez naruszania źródłowych sesji CAN, bounded modeli GUI ani kontraktów warstwy przechwytywania.

## Dostarczone funkcje

### Dashboard porównania

Dodano graficzny przegląd zestawu porównawczego obejmujący:

- pięć kart KPI,
- heatmapę obecności wiadomości,
- ranking istotnych zmian częstotliwości,
- pełną tabelę różnic ze stronicowaniem,
- inspektor wybranego klucza wiadomości,
- podgląd różnic payloadu,
- oddzielną kartę z technicznymi danymi artefaktów.

Dashboard agreguje najnowsze trwałe artefakty według schematów:

- `crt.comparison_statistics`,
- `crt.payload_differences`,
- `crt.message_sequence_differences`.

Zwykłe renderowanie dashboardu nie wykonuje ponownego skanowania źródłowych sesji.

### Wykonywanie analiz

Dodano główną akcję `Uruchom komplet analiz`, która wykonuje kolejno dostępne pasywne providery.

Wybór pojedynczego providera został przeniesiony do domyślnie zwiniętego panelu `Zaawansowane`.

### Filtrowanie i sortowanie

Tabela różnic obsługuje:

- wyszukiwanie po CAN ID, pełnym kluczu wiadomości i nazwie sesji,
- filtrowanie statusu: nowe, brakujące, zmienione i bez zmian,
- czyszczenie filtrów,
- licznik wyniku filtrowanego i pełnego,
- sortowanie całego przefiltrowanego zbioru przed stronicowaniem.

Sortowanie nie jest ograniczone do aktualnie widocznej strony modelu Qt.

### Stronicowanie

Pełny wynik nie jest globalnie ucinany. Dostępne są rozmiary strony:

- 50,
- 100,
- 250,
- 500 wierszy.

Heatmapa i ranking pozostają zwartymi podsumowaniami Top, natomiast pełny zbiór jest dostępny w tabeli.

### Nawigacja do dowodów

Akcja `Otwórz dowody` oraz podwójne kliknięcie wiersza:

1. wybierają właściwą sesję źródłową,
2. lokalizują pierwszą ramkę odpowiadającą pełnemu kluczowi wiadomości,
3. otwierają zapisaną sesję w głównym workspace CRT,
4. przechodzą do właściwej strony bounded modelu,
5. zaznaczają ramkę źródłową.

Dla brakującego ID dowód jest wybierany z sesji bazowej. Dla nowego i zmienionego ID używana jest sesja porównywana.

Lokalizator najpierw korzysta z aktualnego trwałego indeksu wyszukiwania. Gdy indeks nie jest gotowy, wykonuje anulowalne, pasywne wyszukiwanie w tle po niezmiennej sesji.

### Zachowanie okna na Windows

Okno porównania jest niezależnym, niemodalnym oknem roboczym bez właściciela głównego okna CRT.

Po poprawnym otwarciu dowodu:

- okno porównania pozostaje dostępne,
- zostaje zminimalizowane,
- główne CRT przejmuje fokus,
- sesja i ramka stają się widoczne dla użytkownika.

Ponowne wybranie analizy tego samego zestawu aktywuje istniejącą instancję okna zamiast tworzyć duplikat.

## Walidacja

### Potwierdzenie ręczne

Właściciel projektu potwierdził ręcznie działanie końcowego przepływu:

`dashboard → Otwórz dowody → główne CRT → właściwa zapisana sesja → właściwa ramka`.

Potwierdzono również, że okno porównania nie zamyka się i nie zasłania otwartej sesji.

### Testy automatyczne dodane w etapie

Dodano między innymi:

- `tests/test_comparison_evidence.py`,
- `tests_gui/comparison_visualization_smoke.py`,
- `tests_gui/comparison_visualization_navigation_smoke.py`.

Testy obejmują:

- parser pełnego klucza wiadomości,
- lokalizację przez trwały indeks i fallback strumieniowy,
- rozróżnianie STD/EXT oraz data/remote/error,
- filtrowanie pełnego wyniku,
- sortowanie przed stronicowaniem,
- wybór sesji bazowej dla brakującego ID,
- trwałe niemodalne okno porównania,
- przekazanie żądania do głównego shell,
- otwarcie sesji i zaznaczenie ramki.

### Stan CI przy sporządzaniu raportu

Dla funkcjonalnego checkpointu `6564446915d1a27ffe73ac4d2c23a5cf9969a995`:

- Windows GitHub-Hosted CI: sukces,
- Tests: oczekuje w kolejce,
- GUI Regressions: oczekuje w kolejce,
- Live Preview Capacity: oczekuje w kolejce,
- Windows Self-Hosted CI: oczekuje w kolejce.

Nie należy uznawać pełnej walidacji CI za zakończoną, dopóki wszystkie wymagane workflowy nie zakończą się sukcesem.

## Zachowane kontrakty architektoniczne

Etap nie zmienił:

- `CaptureService`,
- backendu Kvaser,
- lifecycle CANlib,
- kodu CAN TX/RX,
- formatu sesji,
- kolejności i kompletności pełnego zapisu surowych ramek,
- schematu trwałych indeksów,
- bounded/stronicowanego modelu zapisanych sesji,
- schematu `.crt/project.sqlite`,
- istniejących formatów artefaktów providerów.

## Znane ograniczenia

- Dashboard prezentuje najnowszy artefakt danego typu; nie jest jeszcze przeglądarką pełnej historii wersji artefaktów.
- Heatmapa i ranking są podsumowaniami Top, nie pełnymi wykresami wszystkich rekordów.
- Nie ma jeszcze wspólnej osi czasu wielu sesji ani synchronizacji względem znacznika.
- Nawigacja prowadzi do pierwszej pasującej ramki dla klucza wiadomości; nie ma jeszcze listy wszystkich wystąpień ani przechodzenia poprzedni/następny.

## Rekomendowany checkpoint

Po zakończeniu wszystkich workflowów CI należy:

1. sprawdzić review Copilota i nierozwiązane wątki,
2. poprawić ewentualne regresje,
3. wykonać końcowy commit i push raportów,
4. dopiero po wyraźnym poleceniu właściciela oznaczyć PR jako ready lub wykonać merge.

## Następny logiczny etap

Rekomendowany następny etap to `Comparison Visualization Stage 2 — analiza czasowa`, obejmujący:

- wspólną oś czasu sesji,
- synchronizację względem znacznika lub zdarzenia,
- porównanie kolejności komunikatów,
- różnice czasu odpowiedzi i opóźnień,
- nawigację z punktu osi czasu do ramki źródłowej.
