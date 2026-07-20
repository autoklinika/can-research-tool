# Przekazanie po refaktoryzacji architektury — punkt startowy dla filtrów

**Status:** działająca, zweryfikowana baza rozwojowa

**Zakres:** etapy B–G z `ARCHITECTURE_REFACTORING_REPORT_PL.md`

**Gałąź:** `agent/working-architecture-refactor-b-g`

**Data zamknięcia porządkowania:** 2026-07-17
**Następny zalecany temat:** dalszy rozwój filtrów CAN

## 1. Stan przekazywanej aplikacji

Aplikacja uruchamia się na Windows z Pythonem 3.12 i zachowuje dotychczasowy
wygląd oraz przebieg pracy. Użytkownik potwierdził działanie aplikacji po kolejnych
etapach refaktoryzacji. Ostatnia automatyczna walidacja zakończyła się wynikiem:

- `pytest`: **94 passed**,
- pełny smoke GUI offscreen: **OK**,
- Ruff dla zmienionych plików: **OK**,
- `git diff --check`: **OK**.

Refaktoryzacja była organizacyjna. Nie zmieniła toru odbioru CAN, lifecycle CANlib,
formatu sesji ani kolejności zapisu surowych ramek przed dekodowaniem.

## 2. Co zostało wykonane

### Etap B — `LiveCaptureController`

- kontroler tworzy `CaptureService`,
- listuje adaptery przez neutralny `CanAdapterInfo`,
- buduje `CaptureConfig` z neutralnego `StartCaptureRequest`,
- udostępnia `start`, `stop`, `status`, `frames_since`, `messages_since`,
- `LiveCaptureWidget` nie tworzy już `CaptureService` ani `CaptureConfig`.

Główne pliki:

- `app/live_capture_controller.py`,
- `gui/live_capture.py`,
- `tests/test_live_capture_controller.py`.

### Etap C — usunięcie Kvasera z warstwy GUI

- GUI operuje na `CaptureMode`,
- mapowanie `BENCH` / `LISTEN_ONLY` do `KvaserReceiveMode` wykonuje kontroler,
- warstwa `gui/` nie importuje `kvaser.backend` ani CANlib.

### Etap D — jawne integracje Live

- `LiveFilterIntegration` i `LiveSaveIntegration` są zależnościami konstruktora,
- podsumowanie protokołów jest podłączane jawnie,
- usunięto runtime patching `LiveCaptureWidget`,
- zachowano buforowanie, pauzę widoku, zapis, znaczniki i DBC.

Główne pliki:

- `gui/live_filter_integration.py`,
- `gui/live_save_integration.py`,
- `gui/protocol_summary.py`.

### Etap E — `StoredSessionController`

- kontroler przejął filtry zapisanych sesji,
- przejął paginację, generacje zadań i worker odczytu strony,
- widok otrzymuje gotowy `StoredSessionPageState`,
- filtry zapisanej sesji nadal są domyślnie wyłączone i wymagają świadomego
  zaznaczenia `Zastosuj filtry`,
- usunięto runtime patching `SessionViewWidget` oraz stare workery GUI.

Główne pliki:

- `app/stored_session_controller.py`,
- `gui/session_view.py`,
- `gui/session_filter_integration.py`,
- `tests/test_stored_session_controller.py`.

### Etap F — nawigacja projektu i sesji

- `ProjectNavigator` przejął rejestrowanie, aktywowanie i zamykanie zakładek,
- ponowne otwarcie tej samej sesji aktywuje istniejącą zakładkę,
- zamknięcie sesji wykonuje `shutdown()` kontrolera,
- `SessionManagementIntegration` jest jawnym obiektem zamiast patcha,
- `Idź do pliku` korzysta z `infrastructure/desktop.py`,
- `app/session_management.py` pozostał bezpieczną warstwą aplikacyjną usuwania.

Główne pliki:

- `gui/project_navigator.py`,
- `gui/session_management_integration.py`,
- `infrastructure/desktop.py`,
- `tests/test_project_navigation_architecture.py`.

### Etap G — composition root

- `ApplicationContainer` jest jedynym produkcyjnym miejscem budowania zależności,
- `gui/main.py` tworzy kontener, a kontener tworzy główne okno,
- kontrolery są tworzone przed widokami i jawnie do nich przekazywane,
- usunięto wszystkie funkcje `install_*` i runtime patching klas,
- logika `filter_state_fix` została wbudowana bezpośrednio w `FilterManagerWidget`,
- graf zależności opisano w `docs/APPLICATION_DEPENDENCIES_PL.md`.

Główne pliki:

- `gui/application_container.py`,
- `gui/main.py`,
- `gui/main_window.py`,
- `gui/filter_manager.py`,
- `tests/test_application_composition.py`.

## 3. Aktualny graf odpowiedzialności

