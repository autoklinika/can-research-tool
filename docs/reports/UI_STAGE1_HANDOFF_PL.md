# CAN Research Tool — finalne przekazanie UI Stage 1 i wiadomości logicznych

Data przekazania: 2026-07-21

## 1. Punkt startowy

- repozytorium: `autoklinika/can-research-tool`
- aktywna gałąź: `agent/ui-engineering-shell-stage1`
- pull request: `#22` — **UI Stage 1 — engineering IDE shell**
- zwalidowany commit funkcjonalny przed dodaniem tego raportu:
  `939e1148bc93850baa020d8ebf47228b88a9e308`
- baza PR: `main` po zakończeniu PR #21
- aplikacja uruchamiana przez: `python -X faulthandler -u .\crt_gui.py`

Ten raport zastępuje wcześniejszą, nieaktualną wersję pliku, która nadal opisywała
widoczny Activity Bar, Output oraz domyślnie otwarty Inspektor.

## 2. Stan ogólny

Etap został dopracowany ręcznie i automatycznie. Użytkownik potwierdził, że aktualny
układ działa. Powłoka GUI, zapisane sesje i wiadomości logiczne są teraz przygotowane
jako fundament pod kolejne, bardziej rozbudowane etapy analizy logów.

Najważniejsza decyzja architektoniczna:

- główny proces Qt odpowiada za płynny interfejs,
- ciężka pierwsza analiza wiadomości może działać w procesie pomocniczym,
- wynik analizy jest zapisywany jako trwały, wersjonowany cache SQLite,
- kolejne otwarcia sesji nie dekodują ponownie całego logu,
- tabela wiadomości jest wirtualna i nie ładuje setek tysięcy obiektów do RAM.

## 3. Powłoka GUI

### 3.1. Styl

- globalny styl `Fusion` nie jest wymuszany,
- używany jest natywny renderer platformy oraz selektywny ciemny QSS,
- motyw jest obecnie jeden — ciemny,
- day/night zostanie rozważony później,
- nie należy wracać do globalnego `app.setStyle("Fusion")`,
- nie należy wykonywać globalnego `polish/unpolish` całego drzewa widgetów.

Ciemny styl obejmuje:

- grafitowe tła,
- niebieski akcent aktywnych zakładek,
- kompaktowe menu i panele,
- ciemne tabele i nagłówki,
- lekkie scrollbary,
- zielony pasek gotowości wiadomości logicznych.

### 3.2. Układ okna

Obecny układ domyślny:

- Activity Bar jest usunięty z widoku,
- panel Output jest trwale usunięty z układu,
- Inspektor jest domyślnie ukryty,
- pasek `Narzędzia główne` jest domyślnie ukryty,
- panel Projekt jest widoczny,
- centralne zakładki wykorzystują całą odzyskaną przestrzeń.

Menu `Widok` zawiera między innymi:

- Projekt — `Ctrl+B`,
- Inspektor — `Ctrl+Shift+I`,
- Narzędzia główne,
- Resetuj układ okna.

`Widok → Resetuj układ okna`:

- nie przywraca Output,
- pozostawia Inspektor ukryty,
- pozostawia Narzędzia główne ukryte,
- pokazuje panel Projekt,
- usuwa wpływ starego zapisu workspace.

Aktualna wersja stanu workspace w `RestorableDockEngineeringShellMainWindow` wynosi `6`.

### 3.3. Panel Projekt

Panel Projekt ma własny pasek tytułu z trzema kontrolkami:

1. odpinanie/dokowanie,
2. strzałka ukrycia panelu,
3. zamknięcie `X`.

Animacja zwijania została świadomie usunięta. Powodowała różnice w zachowaniu
`minimumWidth/maximumWidth` między Linuxem i natywnym Qt na Windows.

Aktualne zachowanie:

- kliknięcie strzałki natychmiast ukrywa panel,
- `Ctrl+B` lub `Widok → Projekt` pokazuje go ponownie,
- szerokość docka nie jest modyfikowana podczas ukrywania,
- `X` zachowuje standardowe działanie zamknięcia docka.

### 3.4. Panel Output

Output nie jest już elementem interfejsu:

- nie zajmuje miejsca,
- nie jest dostępny w menu Widok,
- skrót `Ctrl+J` został usunięty,
- stary workspace nie może go przywrócić,
- reset układu go nie przywraca.

