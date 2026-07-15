# Architektura CAN Research Tool

## Cel

CRT wspiera reverse engineering magistrali CAN: bezpieczne przechwytywanie materiału badawczego, rekonstrukcję warstw transportowych, analizę wiadomości oraz porównywanie sesji. Surowe ramki pozostają zawsze źródłem prawdy.

## Granice projektu

CRT nie importuje ekranów ECU Platform, profili konkretnych ECU ani gotowych procedur serwisowych. J1939, ISO-TP, UDS, DBC i protokoły autorskie są niezależnymi warstwami nad neutralnym modelem CAN.

## Przepływ danych podczas rejestracji

```text
KvaserPassiveChannel — wątek roboczy
        │
        ├── SessionStreamWriter ──► pełna sesja *.crt.jsonl
        │                             + rzadki indeks byte-offset
        │
        ├── FrameCsvStreamWriter ─► surowe *.frames.csv
        │
        ├── StreamingTransportPipeline
        │       ├── J1939 TP BAM / RTS-CTS
        │       ├── ISO-TP
        │       └── RAW fallback
        │                │
        │                ▼
        │          ProtocolRegistry
        │       ├── UDS
        │       ├── J1939 transport
        │       ├── reguły autorskie
        │       └── UNKNOWN
        │                │
        │                ├──► MessageCsvStreamWriter — neutralny zapis
        │                │
        │                ▼
        │       opcjonalna nakładka aktywnych DBC
        │                │
        │                ▼
        │       ograniczony podgląd wiadomości GUI
        │
        └── LiveFrameBuffer ──────► ograniczony podgląd ramek GUI
```

## Zasada stałego zużycia pamięci

Pełna sesja nie jest przechowywana przez GUI. `LiveFrameBuffer` zachowuje jedynie najnowsze ramki, domyślnie 20 000 rekordów, a bufor wiadomości logicznych 5 000 rekordów. Starsze dane pozostają bezpiecznie zapisane w sesji.

GUI pobiera migawki według numeru sekwencji. Gdy interfejs był zatrzymany zbyt długo i jego kursor wypadł poza bufor, bufor zwraca `truncated=True`. Model tabeli zastępuje wtedy swój widok aktualnym oknem zamiast próbować odtworzyć brakujące rekordy z RAM.

## Warstwy

### `kvaser/`

Adapter sprzętowy zna CANlib, kanały Kvaser i flagi ramek. Adapter nie udostępnia metod transmisji aplikacyjnej.

Tryby odbioru:

- `BENCH` — `Driver.NORMAL`, brak API TX w CRT, sprzętowy ACK aktywny;
- `LISTEN_ONLY` — `Driver.SILENT`, brak ACK; wymaga innego aktywnego węzła na magistrali.

### `app/session_stream.py`

- zapis JSONL ramka po ramce,
- okresowe opróżnianie bufora systemowego,
- stopka czystego zakończenia,
- rzadki indeks offsetów bajtowych,
- `SessionPagedReader` do odczytu wybranych zakresów,
- zgodność z wcześniejszym formatem sesji bez stopki i indeksu.

### `app/capture_service.py`

- posiada wątek roboczy odbioru,
- zapisuje dane bezpośrednio na dysk,
- publikuje postęp maksymalnie około 10 razy na sekundę,
- przekazuje ramki i wiadomości do buforów GUI paczkami,
- nie emituje sygnału GUI dla każdej ramki,
- utrzymuje transport pipeline pomiędzy kolejnymi ramkami.

### `app/transport.py` i `app/stream_pipeline.py`

Transport jest oddzielony od protokołu aplikacyjnego. 29-bitowy identyfikator nie oznacza automatycznie J1939. Rozpoznanie J1939 TP lub ISO-TP wymaga charakterystycznych ramek transportowych. Nierozpoznany ruch pozostaje `RAW`.

### `app/protocols.py`

Dekodery są uruchamiane po rekonstrukcji transportu. Brak dopasowania kończy się `UNKNOWN`, nigdy wymuszoną interpretacją. UDS i transportowane J1939 mają pierwszeństwo przed DBC.

### `app/dbc.py` i `app/project_dbc.py`

DBC jest zasobem projektu zarządzanym w zakładce `Dekodery`:

- import waliduje plik przez `cantools`,
- plik jest kopiowany do `decoders/dbc`,
- baza projektu zapisuje ścieżkę względną, SHA-256, liczbę wiadomości i stan aktywności,
- pierwszy aktywny plik ma deterministyczne pierwszeństwo przy kolizji CAN ID.

DBC działa jako odwracalna nakładka tylko na wiadomości `RAW`:

```text
zapisany RAW + aktywny DBC   → DBC message + signals
zapisany RAW + wyłączony DBC → bazowy UNKNOWN/proprietary
```

Przy otwieraniu zapisanej sesji wcześniejsza etykieta DBC nie jest traktowana jako aktualna prawda. Identyfikator i payload są ponownie interpretowane względem bieżącego zestawu aktywnych plików. Wyłączenie DBC nie wymaga modyfikacji sesji ani eksportu CSV.

Trwająca rejestracja zachowuje zestaw aktywnych DBC wybrany przy `Start`. Zmiany w zakładce `Dekodery` przeładowują zapisane sesje, ale nie zmieniają interpretacji w połowie eksperymentu.

### Znaczniki

Definicje znaczników są edytowane w osobnym oknie otwieranym z kafelka `Znaczniki` w sekcji `Połączenie i sesja`. Podczas rejestracji widoczne są tylko aktywne przyciski i skróty.

Timestamp znacznika i ramki korzysta z tego samego źródła `perf_counter_ns()`. Interfejs nadaje czas natychmiast, a zapis plikowy wykonuje się później w wątku roboczym.

### `gui/`

GUI używa Qt Widgets:

- `QTableView` + `QAbstractTableModel`, nigdy `QTableWidget`,
- aktualizacja tabel paczkami co 100 ms,
- ograniczona liczba wierszy,
- brak sortowania pełnej sesji w głównym wątku,
- pauza widoku niezależna od rejestracji,
- indeksowanie, otwieranie sesji i ponowna interpretacja DBC przez `QThreadPool`,
- ładowanie tylko ograniczonego okna danych.

## Reguły wydajności

1. Żadnej operacji plikowej, CAN ani analizy dużego zbioru w wątku GUI.
2. Żadnego sygnału Qt na pojedynczą ramkę.
3. Żadnej nieograniczonej listy ramek lub wiadomości w modelu tabeli.
4. Surowa sesja jest zapisywana przed prezentacją danych.
5. Filtry i porównania dużych sesji będą działały na indeksach i stronach danych.
6. Pauza interfejsu nie może zatrzymać zapisu ani transport pipeline.
7. Utrata rekordów z bufora widoku nie oznacza utraty danych sesji.
8. Wyłączenie dekodera nie może przepisywać materiału źródłowego.

## Następne warstwy

- filtry po CAN ID, protokole, PGN i kompletności,
- paginacja wiadomości zapisanych sesji,
- porównywanie dwóch sesji w wątku roboczym,
- edytor reguł protokołów autorskich,
- dekodery domenowe J1939 i UDS jako wtyczki.
