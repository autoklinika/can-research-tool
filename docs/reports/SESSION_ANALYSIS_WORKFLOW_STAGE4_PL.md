# CRT — uruchamianie analiz zapisanej sesji i trwałe artefakty — Stage 4

## 1. Cel etapu

Etap 4 podłącza pierwszy rzeczywisty provider analityczny do przepływu aplikacji CRT.
Użytkownik może uruchomić analizę dla zapisanej sesji, obserwować postęp, anulować
zadanie oraz przeglądać trwałe artefakty po ponownym otwarciu projektu.

Logika algorytmu nadal pozostaje całkowicie poza GUI. Widok korzysta z
`SessionAnalysisService`, który składa kontrakty Extension API i uruchamia provider
przez `ExtensionRunner`.

## 2. Zakres implementacji

### 2.1. Warstwa aplikacyjna

Dodano `app/session_analysis_service.py`:

- tworzenie pasywnego `ExtensionRegistry`,
- jawna rejestracja zaufanych providerów built-in,
- lista analiz obsługujących wejście `session`,
- walidacja sesji i manifestu providera,
- utworzenie wersjonowanego `AnalysisRun`,
- złożenie `AnalysisContext`, `ProjectContext`, `ArtifactWriter` i `FindingWriter`,
- wykonanie przez `ExtensionRunner`,
- zwrot identyfikatora runu i zapisanych artefaktów.

GUI nie tworzy ręcznie kontekstu providera i nie zna struktury `project.sqlite`.

### 2.2. Katalog artefaktów

Dodano `app/artifact_catalog.py` jako read-only API do:

- listowania artefaktów powiązanych z konkretną sesją,
- odczytu źródeł i wersji artefaktu,
- bezpiecznego rozwiązania ścieżki wewnątrz projektu,
- kontroli obecności pliku,
- kontroli limitu rozmiaru podglądu,
- weryfikacji SHA-256,
- odczytu UTF-8 JSON z obiektem jako elementem głównym.

Uszkodzenie, ręczna modyfikacja lub brak pliku są zgłaszane jako
`ArtifactIntegrityError` i nie wpływają na pliki sesji.

### 2.3. Zakładka Analizy

Zapisana sesja otrzymała zakładkę `Analizy`, zawierającą:

- listę providerów dostarczaną przez Extension Registry,
- przycisk `Uruchom`,
- przycisk `Anuluj`,
- pasek postępu i stan zadania,
- tabelę trwałych artefaktów,
- podgląd metadanych, wersji, SHA-256 i źródeł,
- czytelne podsumowanie artefaktu statystyk sesji.

Lista providerów nie jest zakodowana jako osobny zestaw przycisków w GUI.
Dodanie kolejnego providera przyjmującego `session` może udostępnić go w tym samym
mechanizmie po jawnej rejestracji.

### 2.4. Wykonanie poza GUI

`SessionAnalysisTask` działa jako `QRunnable` w `QThreadPool`.

- odczyt całej sesji nie blokuje wątku GUI,
- postęp jest przekazywany sygnałami Qt,
- anulowanie używa `CancellationToken`,
- wyjątek providera pozostaje odizolowany przez `ExtensionRunner`,
- zamknięcie zakładki żąda anulowania aktywnego zadania.

## 3. Przepływ danych

```text
zapisana sesja *.crt.jsonl (read-only)
        ↓
ProjectNavigator + kontekst CrtProject
        ↓
zakładka Analizy
        ↓
SessionAnalysisService
        ↓
ExtensionRegistry → ExtensionRunner → provider
        ↓
ArtifactWriter (atomowy zapis)
        ↓
artifacts/<analysis_run_id>/session-statistics.json
        ↓
ArtifactCatalog → tabela i podgląd GUI
```

## 4. Trwałość i pochodzenie

Każde wykonanie tworzy osobny `AnalysisRun` oraz nowy artefakt. Artefakt zachowuje:

- provider ID i provider version,
- algorithm version,
- artifact schema version,
- sesję źródłową,
- SHA-256 sesji zapisany w źródle artefaktu,
- SHA-256 pliku artefaktu,
- ścieżkę względną wewnątrz projektu.

Artefakty pozostają widoczne po zamknięciu i ponownym otwarciu sesji.

## 5. Zachowane granice bezpieczeństwa

Etap nie zmienia:

- `CaptureService`,
- backendu Kvaser,
- lifecycle CANlib,
- formatu `*.crt.jsonl`,
- formatu indeksu sesji,
- kolejności ani kompletności zapisu ramek,
- filtrowania Live i zapisanych sesji,
- dekodowania protokołów,
- działania widoku `Lista / Grupuj po ID`.

Provider otrzymuje wyłącznie read-only `SessionSource` i `FrameQuery`.
GUI nie otrzymuje API wysyłania CAN. AI pozostaje wyłączone.

## 6. Testy

### 6.1. Testy jednostkowe

`tests/test_session_analysis_service.py` sprawdza:

- odkrywanie built-in providera przez registry,
- pełny przebieg service → runner → artifact,
- postęp zadania,
- poprawność katalogu artefaktów,
- odczyt JSON i podstawowe wartości statystyk,
- status `completed` w `analysis_runs`,
- identyczny SHA-256 sesji przed i po analizie,
- wykrycie ręcznej modyfikacji artefaktu,
- odrzucenie nieznanej sesji.

### 6.2. Smoke GUI

`tests_gui/session_analysis_workflow_smoke.py` sprawdza rzeczywisty przepływ:

1. utworzenie projektu i zapisanej sesji,
2. otwarcie sesji przez `ProjectNavigator`,
3. przekazanie kontekstu projektu do widoku,
4. dostępność providera z registry,
5. uruchomienie analizy z GUI,
6. wykonanie poza wątkiem GUI,
7. utworzenie i prezentację artefaktu,
8. poprawne podsumowanie statystyk,
9. niezmienność SHA-256 sesji,
10. zamknięcie i ponowne otwarcie sesji,
11. trwałą obecność artefaktu po ponownym otwarciu.

Smoke jest wykonywany w `GUI Regressions` oraz pełnym
`Windows GitHub-Hosted CI`.

## 7. Poza zakresem

Etap nie dodaje jeszcze:

- analiz wielu sesji i comparison sets,
- wykresów częstotliwości lub jitteru,
- nawigacji z artefaktu do konkretnej ramki,
- automatycznych findings,
- CAN Intelligence,
- AI Provider,
- replay, scenariuszy aktywnych lub CAN TX,
- automatycznego uruchamiania analiz po zapisie sesji,
- dynamicznego instalowania rozszerzeń.

## 8. Następny logiczny etap

Po ręcznej walidacji interfejsu można rozwinąć artefakt statystyk o właściwy
inżynierski widok tabelaryczny per CAN ID: liczba ramek, częstotliwość, okres,
jitter, DLC i zakres czasu, z możliwością przejścia do ramek źródłowych. Nadal
powinien to być wyłącznie widok istniejącego, wersjonowanego artefaktu, bez
przenoszenia obliczeń do GUI.
