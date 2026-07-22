# Payload Difference Provider Stage 2 — plan implementacji

## Status dokumentu

Plan przygotowany po ręcznym potwierdzeniu działania `Comparison Statistics Provider Stage 1`.

Implementację Stage 2 należy rozpocząć dopiero po zielonym CI dla aktualnego HEAD PR #45 i na osobnej gałęzi stacked na `agent/comparison-statistics-provider-stage1`.

Proponowana gałąź:

`agent/comparison-payload-differences-stage2`

Proponowany draft PR powinien mieć bazę:

`agent/comparison-statistics-provider-stage1`

## Cel

Dodać drugi built-in provider typu `COMPARISON`, który porównuje warianty payloadów dla wspólnych kluczy wiadomości CAN w wielu zapisanych sesjach.

Provider ma odpowiedzieć na pytania:

- jakie pełne payloady występowały dla danego klucza wiadomości,
- które warianty występują we wszystkich sesjach, a które tylko w części,
- które pozycje bajtowe są stałe, zmienne albo nieobecne,
- jak zmienia się rozkład wartości bajtów względem sesji bazowej,
- które różnice są najbardziej użyteczne do dalszej analizy ECU.

Wynik ma być trwałym, deterministycznym i wersjonowanym artefaktem projektu z pełnym śladem źródłowym.

## Proponowany provider

- ID: `crt.comparison.payload_differences`
- typ rozszerzenia: `comparison`
- wersja providera: `1.0.0`
- wersja algorytmu: `1`
- input kind: `comparison_set`
- output kind: `payload_differences`
- nazwa pliku: `payload-differences.json`
- schemat: `crt.payload_differences`
- wersja schematu: `1`

Uprawnienia:

- `project.read`
- `session.read`
- `artifact.write`

Provider nie powinien tworzyć findings automatycznie. Wynik Stage 2 jest opisem różnic i materiałem wejściowym do późniejszych analiz hipotez.

## Model klucza wiadomości

Należy zachować identyczną semantykę klucza jak w Stage 1:

- kanał,
- arbitration ID,
- STD/EXT,
- data/RTR,
- error flag.

Payloady należy analizować wyłącznie dla ramek danych. Ramki RTR i error mogą zostać ujęte w metadanych klucza, ale nie wolno przypisywać im sztucznego payloadu.

Nie wolno scalać ramek wyłącznie po arbitration ID, jeżeli różnią się kanałem albo flagami.

## Zakres analizy

### Warianty pełnego payloadu

Dla każdego klucza wiadomości i każdej sesji provider powinien agregować:

- DLC lub rzeczywistą długość danych,
- payload jako stabilny zapis szesnastkowy,
- liczbę wystąpień,
- udział wariantu w ramach danego klucza i sesji,
- pierwszy oraz ostatni timestamp wystąpienia,
- SHA-256 reprezentacji wariantu opcjonalnie, jeżeli ułatwia stabilne odwołania.

Należy rozróżniać payloady o różnych długościach. Krótszego payloadu nie wolno dopełniać zerami.

### Obecność między sesjami

Dla każdego wariantu należy określić:

- sesje, w których wystąpił,
- sesje, w których nie wystąpił,
- rolę względem sesji bazowej:
  - `common`,
  - `baseline_only`,
  - `comparison_only`,
  - `subset_only`.

### Profil pozycji bajtowych

Dla każdej pozycji bajtowej należy policzyć osobno dla każdej sesji:

- liczbę ramek zawierających tę pozycję,
- zbiór obserwowanych wartości,
- liczbę wystąpień każdej wartości,
- wartość minimalną i maksymalną,
- najczęstszą wartość i jej udział,
- klasyfikację pozycji:
  - `absent`,
  - `constant`,
  - `variable`.

Porównanie względem bazy powinno wskazywać:

- zmianę wartości stałej,
- przejście `constant → variable`,
- przejście `variable → constant`,
- wartości nowe,
- wartości brakujące,
- zmianę dominującej wartości,
- zmianę udziału dominującej wartości.

### Ranking zmian

Provider powinien tworzyć ograniczony ranking istotnych różnic. Proponowane priorytety:

1. wariant obecny wyłącznie poza bazą,
2. wariant występujący wyłącznie w bazie,
3. zmiana stałej wartości bajtu,
4. przejście stały/zmienny,
5. nowe albo brakujące wartości pozycji,
6. duża zmiana udziału dominującej wartości,
7. pozostałe różnice rozkładu.