Wewnętrzny sink diagnostyczny nadal istnieje, aby nie uszkodzić istniejących ścieżek
raportowania, ale jego dock jest ukryty, odłączony od `QMainWindow` i zablokowany.

## 4. Zapisane sesje — pełna liczba ramek

### 4.1. Surowe ramki

Usunięto wcześniejszy limit strony wynoszący 2000 ramek.

Dla zapisanej sesji:

- rzeczywista liczba ramek jest odczytywana z indeksu sesji,
- model dostaje pojemność odpowiadającą pełnej sesji,
- użytkownik ma dostęp do wszystkich zapisanych ramek,
- filtry obejmują cały log, a nie tylko jedną stronę wyników.

Nie zmieniono:

- formatu `*.crt.jsonl`,
- formatu indeksu sesji,
- kolejności pełnego zapisu ramek,
- `CaptureService`,
- Kvasera ani lifecycle CANlib.

### 4.2. Wiadomości logiczne

Usunięto wcześniejszy limit 1000 wiadomości.

Zakładka pokazuje pełny zbiór zapisanej sesji i ma układ ośmiu kolumn:

1. `Czas [s]`,
2. `ID`,
3. `Nazwa`,
4. `Nadawca`,
5. `Protokół`,
6. `DLC`,
7. `Dane`,
8. `Wartości (zdekodowane)`.

Panel filtrów zawiera:

- protokół,
- nadawcę,
- ID / nazwę,
- czas od/do,
- dane hex/dec,
- tylko błędy,
- ukrywanie okresowych,
- opcję `Zastosuj filtry projektu`,
- `Zastosuj` i `Wyczyść`.

Filtry projektu korzystają z tego samego silnika decyzyjnego co Live. Lokalne kryteria
zapisanej sesji są wykonywane na indeksowanym cache SQLite.

## 5. Trwały obraz analityczny SQLite

Dla sesji:

```text
nazwa.crt.jsonl
nazwa.messages.csv
```

CRT tworzy:

```text
nazwa.logical.sqlite
```

Główna implementacja znajduje się w:

- `app/logical_cache.py`,
- `crt_logical_messages_worker.py`,
- `gui/stored_logical_sql_model.py`,
- `gui/sqlite_logical_session_view.py`,
- `gui/stored_logical_message_panel.py`.

Cache ma:

- format: `crt-logical-cache`,
- wersję formatu: `1`,
- bieżący podpis dekoderów:
  `transport-v2;protocol-v3;dbc-v2`,
- zapis partiami po `1000` rekordów,
- atomową podmianę pliku tymczasowego,
- jawne zamykanie połączeń SQLite przed `os.replace`,
- retry pod Windows na krótkotrwałą blokadę antywirusa lub indexera.

Cache jest ponownie używany tylko wtedy, gdy zgadzają się:

- fingerprint źródłowej sesji,
- stan `messages.csv`,
- podpis wersji dekoderów,
- podpis aktywnych plików DBC,
- liczba rekordów zapisana w metadanych i faktyczna liczba w tabeli.

Przycisk `Załaduj ponownie` celowo wymusza pełną przebudowę cache.
Zwykłe ponowne otwarcie tej samej sesji powinno używać zapisanego obrazu.

Jeżeli `messages.csv` nie istnieje, cache jest rekonstruowany z surowych ramek przez
transport pipeline.

## 6. Wirtualny model wiadomości

Tabela wiadomości logicznych nie przechowuje całej sesji jako listy obiektów Python.

Model:

- czyta dane bezpośrednio z SQLite,
- pobiera tylko potrzebne strony,
- używa małego cache stron,
- zachowuje pełny `rowCount`,
- pozwala przewijać cały log,
- nie skanuje całego zbioru przy każdym odświeżeniu GUI.

Ta warstwa jest krytyczna dla kolejnych etapów analizowania logów. Nie należy jej
zastępować ponownym ładowaniem wszystkich rekordów do RAM.

## 7. DBC — wydajność i prezentacja

Dekodowanie DBC zostało radykalnie przyspieszone. Użytkownik potwierdził dużą różnicę
wydajności.

Implementacja w `app/dbc.py` wykorzystuje:

- dokładne dopasowanie CAN ID przez słownik O(1),
- indeks PDU1 według PF,
- indeks PDU2 według PF i Group Extension,
- cache dopasowania per CAN ID — maksymalnie `65 536` wpisów,
- LRU zdekodowanych kombinacji wiadomość+payload — `4096` wpisów,
- jednorazowe przygotowanie nadawców i jednostek,
- `decode_if_matches()` zamiast osobnego `matches()` i `decode()`.