```text
gui/main.py
└─ ApplicationContainer
   ├─ MainWindow
   ├─ ProjectNavigator
   │  └─ SessionViewWidget
   │     └─ StoredSessionController
   ├─ LiveCaptureWidget
   │  └─ LiveCaptureController
   │     └─ CaptureService
   ├─ SessionManagementIntegration
   │  ├─ app/session_management.py
   │  └─ infrastructure/desktop.py
   └─ pozostałe fabryki widoków i zadań GUI
```

Pełny opis kompozycji znajduje się w `docs/APPLICATION_DEPENDENCIES_PL.md`.

## 4. Fundamenty — nie zmieniać bez osobnego planu i testów sprzętowych

Poniższe elementy są fundamentem aplikacji. Rozwój filtrów nie daje zgody na ich
zmianę.

### 4.1. Lifecycle CANlib i Kvasera

- Nie zmieniać kolejności `open → configure bitrate/mode → bus on → read → bus off → close`.
- Nie dodawać automatycznego TX, `write` ani `send`.
- `LISTEN_ONLY` musi pozostać sprzętowym trybem silent, bez ACK i bez transmisji.
- Nie przenosić dekodowania, filtrów GUI ani zapisu plików do wątku odczytu
  sprzętowego.
- `kvaser/backend.py` zmieniać tylko w osobnym zadaniu dotyczącym infrastruktury
  Kvasera, z testem na prawdziwym adapterze.

### 4.2. Krytyczna kolejność danych

W `CaptureService` surowa ramka musi zostać utrwalona przed przetwarzaniem
transportu i dekodowaniem:

```text
odczyt CAN
→ normalizacja ramki
→ SessionStreamWriter.append + FrameCsvStreamWriter.append
→ pipeline transportowy
→ dekodowanie protokołu/DBC
→ zapis wiadomości logicznej
→ ograniczony bufor GUI
```

Nie wolno dopuścić, aby błąd filtra, DBC lub dekodera uniemożliwił zapis surowej
ramki. Filtry użytkownika są warstwą widoku i nie mogą odrzucać materiału
źródłowego z zapisywanej sesji.

### 4.3. Format i źródło prawdy sesji

- Surowe `*.crt.jsonl` i `*.frames.csv` są źródłem prawdy.
- Nie zmieniać schematu nagłówka, rekordów, sparse index ani nazw sidecarów bez
  wersjonowania i migracji wstecznej.
- Zachować pliki:
  - `*.crt.jsonl`,
  - `*.crt.jsonl.idx.json`,
  - `*.frames.csv`,
  - `*.messages.csv`,
  - `*.markers.jsonl`.
- DBC i wiadomości logiczne są odwracalną interpretacją; nie modyfikują surowych
  ramek.
- Importowana sesja może usuwać tylko kopie należące do projektu. Oryginalny plik
  spoza projektu musi pozostać nietknięty.

### 4.4. Czas, kolejność i znaczniki

- Zachować monotoniczny zegar ramek i znaczników.
- Nie zmieniać znaczenia `sequence` ani `timestamp_ns`.
- Znacznik ma być timestampowany natychmiast; zapis na dysk może być kolejkowany.
- Nie sortować ani nie przepisywać surowych ramek według wyników dekodowania.

### 4.5. Granice pamięci GUI

- Bufory Live GUI pozostają ograniczone.
- `Pauza widoku` nie zatrzymuje rejestracji ani zapisu.
- Zniknięcie starych wierszy z widoku nie oznacza utraty ramek zapisanych w sesji.
- Stronicowanie zapisanej sesji nie może ładować całego dużego logu do pamięci,
  chyba że świadomie wykonuje pełny skan filtra poza wątkiem Qt.

### 4.6. Kompozycja i brak runtime patchingu

- Nie przywracać `Class.method = replacement` ani funkcji `install_*`.
- Nowe zależności produkcyjne dodawać w `ApplicationContainer`.
- GUI nie może bezpośrednio tworzyć `CaptureService` ani importować Kvasera.
- Logikę niezależną od Qt umieszczać w `app/`; operacje systemowe w
  `infrastructure/`; prezentację w `gui/`.

## 5. Co wolno rozwijać w filtrach

Rozwój filtrów może obejmować:

- nowe pola `FilterField`,
- nowe operatory `FilterOperator`,
- rozszerzenie drzewa AND/OR/NOT,
- walidację i komunikaty błędów,
- nowe tryby prezentacji i wyróżnienia,
- zarządzanie presetami, skrótami i zakresem `live` / `stored_session`,
- optymalizację oceny filtrów,
- poprawę edytora `FilterManagerWidget`,
- diagnostykę niedostępnych pól,
- testowanie filtra na przykładowej ramce,
- paginację i wyszukiwanie wyników zapisanej sesji.

Najważniejsze miejsca zmian:

| Obszar | Pliki |
|---|---|
| Model, format i kompilator | `app/filters.py` |
| Operacje na drzewie | `app/filter_tree.py` |
| Semantyka aktywnych presetów | `app/live_filters.py` |
| Strona zapisanej sesji | `app/session_filters.py` |
| Kontroler zapisanej sesji | `app/stored_session_controller.py` |
| Edytor filtrów | `gui/filter_manager.py` |
| Filtr Live | `gui/live_filter_integration.py`, `gui/live_filter_proxy.py` |
| Filtry zapisanej sesji | `gui/session_filter_integration.py` |

## 6. Kontrakty filtrów, które trzeba zachować

1. Filtry nie wpływają na zapis surowych ramek.
2. `INCLUDE` i `EXCLUDE` wpływają wyłącznie na widoczność.
3. `HIGHLIGHT` nie ukrywa ramki.
4. Wiele aktywnych presetów `INCLUDE` jest obecnie łączonych przez AND.
5. Preset działa tylko w swoim `scope`.
6. Filtry zapisanej sesji są domyślnie wyłączone.
7. Niepoprawny, wyłączony szkic może zostać zapisany.
8. Niepoprawny aktywny preset blokuje zapis i pokazuje błąd.
9. Zmiana aktywności presetu jest zapisywana natychmiast.
10. Pełna ocena dużego bufora Live odbywa się w workerze; nowe ramki po snapshotcie
    są oceniane przyrostowo.
11. Wynik starszego workera nie może nadpisać nowszej generacji filtra lub strony.

Zmiana któregoś z tych kontraktów wymaga jawnej decyzji produktowej, aktualizacji
formatu lub dokumentacji oraz nowych testów regresyjnych.

## 7. Minimalny zestaw testów po zmianie filtrów

```powershell
python -m pytest -q
python tests_gui\live_filter_worker_smoke.py
python tests_gui\stored_session_filter_optin_smoke.py
```

Przed połączeniem większej zmiany uruchomić również:

```powershell
python tests_gui\dbc_activation_smoke.py
python tests_gui\session_management_smoke.py tree
python tests_gui\session_management_smoke.py live
python tests_gui\session_management_smoke.py imported
```

W CI wszystkie smoki GUI używają `QT_QPA_PLATFORM=offscreen`.

Testy architektury, których nie wolno usuwać tylko dlatego, że nowa implementacja
ich nie przechodzi:

- `tests/test_live_capture_controller.py`,
- `tests/test_stored_session_controller.py`,
- `tests/test_project_navigation_architecture.py`,
- `tests/test_application_composition.py`.

## 8. Znane ograniczenia i odłożone prace

- Etap H, czyli monitoring backlogu, RAM i CPU, został świadomie odłożony do czasu
  rzeczywistych pomiarów na obciążonej magistrali.
- `MainWindow._tab_keys` pozostaje aliasem kompatybilności.
- Widoki mają domyślne kontrolery dla izolowanych testów; produkcyjny punkt wejścia
  zawsze korzysta z `ApplicationContainer`.
- `SessionManagementIntegration` zna `MainWindow`, ale jest jawnym obiektem i nie
  patchuje klasy.
- Worker wiadomości logicznych zapisanej sesji nadal korzysta z Qt; etap E
  wydzielił worker filtrów i paginacji.
- Nie ustalono jeszcze polityki limitowania sprzętowej kolejki odbiorczej. Nie
  dodawać arbitralnego odrzucania ramek bez pomiarów.

## 9. Proponowany początek następnej rozmowy

Można wkleić poniższy tekst jako pierwszy prompt:

> Pracujemy na gałęzi `agent/working-architecture-refactor-b-g`. Przeczytaj
> `docs/REFACTORING_HANDOFF_FILTERS_PL.md` oraz
> `docs/APPLICATION_DEPENDENCIES_PL.md`. Aplikacja jest działającą bazą po etapach
> B–G; pełne pytest miało 94 testy zielone, a GUI smoke przeszedł. Kontynuujemy
> rozwijanie filtrów. Bezwzględnie zachowaj lifecycle CANlib, kolejność raw write
> przed dekodowaniem, formaty sesji, bounded GUI buffers, brak TX oraz zasadę, że
> filtry nie wpływają na materiał zapisywany na dysk. Przed implementacją opisz
> proponowany kontrakt nowej funkcji filtra i wskaż testy regresyjne.

## 10. Kryterium gotowości tej gałęzi

Gałąź jest punktem bazowym do dalszego rozwoju, jeśli:

- aplikacja uruchamia się przez `python .\crt_gui.py` lub `crt-gui`,
- `python -m pytest -q` jest zielone,
- oba smoki filtrów są zielone,
- nie ma runtime patchingu ani funkcji `install_*`,
- `kvaser/backend.py`, `CaptureService` i formaty sesji pozostają bez zmian względem
  bazowego commita przed refaktoryzacją.
