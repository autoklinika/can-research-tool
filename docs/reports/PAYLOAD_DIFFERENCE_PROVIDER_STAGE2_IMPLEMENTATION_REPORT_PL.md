# Payload Difference Provider Stage 2 — raport implementacyjny

## Status

Etap został zaimplementowany na gałęzi:

`agent/payload-difference-provider-stage2`

Gałąź jest stacked na:

`agent/comparison-statistics-provider-stage1` — draft PR #45, commit bazowy `12524adb8bbdd7286efaec3152584c5388b5a74c`.

Stage 2 powinien pozostać osobnym draft PR. Nie należy oznaczać PR jako ready ani wykonywać merge bez wyraźnej decyzji użytkownika.

## Cel etapu

Dodać drugi rzeczywisty provider typu `COMPARISON`, który porównuje pełne warianty payloadów oraz profile pozycji bajtowych dla wielu niezmiennych zapisanych sesji w trwałym zestawie porównawczym.

Etap rozwija analizę statystyczną CAN ID z Stage 1, ale nadal pozostaje analizą pasywną. Nie wysyła ramek CAN i nie modyfikuje sesji źródłowych.

## Kontrakt providera

Dodano provider:

- ID: `crt.comparison.payload_differences`,
- nazwa: `CAN payload differences`,
- typ rozszerzenia: `comparison`,
- wersja providera: `1.0.0`,
- wersja algorytmu: `1`,
- input kind: `comparison_set`,
- output kind: `payload_differences`,
- typ artefaktu: `payload_differences`,
- plik: `payload-differences.json`,
- schemat: `crt.payload_differences`,
- wersja schematu: `1`.

Provider ma wyłącznie uprawnienia:

- `project.read`,
- `session.read`,
- `artifact.write`.

Nie tworzy automatycznych findings. Wynik jest trwałym materiałem badawczym, a nie automatyczną oceną naprawy ECU.

## Model danych

### Klucz wiadomości

Zachowano semantykę Stage 1:

- kanał,
- arbitration ID,
- STD/EXT,
- data/RTR/error.

Payloady są agregowane wyłącznie dla ramek danych. Ramki RTR i error są pomijane przez analizę payloadu i liczone osobno jako pominięte ramki niedanych.

### Warianty payloadu

Dla każdego klucza wiadomości i każdej sesji zapisywane są:

- payload w stabilnej reprezentacji szesnastkowej,
- rzeczywista długość payloadu,
- liczba wystąpień,
- udział procentowy w ramach klucza i sesji,
- pierwszy timestamp,
- ostatni timestamp.

Payloady o różnych długościach pozostają różnymi wariantami. Dane nie są dopełniane zerami.

### Macierz obecności wariantów

Dla śledzonych wariantów tworzona jest deterministyczna macierz sesji z rolą:

- `common`,
- `baseline_only`,
- `comparison_only`,
- `subset_only`,
- `incomplete` — gdy limit wariantów uniemożliwia pełne porównanie.

Macierz zapisuje sesje, w których wariant wystąpił, oraz sesje, w których go nie odnotowano.

### Profil pozycji bajtowych

Dla każdej pozycji bajtu provider zapisuje:

- liczbę ramek zawierających pozycję,
- udział obecności pozycji,
- klasyfikację `absent`, `constant` albo `variable`,
- liczbę unikalnych wartości,
- wartość minimalną i maksymalną,
- dominantę,
- udział dominanty,
- deterministycznie posortowany histogram wartości.

Porównanie względem sesji bazowej wykrywa między innymi:

- zmianę wartości stałego bajtu,
- przejście `constant → variable`,
- przejście `variable → constant`,
- zmianę zbioru wartości,
- zmianę dominującej wartości,
- zmianę udziału dominanty,
- zmianę obecności pozycji,
- dodanie albo usunięcie pozycji bajtu,
- zmianę zestawu DLC.

## Ranking zmian

Artefakt zawiera ograniczony, stabilnie sortowany `ranked_changes`.

