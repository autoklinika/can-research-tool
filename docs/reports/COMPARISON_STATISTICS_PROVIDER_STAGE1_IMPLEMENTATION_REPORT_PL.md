# Comparison Statistics Provider Stage 1 — raport implementacyjny

## Status

Etap implementacyjny został przygotowany na gałęzi:

`agent/comparison-statistics-provider-stage1`

Gałąź jest stacked na:

`agent/comparison-sets-stage1` — PR #44, baza `5f8522da066eedacfe9a1a237ddc5250a8e3c56b`.

PR tego etapu pozostaje draftem do czasu zakończenia GitHub Actions i ręcznej oceny widoku. Nie należy oznaczać go jako ready ani wykonywać merge bez wyraźnej decyzji użytkownika.

## Cel etapu

Dodać pierwszy rzeczywisty `Comparison Provider` zgodny z Master Planem CRT. Provider porównuje statystyki CAN ID dwóch lub większej liczby niezmiennych zapisanych sesji wskazanych przez trwały zestaw porównawczy.

Etap nie implementuje jeszcze porównania payloadów, protokołów ani synchronizacji osi czasu.

## Zakres funkcjonalny

### Provider

Dodano provider:

- ID: `crt.comparison.statistics`,
- typ rozszerzenia: `comparison`,
- wersja providera: `1.0.0`,
- wersja algorytmu: `1`,
- typ artefaktu: `comparison_statistics`,
- schemat artefaktu: `crt.comparison_statistics`, wersja `1`.

Provider:

- odczytuje wszystkie sesje zestawu w zapisanej kolejności,
- używa jawnej sesji bazowej lub pierwszej sesji jako efektywnej bazy,
- agreguje dane strumieniowo bez ładowania pełnych logów do pamięci,
- rozróżnia kanał, format STD/EXT oraz ramki data/RTR/error,
- wykrywa nowe, brakujące i wspólne klucze wiadomości,
- porównuje liczbę ramek i udział procentowy,
- porównuje średnią częstotliwość wyliczoną z dodatnich interwałów,
- wskazuje wzrosty i spadki przekraczające progi,
- tworzy deterministyczny artefakt JSON,
- zapisuje źródła, role sesji, SHA-256 i liczbę odczytanych ramek,
- nie tworzy automatycznych findings, ponieważ wynik jest statystyką opisową, a nie hipotezą.

Domyślne parametry:

- próg zmiany częstotliwości: `10%`,
- próg zmiany udziału: `0,5` punktu procentowego,
- limit rankingu istotnych zmian: `250`.

Provider Stage 1 jawnie odrzuca zestawy z trybem synchronizacji innym niż `none`, aby nie sugerować, że synchronizacja znacznikiem lub ręcznym punktem została już wykonana.

### Extension API

Rozszerzono stabilny fundament API o rzeczywisty kontrakt porównań:

- `ComparisonProvider`,
- `ExtensionRegistry.get_comparison()`,
- `ExtensionRunner.execute_comparison()`,
- `ComparisonContext` jako niezmienny snapshot zestawu,
- jawna rejestracja zaufanych providerów porównawczych.

Dotychczasowy kontrakt `AnalysisProvider`, `get_analysis()` i `execute_analysis()` pozostaje zachowany.

### Warstwa aplikacyjna

Dodano `ComparisonAnalysisService`, który:

- pobiera trwały zestaw porównawczy,
- łączy parametry zestawu z parametrami konkretnego uruchomienia,
- tworzy trwały `analysis_run` z wejściem `comparison_set`,
- przekazuje snapshot zestawu do providera,
- korzysta z istniejących `ArtifactWriter`, `ProjectDomainStore` i `ExtensionRunner`,
- udostępnia katalog artefaktów danego zestawu.

`ArtifactCatalog` otrzymał read-only zapytanie `list_for_comparison_set()` bez zmiany schematu bazy.

### GUI

Widok `Zestawy porównawcze` otrzymał akcję:

`Analizuj wybrany zestaw…`

Dialog analizy:

- pobiera listę providerów z rejestru,
- uruchamia analizę poza wątkiem GUI,
- pokazuje postęp i obsługuje anulowanie,
- prezentuje zapisane artefakty,
- pokazuje podsumowanie sesji,
- pokazuje tabelę nowych/brakujących ID oraz zmian częstotliwości i udziału,
- weryfikuje integralność JSON przez istniejący `ArtifactCatalog`,
- po wykonaniu blokuje edycję zestawu zgodnie z istniejącą zasadą powtarzalności.