Kolejność klasyfikacji jest konserwatywna:

1. UDS po ISO-TP,
2. J1939 TP,
3. aktywne DBC,
4. reguły użytkownika,
5. CANopen,
6. potwierdzony pojedynczy J1939,
7. Unknown / proprietary.

Nie wolno uznawać każdej ramki 29-bitowej za J1939 wyłącznie na podstawie układu ID.

Prezentacja DBC zawiera:

- nazwę wiadomości,
- nazwę nadawcy,
- sygnały,
- wartości skalowane,
- jednostki,
- plik DBC,
- sposób dopasowania.

## 8. Wbudowane dekodowanie UDS

UDS został rozszerzony z prostego rozpoznawania SID na dekodowanie warstwy danych.
Użytkownik zaakceptował bieżący stan słowami „na razie tak zostaje”.

Obsługiwane są między innymi:

- `0x10 DiagnosticSessionControl`,
- `0x14 ClearDiagnosticInformation`,
- `0x19 ReadDTCInformation`,
- `0x22 ReadDataByIdentifier`,
- `0x23 ReadMemoryByAddress`,
- `0x27 SecurityAccess`,
- `0x28 CommunicationControl`,
- `0x2E WriteDataByIdentifier`,
- `0x2F InputOutputControlByIdentifier`,
- `0x31 RoutineControl`,
- `0x34 RequestDownload`,
- `0x35 RequestUpload`,
- `0x36 TransferData`,
- `0x37 RequestTransferExit`,
- `0x3D WriteMemoryByAddress`,
- odpowiedzi negatywne `0x7F`, w tym `responsePending`.

Dekodowane pola obejmują między innymi:

- typ sesji i czasy P2/P2*,
- DID oraz data record,
- ASCII, np. VIN,
- seed/key i poziom SecurityAccess,
- Routine ID,
- adres i rozmiar pamięci,
- block sequence counter,
- transfer data,
- DTC i status,
- NRC.

Nieznane dane producenta pozostają dostępne jako HEX. Dekoder nie powinien zgadywać
semantyki danych bez jednoznacznej definicji.

Testy obejmują rzeczywiste przypadki ETC3, np.:

- `50 01 00 32 00 FA`,
- `67 07 5A 19 4C 00`,
- `27 08 A1 74 97 E5`,
- `34 00 44 00 A2 00 00 00 00 11 EE`,
- `31 01 F0 22 00 A0 00 00`,
- `7F 27 35`,
- wieloramkowe ISO-TP `62 F190 <VIN>`.

## 9. Szczegóły wiadomości po podwójnym kliknięciu

W zakładce `Wiadomości logiczne` dwukrotne kliknięcie lewym przyciskiem myszy otwiera
niezależne, nieblokujące okno szczegółów.

Nie uruchamia ponownego ładowania sesji. Pobierany jest tylko wskazany rekord z SQLite.

Okno ma wspólną sekcję transportową i sekcje zależne od protokołu:

- UDS,
- DBC,
- J1939,
- CANopen,
- Unknown / proprietary.

Można otworzyć kilka okien jednocześnie i porównywać wiadomości.

Pliki:

- `gui/protocol_message_details.py`,
- `tests_gui/logical_message_details_smoke.py`.

Duże natywne tooltipy tabeli wiadomości są wyłączone. Szczegóły mają być prezentowane
w dedykowanym oknie, nie w Inspektorze ani tooltipie.

## 10. Pliki historyczne i nieaktywne ścieżki

W repozytorium nadal istnieją wcześniejsze pliki eksperymentalnego zewnętrznego viewer-a:

- `crt_logical_messages.py`,
- `gui/logical_message_viewer.py`,
- część kodu w `gui/external_logical_session_view.py`.

Aktualny interfejs nie używa osobnego okna/programu jako głównej zakładki wiadomości.
Proces pomocniczy może działać w tle, ale użytkownik pozostaje w zakładce CRT.

Nie usuwać plików historycznych bez osobnego przeglądu zależności i testów importów.

## 11. Najważniejsze kontrakty, których nie wolno naruszyć

1. Nie zmieniać `CaptureService` bez osobnego etapu.
2. Nie zmieniać Kvasera ani lifecycle CANlib.
3. Nie zmieniać formatu `*.crt.jsonl` ani istniejącego indeksu sesji.
4. Nie zmieniać kolejności pełnego zapisu surowych ramek.
5. Live Capture nadal używa ograniczonych modeli podglądu — pełny dostęp dotyczy
   zapisanych logów.