Priorytet obejmuje przede wszystkim:

1. nowe i brakujące warianty payloadu,
2. nowe i brakujące klucze wiadomości,
3. zmianę stałego bajtu,
4. przejścia stały/zmienny,
5. zmianę zbioru wartości,
6. zmianę dominanty,
7. zmianę DLC i obecności pozycji,
8. jawne ostrzeżenie o niepełnym porównaniu wariantów.

Przy remisach wynik jest sortowany według zapisanej kolejności sesji, typu zmiany, kanału, CAN ID, flag, indeksu bajtu, DLC i payloadu.

## Parametry

Obsługiwane parametry wykonania:

- `max_ranked_changes` — domyślnie `500`, zakres `1..5000`,
- `max_variants_per_message` — domyślnie `1000`, zakres `1..100000`,
- `dominant_share_delta_threshold_pp` — domyślnie `5.0`,
- `include_complete_variant_matrix` — domyślnie `true`,
- `include_byte_histograms` — domyślnie `true`,
- `minimum_message_frame_count` — domyślnie `1`.

Parametry są walidowane przed zapisem artefaktu. Niepoprawny parametr kończy uruchomienie statusem `failed` bez częściowego artefaktu.

## Kontrola pamięci i jawne ograniczenie wariantów

Analiza sesji jest strumieniowa i nie ładuje pełnych logów do pamięci.

Dla każdego klucza i sesji liczba przechowywanych pełnych wariantów payloadu jest ograniczona parametrem `max_variants_per_message`. Profil bajtowy pozostaje ograniczony naturalnie do maksymalnie 64 pozycji i 256 wartości na pozycję.

Po przekroczeniu limitu:

- kolejne nieśledzone wystąpienia są liczone,
- artefakt zapisuje `complete=false`, liczbę pominiętych wystąpień i regułę wyboru,
- macierz wariantów otrzymuje rolę `incomplete`,
- provider nie generuje `new_payload_variant` ani `missing_payload_variant` dla niepełnego porównania,
- zamiast tego emituje `variant_comparison_truncated`.

Zastosowana reguła jest deterministyczna i jednoprzebiegowa:

`first_observed_in_session_order`

Jest to świadome odstępstwo od opcjonalnej preferencji rankingu top-frequency z planu. Zachowuje ograniczoną pamięć i pojedynczy przebieg po dużych sesjach, a niepełność jest w pełni jawna w artefakcie.

## Deterministyczność

Artefakt nie zawiera:

- czasu wykonania,
- identyfikatora analysis run,
- losowych wartości,
- ścieżek absolutnych,
- kolejności zależnej od słowników lub zbiorów.

Warianty, histogramy, klucze, macierze i ranking mają zdefiniowaną kolejność. Dwa uruchomienia z tymi samymi źródłami, parametrami i wersją algorytmu powinny wygenerować identyczną treść i SHA-256.

## Źródła artefaktu

Każde źródło zapisuje:

- session ID,
- rolę `base` albo `comparison`,
- pozycję w zestawie,
- liczbę ramek odczytanych przez reader,
- liczbę ramek danych przeanalizowanych przez provider,
- SHA-256 sesji.

Sesje są otwierane wyłącznie przez istniejące read-only `SessionSource` i `FrameQuery`.

## GUI

Istniejący dialog `Analiza porównawcza` pozostaje wspólnym punktem uruchamiania providerów typu `COMPARISON`.

Dodano:

- drugi provider w selektorze analiz,
- renderer schematu `crt.payload_differences`,
- tabelę podsumowania sesji payloadowych,
- tabelę rankingu różnic,
- polskie etykiety typów zmian,
- prezentację bajtu bazowego i bieżącego,
- prezentację payloadu oraz zmian DLC,
- obsługę dominanty i klasyfikacji stały/zmienny.

Wykonanie nadal działa w tle przez istniejący worker, z progressem, anulowaniem i blokadą zamknięcia dialogu podczas aktywnego zadania.

## Testy