Ranking musi mieć jawne i stabilne reguły sortowania. Przy remisie należy sortować kolejno po:

- zapisanej kolejności sesji,
- kanale,
- arbitration ID,
- flagach klucza,
- pozycji bajtu,
- długości payloadu,
- payloadzie leksykograficznie.

Domyślny limit rankingu: `500`.

## Parametry Stage 2

Proponowane parametry wykonania:

- `max_ranked_changes`: domyślnie `500`, zakres `1..5000`,
- `max_variants_per_message`: domyślnie `1000`, zakres `1..100000`,
- `dominant_share_delta_threshold_pp`: domyślnie `5.0`,
- `include_complete_variant_matrix`: domyślnie `true`,
- `include_byte_histograms`: domyślnie `true`.

Każdy parametr musi być walidowany przed rozpoczęciem zapisu artefaktu. Błędne parametry powinny kończyć run statusem `failed` bez częściowego artefaktu.

Limit wariantów nie może prowadzić do cichego pominięcia danych. W razie przekroczenia provider powinien:

- oznaczyć klucz jako `truncated`,
- podać całkowitą liczbę unikalnych wariantów,
- podać regułę wyboru zachowanych wariantów,
- preferować stabilny ranking według liczby wystąpień, a następnie payloadu.

## Deterministyczność

Artefakt nie może zawierać:

- czasu uruchomienia,
- identyfikatora analysis run,
- losowych identyfikatorów,
- kolejności zależnej od słowników lub zbiorów,
- ścieżek absolutnych środowiska wykonawczego.

Dla identycznego projektu, zestawu, parametrów, źródeł i wersji algorytmu treść oraz SHA-256 artefaktu muszą być identyczne.

Każda kolekcja w JSON powinna mieć zdefiniowaną kolejność. Histograny wartości bajtów należy sortować numerycznie po wartości.

## Wydajność i pamięć

Analiza powinna być strumieniowa i nie może ładować pełnych sesji do pamięci.

Dopuszczalne jest utrzymywanie agregatów:

- per klucz wiadomości,
- per długość i payload,
- per pozycja bajtowa i wartość.

Należy jawnie uwzględnić ryzyko dużej liczby unikalnych payloadów. Implementacja powinna mieć kontrolowany limit i informację o truncation, zamiast nieograniczonego wzrostu pamięci.

Nie wolno zmieniać w tym celu formatu sesji, indeksów trwałych ani zapisu surowych ramek.

## Artefakt wynikowy

Proponowana struktura główna:

- `schema`
- `schema_version`
- `provider`
- `algorithm_version`
- `project_id`
- `comparison_set`
- `parameters`
- `sources`
- `summary`
- `message_payload_profiles`
- `ranked_changes`
- `truncation`

### `sources`

Dla każdej sesji:

- session ID,
- rola `baseline` albo `comparison`,
- pozycja w zestawie,
- frame count,
- SHA-256 pliku źródłowego,
- opcjonalnie zakres timestampów odczytany w trakcie agregacji.

### `summary`

Co najmniej:

- liczba sesji,
- efektywna baza,
- liczba kluczy wiadomości z payloadem,
- liczba wspólnych kluczy,
- liczba unikalnych wariantów payloadu,
- liczba zmian stałych bajtów,
- liczba przejść stały/zmienny,
- liczba nowych i brakujących wartości,
- liczba elementów rankingu,
- informacja o truncation.

### `message_payload_profiles`

Dla każdego klucza:

- stabilna reprezentacja klucza,
- profil każdej sesji,
- warianty payloadów,
- macierz obecności wariantów,
- profil pozycji bajtowych,
- porównania każdej sesji względem bazy,
- lokalne flagi truncation.

## GUI

Istniejący dialog analiz zestawu powinien pozostać wspólnym punktem uruchamiania providerów typu `COMPARISON`.

Stage 2 powinien dodać renderer artefaktu `payload_differences` bez rozbijania kontraktu Stage 1.

Minimalny widok:

- wybór providera `Payload differences`,
- podsumowanie sesji i liczby wariantów,
- lista kluczy wiadomości,
- filtr arbitration ID,
- tabela wariantów payloadu z obecnością per sesja,
- tabela pozycji bajtowych z klasyfikacją stała/zmienna,
- ranking najważniejszych zmian,
- jasna informacja o truncation,
- podgląd integralności i źródeł artefaktu.