6. Nie wprowadzać globalnych mutacji klas, np. zmiany `SessionViewWidget.MAX_MESSAGES`
   z poziomu kontenera aplikacji.
7. Nie wymuszać globalnego Fusion.
8. Nie ładować całej bazy wiadomości do listy Python tylko po to, aby pokazać pełny
   `rowCount`.
9. Cache analityczny musi być unieważniany po zmianie źródła, DBC albo dekoderów.
10. Klasyfikacja protokołu ma być konserwatywna — brak fałszywego J1939.

## 12. Walidacja

Dla zwalidowanego commitu funkcjonalnego `939e114` przeszły:

- pełny `pytest`,
- GUI smoke,
- wszystkie regresje GUI,
- testy filtrowania zapisanych sesji i Live,
- testy cache SQLite,
- testy DBC i jego cache,
- testy UDS data decoder,
- testy okien szczegółów UDS/DBC,
- GitHub-hosted Windows full validation,
- finalny krok `Enforce validation result`.

Istotne testy:

- `tests/test_dbc.py`,
- `tests/test_logical_cache.py`,
- `tests/test_uds_data_decoder.py`,
- `tests_gui/engineering_shell_smoke.py`,
- `tests_gui/stored_logical_workspace_smoke.py`,
- `tests_gui/logical_message_details_smoke.py`,
- `tests_gui/uds_data_display_smoke.py`,
- `tests_gui/stored_session_filter_optin_smoke.py`,
- `tests_gui/protocol_filter_gui_smoke.py`.

## 13. Szybkie uruchomienie na Windows

```powershell
cd C:\CAN\can-research-tool

git fetch origin
git switch agent/ui-engineering-shell-stage1
git reset --hard origin/agent/ui-engineering-shell-stage1

git status -sb
git rev-parse --short HEAD
python -X faulthandler -u .\crt_gui.py
```

## 14. Diagnostyka natywnego abortu Qt

Przy ewentualnym natywnym przerwaniu aplikacji najpierw odczytać:

```powershell
Get-Content .\crt_gui_startup.log
```

Checkpointy w `gui/main.py` rozdzielają:

- tworzenie `QApplication`,
- motyw,
- kontener,
- konstrukcję okna,
- pokazanie okna,
- event loop.

Nie należy automatycznie przypisywać komunikatów `QThreadStorage` jako pierwotnej
przyczyny. Często są skutkiem wcześniejszego natywnego abortu Qt.

## 15. Rekomendowany początek następnego etapu

Najpierw wykonać krótką kontrolę aktualnego HEAD oraz przeczytać ten raport.
Następnie ustalić jeden zamknięty zakres dalszej pracy.

Rekomendowana kolejność:

1. finalny ręczny przegląd dużej sesji na Windows,
2. kontrola płynności przewijania i filtrowania po dłuższej pracy,
3. ewentualne uporządkowanie nieaktywnych plików zewnętrznego viewer-a,
4. dopiero potem rozpoczęcie kolejnego etapu analizy logów,
5. każdą nową analizę budować na indeksach SQLite lub przetwarzaniu strumieniowym,
   nie na pełnych listach rekordów w GUI.

## 16. Gotowy tekst do rozpoczęcia nowej rozmowy

```text
Kontynuujemy CAN Research Tool po zakończeniu dopracowania UI Stage 1 i zapisanych
wiadomości logicznych.

Repozytorium: autoklinika/can-research-tool
Gałąź: agent/ui-engineering-shell-stage1
PR: #22
Zwalidowany commit funkcjonalny przed raportem: 939e114

Przeczytaj dokładnie docs/reports/UI_STAGE1_HANDOFF_PL.md, sprawdź aktualny HEAD gałęzi
i nie opieraj się na starym opisie PR #22, ponieważ nie uwzględnia on późniejszych
zmian: usuniętego Output, ukrytego Inspektora i paska Narzędzia główne, SQLite cache,
wirtualnego modelu wiadomości, optymalizacji DBC, rozszerzonego UDS oraz okien
szczegółów po podwójnym kliknięciu.

Nie zmieniaj CaptureService, Kvasera, lifecycle CANlib, formatu sesji ani kolejności
pełnego zapisu surowych ramek. Zacznij od potwierdzenia stanu repozytorium i krótkiego
podsumowania najważniejszych kontraktów z raportu.
```