Dodano testy jednostkowe obejmujące:

- rejestrację drugiego providera typu `COMPARISON`,
- trwałość i deterministyczność dwóch uruchomień,
- nowe i brakujące klucze wiadomości,
- nowe i brakujące pełne warianty payloadu,
- zmianę stałego bajtu,
- zmianę zbioru wartości,
- przejście `constant → variable`,
- przejście `variable → constant`,
- macierz `baseline_only` i `comparison_only`,
- pierwszy i ostatni timestamp wariantu,
- źródła i role sesji,
- niezmienność SHA-256 plików sesji,
- niezmienioną wersję schematu projektu,
- blokadę użytego zestawu,
- jawne zachowanie po przekroczeniu limitu,
- brak fałszywych nowych/brakujących wariantów po truncation,
- kontrolowane odrzucenie niepoprawnego limitu.

Dodano smoke GUI obejmujący:

- dwa providery w selektorze,
- wybór `crt.comparison.payload_differences`,
- wykonanie w tle,
- trwały artefakt,
- tabelę sesji i tabelę zmian,
- integralność plików sesji,
- blokadę zestawu,
- niezmieniony schemat projektu,
- teardown workera i dialogu.

Smoke Stage 1 został zaktualizowany tak, aby potwierdzał zachowanie pierwszego providera przy obecności drugiego.

Workflowy Linux GUI oraz Windows GitHub-hosted zostały rozszerzone o testy Stage 2.

## Wykonana walidacja przed uruchomieniem CI

Wykonano:

- kompilację składniową rdzenia providera,
- kompilację składniową renderera GUI i testów,
- kontrolę długości linii względem limitu projektu,
- izolowany test runtime na dwóch syntetycznych sesjach,
- potwierdzenie nowych/brakujących kluczy i wariantów,
- potwierdzenie zmiany stałego bajtu oraz przejść stały/zmienny,
- potwierdzenie macierzy obecności wariantów,
- potwierdzenie końcowego progresu `17/17`,
- test limitu wariantów bez generowania fałszywych różnic.

Lokalny kontener nie ma dostępu sieciowego do checkoutu GitHub ani środowiska PySide6 repozytorium. Pełny pytest i smoke Qt pozostają zadaniem GitHub Actions po utworzeniu draft PR.

## Nienaruszone kontrakty

Etap nie zmienia:

- `CaptureService`,
- backendu Kvaser,
- lifecycle CANlib,
- kodu CAN TX/RX,
- formatu sesji,
- kolejności ani kompletności pełnego zapisu surowych ramek,
- trwałych indeksów wyszukiwania,
- schematu `.crt/project.sqlite`,
- kontraktów Project Properties,
- kontraktów Project Catalog,
- `session-statistics.json`,
- `comparison-statistics.json`.

## Ręczna lista akceptacyjna

1. Otworzyć projekt z co najmniej dwiema zapisanymi sesjami.
2. Utworzyć zestaw porównawczy z jawną sesją bazową.
3. Otworzyć `Zestawy porównawcze` i `Analizuj wybrany zestaw…`.
4. Sprawdzić obecność dwóch providerów.
5. Wybrać `CAN payload differences`.
6. Uruchomić analizę i sprawdzić progres.
7. Sprawdzić podsumowanie sesji i ranking zmian.
8. Zweryfikować zmianę stałego bajtu na znanym przykładzie.
9. Zamknąć i ponownie otworzyć dialog; artefakt musi pozostać dostępny.
10. Powtórzyć analizę i porównać SHA-256 artefaktów.
11. Potwierdzić, że sesje nadal otwierają się poprawnie.
12. Potwierdzić poprawny teardown dialogu na Windows.

## Następny etap

Po zielonym CI i ręcznej akceptacji Stage 2 właściwym dalszym krokiem jest osobny etap analizy sekwencji lub protokołów. Synchronizacja osi czasu nadal powinna pozostać oddzielnym kontraktem i nie może być pozorowana przez prostą normalizację timestampów.