Wykonanie musi pozostać asynchroniczne, z progressem i anulowaniem. Zamknięcie dialogu w trakcie run nie może pozostawiać aktywnego workera ani otwartego `project.sqlite`.

## Progres i anulowanie

Progres powinien mieć stabilne fazy:

1. walidacja zestawu i parametrów,
2. skan każdej sesji,
3. budowa porównań względem bazy,
4. ranking zmian,
5. serializacja i atomowy zapis artefaktu.

Anulowanie musi:

- być sprawdzane podczas skanowania ramek,
- przerwać analizę bez częściowego artefaktu,
- ustawić kontrolowany status run,
- zwolnić uchwyty do sesji i bazy projektu.

## Testy jednostkowe

Minimalny zestaw testów:

1. Rejestracja providera jako `COMPARISON`.
2. Dwa identyczne logi dają brak różnic i identyczny artefakt przy powtórzeniu.
3. Wariant występujący tylko w bazie.
4. Wariant występujący tylko w sesji porównawczej.
5. Wariant występujący w podzbiorze co najmniej trzech sesji.
6. Bajt stały o innej wartości między sesjami.
7. Przejście `constant → variable`.
8. Przejście `variable → constant`.
9. Różne długości payloadu bez dopełniania zerami.
10. Osobne klucze dla różnych kanałów i flag.
11. Stabilna kolejność wyników przy innym porządku wejściowych słowników.
12. Deterministyczna treść i SHA-256 dwóch runów.
13. Kompletne źródła i role sesji.
14. Brak zmiany SHA-256 plików sesji.
15. Brak zmiany schematu `.crt/project.sqlite`.
16. Kontrolowane przekroczenie limitu wariantów i jawne truncation.
17. Niepoprawne parametry kończą run jako failed bez artefaktu.
18. Anulowanie nie pozostawia częściowego artefaktu.
19. Odrzucenie trybu synchronizacji innego niż `none`.

## Smoke GUI

Smoke powinien potwierdzić:

- wybór nowego providera,
- uruchomienie w tle,
- zapis artefaktu,
- wyświetlenie listy kluczy,
- wyświetlenie wariantów i pozycji bajtowych,
- wyświetlenie rankingu,
- ponowne otwarcie zapisanego artefaktu,
- integralność sesji,
- blokadę zestawu,
- poprawny teardown workera i `project.sqlite` na Windows.

## Granice Stage 2

Stage 2 nie obejmuje:

- synchronizacji osi czasu,
- korelacji payloadów z markerami,
- automatycznego wykrywania sygnałów bitowych,
- endianess i skalowania sygnałów,
- DBC inference,
- dekodowania J1939/UDS,
- porównania sekwencji transportowych,
- klasyfikacji naprawy ECU jako udanej lub nieudanej,
- automatycznych findings.

Te funkcje wymagają osobnych providerów lub późniejszych etapów.

## Nienaruszalne kontrakty

Nie zmieniać:

- `CaptureService`,
- Kvasera,
- lifecycle CANlib,
- kodu CAN TX/RX,
- formatu sesji,
- kompletności i kolejności pełnego zapisu surowych ramek,
- trwałych indeksów wyszukiwania,
- schematu `.crt/project.sqlite`,
- kontraktów Project Properties,
- kontraktów Project Catalog,
- istniejących artefaktów `session-statistics.json` i `comparison-statistics.json`.

Surowe sesje pozostają niezmiennym źródłem prawdy. Provider może wyłącznie odczytywać źródła i zapisywać nowy artefakt poza katalogiem sesji.

## Warunki rozpoczęcia implementacji

Przed utworzeniem gałęzi Stage 2:

1. PR #45 musi mieć zielone wymagane CI dla aktualnego HEAD.
2. Należy potwierdzić brak nierozwiązanych review threads.
3. Należy zachować PR #45 jako draft, dopóki użytkownik nie poleci inaczej.
4. Nowa gałąź musi być stacked dokładnie na aktualnym HEAD PR #45.
5. Pierwszy commit Stage 2 powinien zawierać provider i testy rdzenia bez zmian GUI, a GUI powinno zostać dołączone po ustabilizowaniu artefaktu.

## Punkt kontrolny Stage 2

Na końcu etapu przygotować:

- commit,
- push,
- draft PR stacked na PR #45,
- raport implementacyjny,
- handoff do kolejnego czatu,
- pełną walidację GitHub Actions,
- ręczną listę akceptacyjną GUI.
