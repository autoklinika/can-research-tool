# Comparison Visualization Stage 2C2 — latencja i transakcje UDS

## Cel

Rozszerzyć pasywne porównywanie zapisanych sesji o deterministyczną analizę
transakcji UDS. Etap ma łączyć jawnie wskazane komunikaty request/response,
mierzyć osobno czas do pierwszej oraz końcowej odpowiedzi, obsługiwać
`0x78 ResponsePending`, klasyfikować brak odpowiedzi i zachowywać dokładne
ramki źródłowe każdej transakcji.

Stage 2C2 nie wysyła żadnych ramek CAN. Analizuje wyłącznie niezmienne,
zapisane sesje projektu.

## Zakres dostarczony

- nowa karta `Latencja UDS` w produkcyjnym oknie `Porównanie logów`,
- jawna konfiguracja dokładnego klucza wiadomości żądania i odpowiedzi,
- rekonstrukcja pojedynczych i wieloramkowych komunikatów przez istniejący
  `IsoTpReassembler`,
- deterministyczne parowanie FIFO według bazowego SID usługi,
- rozpoznawanie odpowiedzi pozytywnej `request SID + 0x40`,
- rozpoznawanie odpowiedzi negatywnej `0x7F requestSID NRC`,
- obsługa dowolnej liczby odpowiedzi `0x78 ResponsePending`,
- ponowne uruchomienie okna timeoutu po każdym `0x78`,
- osobna latencja pierwszej i końcowej odpowiedzi,
- timeout wyznaczany względem rzeczywistego końca surowej sesji,
- klasyfikacja żądań z flagą suppress-positive-response,
- wykrywanie odpowiedzi nieparowanych i niekompletnych komunikatów ISO-TP,
- percentyle i porównanie sesji względem bazy,
- trwały, wersjonowany artefakt,
- nawigacja do dokładnych ramek źródłowych.

## Konfiguracja

Analiza wymaga dwóch dokładnych kluczy w formacie używanym przez oś czasu:

`kanał:STD/EXT:CAN_ID:data`

Przykład dla normal-fixed UDS 29-bit:

- żądanie: `0:EXT:18DA30F9:data`,
- odpowiedź: `0:EXT:18DAF930:data`.

Przykład dla typowego UDS 11-bit:

- żądanie: `0:STD:7E0:data`,
- odpowiedź: `0:STD:7E8:data`.

Klucze muszą być różne i wskazywać ramki typu `data`. Timeout jest podawany w
milisekundach i oznacza maksymalny okres oczekiwania:

- od końca kompletnego żądania,
- albo od początku ostatniej odpowiedzi `0x78`.

Domyślny timeout wynosi 5000 ms.

## Rekonstrukcja ISO-TP

Stage 2C2 korzysta z istniejącego, konserwatywnego `IsoTpReassembler` CRT.
Obsługiwane są:

- Single Frame,
- First Frame i Consecutive Frame,
- standardowe identyfikatory diagnostyczne 11-bit,
- normal-fixed 29-bit z PF `0xDA` lub `0xDB`.

Flow Control nie jest traktowany jako komunikat UDS, ale nie przerywa aktywnej
rekonstrukcji właściwego kierunku. Dla komunikatu wieloramkowego artefakt
zachowuje pierwszy i ostatni `source_row` oraz liczbę ramek składowych.

Niekompletny komunikat ISO-TP nie uczestniczy w parowaniu; jest dokładnie
zliczany jako problem transportowy.

## Reguły parowania

Każde kompletne żądanie zawierające znany SID UDS otwiera oczekującą
transakcję. Odpowiedź jest dopasowywana do najstarszego oczekującego żądania o
tym samym bazowym SID, którego timestamp nie jest późniejszy od odpowiedzi.

Parowanie jest zatem:

- deterministyczne,
- FIFO,
- niezależne od wyglądu GUI,
- powtarzalne po ponownym uruchomieniu analizy.

Odpowiedź pozytywna ma SID równy `request SID + 0x40`. Odpowiedź negatywna ma
postać `0x7F requestSID NRC`.

### ResponsePending `0x78`

`0x7F requestSID 0x78` jest zapisywane jako pierwsza albo kolejna odpowiedź
pośrednia. Nie zamyka transakcji. Analizator:

1. zapisuje czas do pierwszej odpowiedzi, jeżeli jest to pierwszy komunikat
   odpowiedzi,
2. zwiększa dokładny licznik `0x78`,
3. zachowuje bounded listę ramek pending,
4. rozpoczyna nowe okno timeoutu,
5. czeka na odpowiedź końcową pozytywną albo negatywną.

