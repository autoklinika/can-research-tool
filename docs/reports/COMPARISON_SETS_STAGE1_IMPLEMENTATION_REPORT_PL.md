# Comparison Sets Stage 1 — raport implementacyjny

## 1. Status dokumentu

Comparison Sets Stage 1 został zaimplementowany funkcjonalnie na osobnej gałęzi stacked, ale nie został jeszcze ręcznie zaakceptowany ani oznaczony jako gotowy do review.

Aktualny stan przy utworzeniu raportu:

- repozytorium: `autoklinika/can-research-tool`,
- gałąź bazowa: `agent/project-catalog-stage1`,
- bazowy commit Project Catalog Stage 1: `62b357795ce392c18a88554a0966c46492706beb`,
- gałąź etapu: `agent/comparison-sets-stage1`,
- PR: `#44`,
- PR pozostaje draftem,
- GitHub Actions dla aktualnego HEAD pozostają w kolejce,
- ręczna walidacja GUI pozostaje do wykonania.

Nie należy oznaczać PR #44 jako Ready for review ani wykonywać merge bez osobnej decyzji użytkownika.

## 2. Dlaczego ten etap jest kolejnym logicznym krokiem

Master Plan wymaga, aby projekt CRT mógł trwale grupować wiele zapisanych sesji w zestawy porównawcze, wskazywać sesję bazową, a następnie przekazywać taki zestaw jako wejście wersjonowanych analiz.

Fundamenty potrzebne do tego etapu już istniały:

- model domenowy `ComparisonSet`,
- tabele `comparison_sets` i `comparison_set_sessions`,
- `analysis_inputs` obsługujące wejście `comparison_set`,
- Extension API i workflow analiz,
- trwałe statystyki pojedynczej sesji,
- Project Properties Stage 1,
- Project Catalog Stage 1.

Dlatego nie powtarzano implementacji modelu domenowego ani migracji. Dodano brakującą warstwę zarządzania zestawami w aplikacji.

## 3. Dostarczony zakres

### 3.1. Repozytorium zestawów

Dodano `app/comparison_sets.py` z `ComparisonSetStore`.

Obsługiwane operacje:

- utworzenie zestawu z co najmniej dwóch istniejących sesji,
- odczyt pojedynczego zestawu,
- lista zestawów,
- edycja nazwy, kolejności sesji, sesji bazowej i zapisanego trybu synchronizacji,
- usunięcie zestawu bez usuwania sesji,
- liczba uruchomień analiz używających zestawu,
- blokada modyfikacji i usuwania zestawu użytego przez analizę.

`ComparisonSetStore` korzysta z istniejącego `ProjectDomainStore` oraz istniejącego schematu domenowego w wersji 1. Nie dodano migracji ani tabel.

### 3.2. Bezpieczeństwo i powtarzalność analiz

Zestaw przechowuje wyłącznie identyfikatory istniejących sesji. Nie kopiuje i nie modyfikuje plików sesji.

Po użyciu zestawu jako wejścia `analysis_run` zestaw staje się niemutowalny. Operator musi utworzyć nowy zestaw, jeśli chce zmienić dobór sesji. Zapobiega to zmianie znaczenia już zapisanych wyników analizy.

Usunięcie zestawu usuwa wyłącznie rekord zestawu i jego relacje. Źródłowe sesje oraz surowe ramki pozostają bez zmian.

### 3.3. Widok GUI

Dodano zarządzany widok `Zestawy porównawcze`:

- tabela istniejących zestawów,
- nazwa,
- sesja bazowa,
- liczba sesji,
- zapisany tryb synchronizacji,
- stan edytowalny/zablokowany,
- data aktualizacji,
- tworzenie, edycja, usuwanie i odświeżanie,
- szczegóły wybranego zestawu,
- czytelna informacja o wymaganiu co najmniej dwóch sesji.

Dialog zestawu umożliwia:

- nadanie nazwy,
- wybór wielu sesji,
- wybór opcjonalnej sesji bazowej,
- zachowanie istniejącego trybu synchronizacji.

Comparison Sets Stage 1 nie uruchamia jeszcze algorytmu synchronizacji ani analizy porównawczej. Nowe zestawy używają trybu `none`.

### 3.4. Integracja z powłoką CRT

- akcja `Porównaj` otwiera rzeczywisty widok zamiast placeholdera,
- Explorer projektu zawiera sekcję `Zestawy porównawcze`,
- dwuklik sekcji otwiera menedżer,
- dwuklik konkretnego zestawu otwiera menedżer i zaznacza zestaw,
- Explorer odświeża się po utworzeniu, zmianie i usunięciu zestawu,
- otwarty widok odświeża listę sesji po zakończeniu importu.

