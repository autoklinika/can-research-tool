# Comparison Visualization Stage 2B — trwałe wyrównania i kotwice zdarzeń

## Cel

Rozszerzyć fundament osi czasu Stage 2A o wersjonowane, trwałe wyrównania oraz
kotwice zdarzeń, które można ponownie otworzyć bez skanowania źródłowych sesji.

## Zakres dostarczony

- artefakt `comparison_timeline_alignment` ze schematem
  `crt.comparison_timeline_alignment` w wersji 1,
- zapis kompletnego, bounded modelu osi czasu wraz z maksymalnie 2000 punktów
  na sesję,
- automatyczne wczytanie najnowszego zgodnego artefaktu po otwarciu okna,
- walidacja identyfikatorów sesji, liczby ramek oraz SHA-256,
- pomijanie uszkodzonych i niezgodnych artefaktów,
- zapis i odczyt poza wątkiem GUI,
- brak ponownego skanowania ramek przy odtwarzaniu artefaktu,
- wersjonowany analysis run i źródła artefaktu bez zmiany schematu SQLite.

## Tryby synchronizacji

### Początek sesji

Pierwsza ramka każdej sesji jest punktem `t = 0`.

### N-te wystąpienie dokładnego klucza wiadomości

Kotwica obejmuje kanał, STD/EXT, CAN ID oraz typ ramki. Stage 2B pozwala wybrać
numer wystąpienia, a nie tylko pierwsze wystąpienie.

### N-ty znacznik operatora

Wyrównanie wykorzystuje dokładną nazwę znacznika zapisanego w strumieniu
markerów sesji. Czas znacznika jest rzeczywistym `t = 0`, natomiast do
nawigacji zachowywana jest najbliższa ramka źródłowa.

### Wybrane dokładne zdarzenia

Użytkownik może kliknąć punkt istniejącej osi i przypisać jego `source_row` jako
kotwicę danej sesji. Ten tryb zapewnia ogólny kontrakt dla ręcznie wskazanych
zdarzeń protokołu oraz przyszłych wyników analiz automatycznych.

## Trwały artefakt

Artefakt przechowuje:

- konfigurację synchronizacji,
- kolejność i fingerprinty sesji,
- ostrzeżenia,
- zakres względnego czasu,
- dokładne dane kotwic każdej sesji,
- bounded listę zdarzeń z `source_row`, timestampem, sekwencją, kluczem
  wiadomości, DLC i payloadem.

Artefakt jest zapisywany przez `ArtifactWriter` w katalogu projektu i
rejestrowany w istniejącym katalogu analiz. Nie wprowadzono nowej tabeli ani
migracji `.crt/project.sqlite`.

## GUI

Karta `Oś czasu` zawiera teraz:

- wybór czterech trybów synchronizacji,
- numer wystąpienia klucza lub znacznika,
- przycisk `Ustaw jako kotwicę sesji`,
- podsumowanie liczby ustawionych dokładnych kotwic,
- `Zapisz wyrównanie`,
- `Wczytaj zapisane`,
- automatyczne wczytywanie po otwarciu okna,
- wyróżnienie punktu kotwicy na wykresie.

## Bezpieczeństwo i wydajność

- skanowanie sesji pozostaje pasywne i anulowalne,
- zapis oraz odczyt artefaktu odbywają się w `QThreadPool`,
- GUI nie materializuje pełnej sesji,
- odtworzenie artefaktu nie otwiera strumienia ramek,
- nie jest wykonywana transmisja CAN,
- źródłowe sesje i markery nie są modyfikowane.

## Testy

Dodano lub rozszerzono:

- `tests/test_comparison_timeline.py`,
- `tests/test_comparison_timeline_artifacts.py`,
- `tests_gui/comparison_timeline_smoke.py`,
- workflow `Comparison Timeline Stage 2B Validation` na Ubuntu i Windows.

Testy obejmują:

- zachowanie początku i końca próbki,
- N-te wystąpienie klucza wiadomości,
- dokładny czas znacznika i najbliższy `source_row`,
- jawny brak znacznika,
- dokładne kotwice per sesja,
- round-trip artefaktu,
- odrzucenie zmienionego fingerprintu,
- pominięcie uszkodzonego nowszego artefaktu,
- zapis, zamknięcie i ponowne otwarcie osi bez skanowania,
- pełną nawigację do dokładnej ramki źródłowej.

## Zachowane kontrakty

Bez zmian pozostają:

- `CaptureService`,
- backend Kvaser i lifecycle CANlib,
- CAN TX/RX,
- format sesji,
- kolejność i kompletność pełnego zapisu surowych ramek,
- format strumienia markerów,
- schemat trwałych indeksów,
- bounded/stronicowany model zapisanych sesji,
- schemat `.crt/project.sqlite`,
- dotychczasowe artefakty analiz porównawczych.

## Świadomie poza zakresem Stage 2B

- automatyczne rozpoznawanie transakcji UDS,
- obliczanie jitteru i rozkładów odstępów międzyramkowych,
- pomiar request/response latency,
- porównanie czasów odpowiedzi UDS,
- agregacja punktów zależna od zoomu,
- automatyczna korelacja semantycznych zdarzeń z wielu providerów.
