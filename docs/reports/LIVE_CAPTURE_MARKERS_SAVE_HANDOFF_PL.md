# CAN Research Tool — przekazanie zmian Live Capture, znaczników i zapisu logów

Data raportu: 2026-07-21

## 1. Punkt odniesienia

- repozytorium: `autoklinika/can-research-tool`
- aktywna gałąź: `agent/ui-engineering-shell-stage1`
- pull request: `#22` — **UI Stage 1 — engineering IDE shell**
- ostatni commit funkcjonalny przed dodaniem raportu:
  `5f4985df818fa4c22d92fa0a9c7ca701b57f56d7`
- uruchomienie aplikacji:
  `python -X faulthandler -u .\crt_gui.py`

Użytkownik ręcznie potwierdził działanie opisanego niżej przepływu.

## 2. Zakres wykonanych prac

W ramach tej serii zmian dopracowano:

- obsługę Start/Stop z klawiatury,
- prezentację i nawigację po znacznikach,
- osobne okno znaczników zapisanej sesji,
- opóźnioną analizę logiczną Live,
- tymczasowy zapis każdej rejestracji,
- jawne przenoszenie zakończonego logu do projektu,
- ochronę przed utratą niezapisanego logu,
- dwustopniowe rozpoczęcie kolejnej rejestracji,
- nadawanie nazwy dopiero podczas zapisu logu.

## 3. Live Capture — sterowanie

### 3.1. Start i Stop przez Spację

W zakładce Live:

- `Spacja` przy zatrzymanej rejestracji uruchamia Start,
- `Spacja` podczas aktywnej rejestracji uruchamia Stop,
- auto-repeat klawisza jest wyłączony,
- skrót nie przechwytuje spacji używanej w polach edycyjnych, listach wyboru,
  przyciskach i checkboxach.

### 3.2. Pole nazwy sesji

Pole `Nazwa sesji` zostało usunięte z interfejsu Live.

Podczas rejestracji używana jest wyłącznie techniczna nazwa tymczasowa:

```text
live_temp_YYYYMMDD_HHMMSS_microseconds
```

Operator nadaje właściwą nazwę dopiero podczas zapisu logu do projektu.

### 3.3. Przycisk konfiguracji znaczników

Przycisk konfiguracji ma zwarty, jednoliniowy format:

```text
Znaczniki: aktywne/wszystkie
```

Przykład:

```text
Znaczniki: 2/2
```

Rozwiązanie nie jest zależne od wysokości tekstu wieloliniowego ani skalowania Windows.

## 4. Znaczniki

### 4.1. Znaczniki podczas Live

W zakładce `Surowe ramki` pozostaje boczna lista `Znaczniki tej sesji`.

Dwuklik na znaczniku:

- pozostaje w bieżącym widoku Live,
- wyszukuje najbliższą ramkę według czasu znacznika,
- zaznacza właściwy wiersz,
- przewija tabelę do środka,
- wyłącza auto-scroll i zatrzymuje widok, aby wybrana ramka nie odskoczyła.

### 4.2. Znaczniki zapisanej i tymczasowej sesji

Usunięto osobną zakładkę `Znaczniki` z widoku zapisanej sesji.

Znaczniki są dostępne jako osobne, niemodalne okno:

```text
Narzędzia → Znaczniki
```

Skrót:

```text
Ctrl+M
```

Okno zapamiętuje położenie i rozmiar.

Kliknięcie znacznika działa zależnie od aktualnie wybranej zakładki sesji:

- `Surowe ramki` — przejście do najbliższej ramki,
- `Wiadomości logiczne` — przejście do najbliższej wiadomości logicznej.

Jeżeli cache wiadomości logicznych nie jest jeszcze gotowy, aplikacja najpierw uruchamia
standardowe ładowanie lub budowanie cache SQLite, a następnie wykonuje nawigację.

Rozwiązanie działa również dla zakończonej sesji pozostającej jeszcze w katalogu
tymczasowym Live.

## 5. Opóźniona analiza logiczna Live