Integrację wykonano przez nową końcową klasę powłoki `ComparisonSetsMainWindow`, pozostawiając kontrakty Project Properties i Project Catalog bez zmian.

## 4. Testy

Dodano:

- `tests/test_comparison_sets.py`,
- `tests_gui/comparison_sets_smoke.py`.

Testy jednostkowe sprawdzają:

- pełny CRUD,
- minimalną liczbę sesji,
- odrzucenie brakującej sesji,
- trwałość sesji bazowej i kolejności sesji,
- blokadę zestawu użytego przez analizę,
- brak zmiany wersji schematu,
- zachowanie rekordów sesji,
- identyczne SHA-256 plików sesji przed i po operacjach.

Smoke GUI sprawdza:

- działanie akcji `Porównaj`,
- otwarcie zarządzanego widoku,
- rzeczywiste zaakceptowanie modalnego dialogu tworzenia,
- zapis zestawu,
- obecność zestawu w Explorerze,
- otwarcie zestawu z Explorera,
- rzeczywistą edycję przez modalny dialog,
- stan zablokowany po utworzeniu analizy,
- niezmienność plików sesji,
- zwalnianie zasobów Qt i SQLite.

Workflowy GitHub Actions zostały rozszerzone wyłącznie o nowe testy etapu:

- GUI Regressions — test jednostkowy i smoke GUI,
- Windows GitHub-Hosted CI — smoke GUI; pełny `pytest` obejmuje test jednostkowy.

## 5. Zachowane kontrakty

Etap nie zmienia:

- `CaptureService`,
- backendu Kvaser,
- lifecycle CANlib,
- kodu CAN TX/RX,
- formatu sesji,
- kolejności pełnego zapisu surowych ramek,
- trwałych indeksów wyszukiwania,
- schematu `.crt/project.sqlite`,
- kontraktów Project Properties Stage 1,
- kontraktów Project Catalog Stage 1,
- istniejących providerów analiz,
- surowych danych źródłowych.

## 6. Stan stacked PR-ów

Aktualna zależność nowej warstwy:

`PR #44 Comparison Sets Stage 1`
→ `PR #43 Project Catalog Stage 1`
→ `PR #35 Project Properties Stage 1`
→ `PR #34 Minimal Analysis Chrome Stage 8`
→ wcześniejsze stacked PR-y.

Przed scaleniem należy zachować tę kolejność. PR #35 nadal jest draftem. Jeden wątek Copilota dotyczący martwych selektorów stylu jest formalnie nierozwiązany, mimo że aktualny diff usuwa wskazane selektory. Nie rozwiązano go automatycznie.

## 7. Ręczna walidacja do wykonania

Na projekcie zawierającym co najmniej trzy zapisane sesje:

1. Otworzyć projekt z katalogu CRT.
2. Uruchomić `Porównaj` z paska aktywności lub menu `Analiza`.
3. Utworzyć zestaw z dwóch sesji i wskazać jedną jako bazową.
4. Sprawdzić zapis w tabeli i w Explorerze projektu.
5. Zamknąć zakładkę i otworzyć zestaw dwuklikiem z Explorera.
6. Edytować zestaw, zmienić nazwę i dodać trzecią sesję.
7. Usunąć nieużywany zestaw i potwierdzić, że wszystkie sesje nadal istnieją i otwierają się poprawnie.
8. Zamknąć i ponownie otworzyć projekt, a następnie potwierdzić trwałość zestawu.
9. Potwierdzić, że Live Capture, zapis sesji, wyszukiwanie i Project Catalog działają bez regresji.

## 8. Następny etap po akceptacji

Po zaakceptowaniu Comparison Sets Stage 1 kolejnym logicznym etapem jest pierwszy deterministyczny provider porównawczy działający przez istniejące Extension API.

Rekomendowany zakres:

- wejście: `AnalysisInput(kind="comparison_set")`,
- wykorzystanie istniejących artefaktów statystyk CAN ID lub ich deterministyczne obliczenie,
- porównanie obecności ID, liczby ramek, częstotliwości i podstawowych zmian payloadu,
- osobne wyniki względem sesji bazowej,
- wersjonowany artefakt porównawczy,
- brak AI w pierwszej wersji,
- nawigacja z wyniku do źródłowych sesji i ramek przez trwałe referencje.

Najpierw należy jednak zakończyć CI i ręczną walidację PR #44.