### Suppress-positive-response

Dla usług posiadających subfunkcję analizowana jest flaga bitu 7 drugiego bajtu
żądania. Jeżeli ustawiono suppress-positive-response i nie wystąpiła żadna
odpowiedź, transakcja otrzymuje status `suppressed-no-response`, a nie timeout.
Odpowiedź negatywna nadal kończy taką transakcję normalnie.

## Klasyfikacja transakcji

Każde żądanie otrzymuje jeden status:

- `positive-response` — kompletna pozytywna odpowiedź końcowa,
- `negative-response` — kompletna negatywna odpowiedź końcowa,
- `timeout` — od żądania albo ostatniego `0x78` upłynął skonfigurowany czas,
- `capture-ended` — zapis sesji zakończył się przed upływem timeoutu,
- `suppressed-no-response` — brak odpowiedzi był zgodny z flagą suppress.

Odpowiedź bez pasującego żądania jest liczona jako `unmatched response` i
zachowywana w bounded liście diagnostycznej.

## Definicja latencji

Latencja jest liczona od końca kompletnego komunikatu żądania do początku
komunikatu odpowiedzi:

`latency = response.first_timestamp_ns - request.last_timestamp_ns`

Dzięki temu czas transmisji wieloramkowego żądania nie jest błędnie doliczany do
czasu reakcji ECU.

Wyznaczane są dwa rodzaje latencji:

- **first response latency** — do pierwszej odpowiedzi, w tym `0x78`,
- **final response latency** — do odpowiedzi końcowej pozytywnej albo negatywnej.

Dla każdej sesji obliczane są:

- średnia latencja pierwszej odpowiedzi,
- p50, p95 i p99 pierwszej odpowiedzi,
- średnia latencja końcowej odpowiedzi,
- p50, p95 i p99 końcowej odpowiedzi,
- liczba próbek wykorzystanych do percentyli.

Percentyle korzystają z deterministycznej próbki bounded, domyślnie do 100 000
wartości na sesję. Liczniki transakcji pozostają dokładne.

## Porównanie z sesją bazową

Dla każdej sesji niebazowej zapisywane są:

- zmiana skuteczności zakończenia transakcji w punktach procentowych,
- procentowa zmiana p50 pierwszej odpowiedzi,
- procentowa zmiana p50 końcowej odpowiedzi,
- procentowa zmiana p95 końcowej odpowiedzi,
- różnica liczby timeoutów,
- różnica liczby odpowiedzi negatywnych,
- różnica liczby `0x78`,
- różnica liczby nieparowanych odpowiedzi.

## Dowody i nawigacja

Każda zachowana transakcja zawiera:

- sesję i SID usługi,
- status,
- kompletne żądanie,
- pierwszą odpowiedź,
- odpowiedź końcową,
- bounded listę odpowiedzi pending,
- obie latencje,
- finalny NRC,
- informację suppress-positive-response.

Każdy komunikat dowodowy zawiera:

- pierwszy i ostatni `source_row`,
- pierwszy i ostatni timestamp,
- klucz wiadomości,
- payload,
- liczbę ramek transportowych,
- SID, NRC i nazwy protokołowe,
- kompletność transportu.

GUI umożliwia otwarcie:

- żądania,
- pierwszej odpowiedzi,
- odpowiedzi końcowej.

Nawigacja przekazuje istniejącemu navigatorowi dokładny `source_row`; nie
wyszukuje ponownie ramki po ID ani payloadzie.

## Bounded model

Domyślnie przechowywane jest maksymalnie 2000 transakcji dowodowych na sesję.
Priorytet zachowania mają:

1. timeouty,
2. transakcje przerwane końcem logu,
3. odpowiedzi negatywne,
4. transakcje zawierające `0x78`,
5. najdłuższe latencje.

Dokładne liczniki i percentyle nie zależą od liczby zachowanych wierszy GUI.
Dla pojedynczej transakcji zachowywanych jest maksymalnie 16 ramek `0x78`, przy
jednoczesnym dokładnym liczniku wszystkich odpowiedzi pending.

## Trwały artefakt

- typ: `comparison_uds_latency`,
- schemat: `crt.comparison_uds_latency`,
- wersja schematu: 1,
- provider: `crt.comparison.uds_latency`,
- wersja algorytmu: 1.

Artefakt przechowuje konfigurację, fingerprinty sesji, statystyki, porównania,
transakcje dowodowe, nieparowane odpowiedzi i ostrzeżenia.

Zgodność jest sprawdzana przez:

- identyfikator zestawu,
- identyfikatory i kolejność sesji,
- `frame_count`,
- SHA-256.

Zapis korzysta z istniejącego `ArtifactWriter` oraz `source_kind="session"`.
Nie dodano tabeli, migracji ani zmiany schematu `.crt/project.sqlite`.

## GUI

Karta `Latencja UDS` zawiera:

- klucz żądania,
- klucz odpowiedzi,
- timeout,
- `Analizuj transakcje UDS`,
- `Wczytaj ostatni`,
- `Anuluj`,
- tabelę statystyk sesji,
- tabelę zmian względem bazy,
- tabelę transakcji dowodowych,
- przyciski nawigacji do trzech punktów transakcji.

Po ponownym otwarciu okna najnowszy zgodny artefakt jest automatycznie
odtwarzany bez skanowania sesji.

## Testy automatyczne

Dodano:

- `tests/test_comparison_uds_latency.py`,
- `tests_gui/comparison_uds_latency_smoke.py`,
- workflow `Comparison UDS Latency Stage 2C2 Validation` dla Ubuntu i Windows.

Testy obejmują:

- odpowiedź pozytywną,
- odpowiedź negatywną i NRC,
- pierwszą odpowiedź `0x78` oraz późniejszą odpowiedź końcową,
- timeout względem rzeczywistego końca logu,
- suppress-positive-response,
- odpowiedź wieloramkową ISO-TP,
- dokładny pierwszy i ostatni `source_row`,
- odpowiedź nieparowaną,
- porównanie z bazą,
- round-trip artefaktu,
- odrzucenie zmienionego fingerprintu,
- integrację karty z produkcyjnym dialogiem,
- zapis i automatyczne odtworzenie bez skanowania,
- nawigację do żądania, pierwszej i końcowej odpowiedzi.

## Walidacja funkcjonalnego checkpointu

Funkcjonalny checkpoint:

`eef6dc8872838447707aaad808df843a87e52667`

Dla tego commitu zakończyły się sukcesem:

- dedykowany Stage 2C2 — Ubuntu i Windows, compile, rdzeń, artefakt i GUI,
- pełny `pytest`,
- Windows GitHub-hosted CI,
- GUI Regressions,
- Comparison Dashboard Validation,
- Comparison Timeline Validation,
- Comparison Timeline Stage 2B Validation,
- Comparison Inter-Frame Timing Stage 2C1 Validation,
- Live Preview Capacity.

Ogólny job `Tests/gui-smoke` może kończyć się niezależnie dłużej niż dedykowane
smoki. Self-hosted Windows nie jest wymagany, ponieważ etap nie używa Kvasera,
CANlib ani sprzętu CAN.

Pierwsza walidacja wykryła, że timeout był oceniany względem ostatniego
komunikatu UDS zamiast rzeczywistego końca logu. Poprawka pobiera ostatnią ramkę
przez istniejący indeks stronicowany i nie wykonuje drugiego pełnego skanowania.

## Potwierdzenie ręczne

Dnia 2026-07-27 właściciel projektu uruchomił Stage 2C2 na Windows i potwierdził
pełny przepływ:

`analiza transakcji UDS → parowanie request/response → statystyki first/final latency → nawigacja do żądania i odpowiedzi → zapis artefaktu → ponowne otwarcie bez skanowania`

Potwierdzono działanie produkcyjnej karty `Latencja UDS`, poprawne przejście do
dokładnych ramek dowodowych oraz automatyczne odtworzenie trwałego artefaktu.
Stage 2C2 jest ręcznie zaakceptowany jako funkcjonalny checkpoint do dalszego
rozwoju stacked.

## Zachowane kontrakty

Bez zmian pozostają:

- `CaptureService`,
- backend Kvaser i lifecycle CANlib,
- CAN TX/RX,
- format sesji i markerów,
- kolejność i kompletność pełnego zapisu surowych ramek,
- schemat trwałych indeksów,
- bounded/stronicowany model zapisanych sesji,
- schemat `.crt/project.sqlite`,
- artefakty wcześniejszych etapów porównania.

## Świadomie poza zakresem Stage 2C2

- aktywne wysyłanie żądań UDS,
- automatyczne wykrywanie par identyfikatorów request/response,
- automatyczne rozdzielanie wielu ECU odpowiadających na request funkcjonalny,
- korelacja odpowiedzi na podstawie DID, subfunkcji lub parametrów usługi,
- własna obsługa niestandardowego adresowania ISO-TP,
- analiza DoIP,
- rekonstruowanie aplikacyjnego znaczenia payloadu odpowiedzi.