## Artefakt wynikowy

`comparison-statistics.json` zawiera między innymi:

- identyfikator projektu i zestawu,
- wersje providera, algorytmu, API i schematu,
- parametry wykonania,
- kolejność sesji i efektywną bazę,
- tryb synchronizacji,
- metadane oraz SHA-256 każdej sesji,
- podsumowanie różnic względem bazy,
- pełną macierz kluczy wiadomości dla wszystkich sesji,
- ranking istotnych zmian,
- informację o ewentualnym skróceniu rankingu.

Artefakt nie zawiera czasu uruchomienia, identyfikatora run ani danych losowych. Dla tego samego projektu, zestawu, parametrów oraz wersji algorytmu jego treść i SHA-256 powinny być identyczne.

## Bezpieczeństwo i zachowane kontrakty

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
- providera `crt.analysis.session_statistics` ani jego artefaktu.

Provider ma wyłącznie uprawnienia:

- `project.read`,
- `session.read`,
- `artifact.write`.

Surowe sesje są wyłącznie odczytywane przez `SessionSource` i `FrameQuery`. Wynik jest zapisywany atomowo poza katalogiem sesji.

## Testy

Dodano testy jednostkowe obejmujące:

- rejestrację providera typu `comparison`,
- wybór jawnej i domyślnej sesji bazowej,
- wykrycie nowych i brakujących ID,
- zmianę częstotliwości `10 Hz → 20 Hz`,
- trwałość i deterministyczność artefaktu,
- kompletne źródła artefaktu,
- brak zmiany SHA-256 sesji,
- brak zmiany wersji schematu projektu,
- blokadę zestawu po uruchomieniu analizy,
- kontrolowane odrzucenie niepoprawnych parametrów,
- kontrolowane odrzucenie niezaimplementowanego trybu synchronizacji.

Dodano smoke GUI obejmujący:

- otwarcie dialogu analizy,
- uruchomienie providera w tle,
- zapis i ponowne wyświetlenie artefaktu,
- podsumowanie dwóch sesji,
- tabelę zmian,
- blokadę zestawu,
- integralność plików sesji,
- niezmienioną wersję schematu projektu.

Workflowy Linux i Windows zostały rozszerzone o nowe testy.

## Wykonana walidacja przed push

W środowisku roboczym wykonano:

- kompilację składniową wszystkich nowych i zmodyfikowanych plików Python przez `py_compile`,
- kontrolę długości linii względem limitu projektu `100`,
- niezależny test runtime rdzenia providera na dwóch syntetycznych sesjach, potwierdzający nowe/brakujące ID, zmianę `10 Hz → 20 Hz`, deterministyczne podsumowanie i progres.

Pełnego `pytest` i smoke Qt nie można było uruchomić w lokalnym kontenerze, ponieważ nie jest w nim dostępny checkout repozytorium ani PySide6. Źródłem pełnej walidacji pozostaje GitHub Actions po utworzeniu PR.

## Ręczna lista akceptacyjna

1. Utworzyć projekt z co najmniej dwiema zapisanymi sesjami.
2. Utworzyć zestaw porównawczy i wskazać sesję bazową.
3. Otworzyć `Zestawy porównawcze` i wybrać `Analizuj wybrany zestaw…`.
4. Uruchomić `CAN ID statistics comparison`.
5. Sprawdzić podsumowanie sesji i tabelę zmian.
6. Zamknąć i ponownie otworzyć dialog; artefakt musi pozostać dostępny.
7. Potwierdzić, że zestaw jest zablokowany, a sesje nadal otwierają się poprawnie.
8. Powtórzyć analizę i porównać SHA-256 artefaktów.

## Następny etap

Po akceptacji Stage 1 właściwym kolejnym krokiem jest `Payload Difference Provider Stage 2`:

- warianty payloadów dla wspólnych CAN ID,
- bajty stałe i zmienne,
- wartości obecne tylko w wybranych sesjach,
- deterministyczny artefakt z odwołaniem do sesji źródłowych.

Synchronizacja logów powinna pozostać osobnym etapem, ponieważ wymaga jawnego kontraktu punktów odniesienia i nie może być pozorowana przez prostą normalizację czasu.