Podczas aktywnego Capture interfejs Live nie pobiera i nie renderuje wiadomości
logicznych. Zapisywany jest pełny surowy ruch CAN.

Cel:

- nie obciążać głównego procesu Qt analizą transportu i protokołów,
- zachować płynny podgląd surowych ramek,
- nie zmieniać kolejności ani kompletności pełnego zapisu.

Po `STOP` przycisk `Załaduj` otwiera zakończony plik przez standardowy widok zapisanej
sesji oraz ten sam mechanizm `*.logical.sqlite`.

## 6. Nowa logika zapisu Live

### 6.1. Zapis tymczasowy

Każda rejestracja jest zawsze najpierw zapisywana do:

```text
<projekt>\.crt\temp\live\
```

Nie ma już wcześniejszej kontrolki `Zapisz` w wierszu Start/Stop.

Po zatrzymaniu rejestracji log ma stan niezapisany, a aktywna staje się pozycja:

```text
Plik → Zapisz log
```

### 6.2. Nadawanie nazwy przy zapisie

Po wybraniu `Plik → Zapisz log` pojawia się okno:

```text
Nazwa logu:
```

Wpisana wartość jest używana jako:

- pełna nazwa sesji w indeksie projektu,
- źródło bezpiecznej nazwy plików.

Przykład:

```text
Nazwa projektu: Test EGR 01
Plik: Test_EGR_01.crt.jsonl
```

Znaki niedozwolone w nazwach plików są zastępowane znakiem `_`. Pełna nazwa użytkownika
pozostaje zapisana w projekcie.

Anulowanie okna nazwy:

- nie usuwa logu,
- nie przenosi plików,
- pozostawia stan `niezapisany` i aktywne `Plik → Zapisz log`.

### 6.3. Promocja logu do projektu

Po zaakceptowaniu nazwy komplet artefaktów jest przenoszony do:

```text
<projekt>\sessions\live\
```

Przenoszone są, o ile istnieją:

- `*.crt.jsonl`,
- `*.frames.csv`,
- `*.messages.csv`,
- `*.markers.jsonl`,
- `*.logical.sqlite`,
- pomocnicze pliki SQLite `-wal`, `-shm` i `-journal`.

Następnie sesja jest rejestrowana i finalizowana w projekcie z liczbą ramek, znaczników,
czasem trwania oraz stanem zakończenia.

Przy konflikcie nazwy tworzony jest kolejny wariant:

```text
nazwa_02
nazwa_03
```

## 7. Ochrona niezapisanego logu

Przed operacją, która mogłaby usunąć tymczasowy log, aplikacja pokazuje ostrzeżenie.

Dotyczy to:

- rozpoczęcia kolejnego Capture,
- zamknięcia zakładki Live,
- zmiany projektu,
- zamknięcia aplikacji.

Dostępne decyzje:

```text
Zapisz log
Nie zapisuj
Anuluj
```

`Zapisz log` uruchamia również okno nadania nazwy.

## 8. Dwustopniowy Start po niezapisanym logu

Przy istniejącym niezapisanym logu pierwsze kliknięcie `Start` nie może rozpocząć odbioru
ramek.

Przepływ:

1. Pierwszy `Start` pokazuje ostrzeżenie o niezapisanym logu.
2. Operator wybiera `Zapisz log`, `Nie zapisuj` albo `Anuluj`.
3. Po `Zapisz log` lub `Nie zapisuj` aplikacja czyści:
   - tabelę surowych ramek,
   - model wiadomości,
   - listę znaczników,
   - zaznaczenia,
   - liczniki i statusy.
4. Stary bufor kontrolera nie jest ponownie wczytywany przez timer GUI.
5. Capture pozostaje zatrzymany.
6. Dopiero drugie świadome kliknięcie `Start` rozpoczyna nową rejestrację.

Po wybraniu `Anuluj` poprzedni log i jego widok pozostają bez zmian.

Ta sama zasada obowiązuje przy użyciu `Spacji`.

## 9. Główne pliki implementacji

Najważniejsze elementy aktualnego rozwiązania:

- `gui/live_capture.py` — podstawowy widok Live,
- `gui/bounded_live_capture.py` — ograniczony podgląd produkcyjny i analiza po STOP,
- `gui/confirmed_start_live_capture.py` — dwustopniowy Start, nazwa przy zapisie,
  usunięcie pola nazwy z UI,
- `gui/live_save_integration.py` — zapis tymczasowy, promocja plików i ostrzeżenia,
- `gui/fixed_marker_menu_shell.py` — `Plik → Zapisz log` oraz
  `Narzędzia → Znaczniki`,
- `gui/session_marker_window.py` — osobne okno znaczników,
- `gui/session_view.py` i klasy rozwijające — nawigacja po znacznikach zapisanej sesji,
- `gui/application_container.py` — wybór finalnej implementacji Live.

## 10. Testy regresyjne

Dodane lub rozwinięte testy obejmują między innymi:

- `tests_gui/deferred_live_logical_smoke.py`,
- `tests_gui/deferred_log_save_smoke.py`,
- `tests_gui/live_unsaved_second_start_smoke.py`,
- `tests_gui/live_temp_cleanup_smoke.py`,
- `tests_gui/engineering_shell_smoke.py`.

Workflow `GUI Regressions` uruchamia testy zapisu tymczasowego, promocji logu oraz
świadomego drugiego Startu.

## 11. Stan walidacji na moment raportu

### Potwierdzenie ręczne

Użytkownik potwierdził w aplikacji Windows, że działa:

- Start/Stop przez Spację,
- nawigacja po znacznikach,
- okno znaczników przez `Ctrl+M`,
- nowy zapis przez `Plik → Zapisz log`,
- ostrzeżenia o niezapisanym logu,
- dwustopniowe rozpoczęcie kolejnego Capture,
- usunięcie pola nazwy i nadawanie nazwy przy zapisie.

### Automatyczna walidacja

Dla funkcjonalnego commitu `5f4985d...` raport Windows GitHub-Hosted wykazał:

- kompilacja modułów Python — PASS,
- testy jednostkowe — `191 passed`,
- startup aplikacji — PASS,
- Engineering Shell — PASS,
- większość testów GUI — PASS,
- jeden błąd w `deferred_log_save_smoke.py` podczas sprzątania katalogu tymczasowego:
  Windows nie pozwolił usunąć `project.sqlite`, ponieważ plik był jeszcze otwarty przez
  obiekt testowy.

Jest to problem teardownu testu GUI, a nie zgłoszony błąd funkcjonalny zapisu logu.
Pełny CI dla bieżącej gałęzi nie jest jednak jeszcze całkowicie zielony i przed merge
PR #22 należy:

1. dopracować jawne zamykanie i usuwanie obiektów w `deferred_log_save_smoke.py`,
2. ponownie uruchomić pełne GitHub Actions,
3. sprawdzić wszystkie pozostałe niezielone workflow,
4. wykonać końcowy smoke na docelowym Windows z fizycznym Kvaserem.

## 12. Zachowane kontrakty

Nie zmieniono:

- `CaptureService`,
- backendu Kvaser,
- lifecycle CANlib,
- formatu `*.crt.jsonl`,
- formatu indeksu sesji,
- kolejności pełnego zapisu surowych ramek,
- semantyki Global Filter Engine,
- dekodowania DBC, ISO-TP, J1939 i UDS.

## 13. Następny bezpieczny krok

Następna rozmowa powinna rozpocząć się od:

1. przeczytania tego raportu,
2. sprawdzenia aktualnego HEAD gałęzi,
3. naprawienia teardownu `deferred_log_save_smoke.py`,
4. końcowej walidacji PR #22,
5. dopiero potem rozpoczęcia kolejnego etapu funkcjonalnego.

## 14. Komendy lokalne

```powershell
cd C:\CAN\can-research-tool

git fetch origin
git switch agent/ui-engineering-shell-stage1
git reset --hard origin/agent/ui-engineering-shell-stage1

git status -sb
git rev-parse --short HEAD

Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python -X faulthandler -u .\crt_gui.py
```
