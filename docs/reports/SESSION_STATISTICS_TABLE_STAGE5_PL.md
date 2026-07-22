# CRT — Stage 5: tabelaryczny widok statystyk per CAN ID

## Cel

Rozszerzyć działającą zakładkę `Analizy` o inżynierski, sortowalny i filtrowalny widok statystyk per CAN ID, bez przenoszenia obliczeń do GUI i bez zmiany istniejącego artefaktu `crt.session_statistics`.

Stage 5 jest warstwą prezentacyjną nad trwałym, wersjonowanym artefaktem utworzonym w Stage 3 i uruchamianym z GUI od Stage 4.

## Założenie wizualne

Ręczna walidacja Stage 4 potwierdziła, że operatorowi odpowiada obecny podział ekranu:

- katalog artefaktów po lewej,
- szczegóły wybranego artefaktu po prawej,
- zwarte sterowanie analizą nad obszarem roboczym.

Stage 5 zachowuje ten układ. Prawy panel otrzymuje dwie karty:

- `Podsumowanie` — dotychczasowy tekstowy opis artefaktu,
- `Statystyki CAN ID` — nowy widok tabelaryczny.

Dzięki temu lista artefaktów i ich kontekst pozostają widoczne, a rozbudowane dane nie wypierają prostego podsumowania.

## Implementacja

### `gui/session_statistics_table_view.py`

Nowy moduł zawiera:

- `SessionMessageStatistics` — niemutowalny model jednego klucza wiadomości z artefaktu,
- `SessionStatisticsTableModel` — model Qt dla tabeli,
- `SessionStatisticsTableSessionViewWidget` — rozszerzenie działającego widoku analiz.

GUI nie odczytuje sesji `*.crt.jsonl` i nie wykonuje ponownie statystyk. Dane są pobierane wyłącznie przez read-only `ArtifactCatalog`, który wcześniej weryfikuje ścieżkę, rozmiar i SHA-256 artefaktu.

### Zachowany układ

Istniejący `QSplitter` nadal zawiera:

1. tabelę katalogu artefaktów po lewej,
2. panel interpretacji wybranego artefaktu po prawej.

Dotychczasowy `QPlainTextEdit` z podsumowaniem zostaje przeniesiony do karty `Podsumowanie`. Obok dodawana jest karta `Statystyki CAN ID`.

### Kolumny tabeli

Tabela prezentuje:

- kanał,
- CAN ID,
- format `STD/EXT`,
- typ `DATA/RTR/ERROR`,
- liczbę ramek,
- udział w całej sesji,
- liczbę bajtów payloadu,
- zakres DLC,
- średni okres,
- średnią częstotliwość,
- jitter jako odchylenie standardowe okresu,
- minimalny i maksymalny okres,
- liczbę zerowych i ujemnych różnic timestampów.

Tooltip wiersza zawiera również zakres `source_row`, który w przyszłości może zostać wykorzystany do nawigacji z analizy do ramek źródłowych.

## Interakcje

Operator może:

- sortować po każdej kolumnie,
- filtrować po CAN ID w zapisie hex lub decimal,
- filtrować po `DATA`, `RTR`, `ERROR`, `STD` lub `EXT`,
- ograniczyć widok do jednego kanału,
- wrócić do karty `Podsumowanie` bez utraty wyboru artefaktu.

Domyślne sortowanie jest malejące według liczby ramek. Brakujące wartości czasowe są zawsze umieszczane na końcu, również przy sortowaniu malejącym.

## Integralność danych

Stage 5 nie zmienia:

- providera `crt.analysis.session_statistics`,
- schematu artefaktu,
- algorytmu statystyk,
- plików sesji,
- indeksów sesji,
- `CaptureService`,
- Kvasera,
- lifecycle CANlib,
- Live Capture,
- filtrów i dekoderów.

Wszystkie wartości w tabeli są wyłącznie interpretacją danych już zapisanych w artefakcie.

## Test regresyjny

`tests_gui/session_statistics_table_smoke.py` tworzy projekt z sesją zawierającą:

- trzy klucze wiadomości,
- dwa kanały,
- ramki STD i EXT,
- różne liczby ramek i częstotliwości.

Smoke sprawdza:

- zachowanie dwóch kart `Podsumowanie` i `Statystyki CAN ID`,
- zachowanie dotychczasowego tekstowego podsumowania,
- liczbę i kolejność wierszy,
- liczbę kolumn,
- filtrowanie po CAN ID,
- filtrowanie po kanale,
- sortowanie po częstotliwości,
- ponowne otwarcie gotowego artefaktu,
- identyczny SHA-256 sesji przed analizą i po wszystkich operacjach GUI.

Test jest uruchamiany w:

- `GUI Regressions` na GitHub-hosted Linux,
- pełnym `Windows GitHub-Hosted CI`.

## Poza zakresem

Stage 5 nie dodaje jeszcze:

- wykresów czasowych,
- histogramów okresu i jitteru,
- udziału ruchu w formie wykresu,
- wyboru zakresu czasowego,
- nawigacji z wiersza do pierwszej lub ostatniej ramki,
- comparison sets,
- findings i CAN Intelligence,
- AI,
- CAN TX i funkcji aktywnych.

Te elementy mogą zostać dodane później jako kolejne widoki tego samego, wersjonowanego artefaktu albo jako osobne providery analityczne.

## Kryteria zakończenia

Stage 5 jest zakończony, gdy:

- aplikacja zachowuje wizualny układ zaakceptowany w Stage 4,
- tabela statystyk działa dla istniejących artefaktów,
- sortowanie i filtry działają bez odczytu surowej sesji,
- ponowne otwarcie sesji odtwarza tabelę,
- sesja źródłowa pozostaje bitowo niezmieniona,
- wszystkie GitHub-hosted workflow kończą się sukcesem,
- wygląd i ergonomia zostaną ręcznie potwierdzone na Windows.
