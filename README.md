# CAN Research Tool (CRT)

CRT to niezależne środowisko do **reverse engineeringu komunikacji CAN**. Nie jest kopią ECU Platform i nie zawiera gotowych procedur serwisowych konkretnych sterowników.

## Aktualny zakres

- wykrywanie interfejsów i kanałów Kvaser,
- odbiór surowych ramek bez aplikacyjnego API `write` / `send`,
- dwa tryby elektryczne:
  - `BENCH` — kontroler wystawia ACK; właściwy dla pojedynczego ECU na stole,
  - `LISTEN_ONLY` — sprzętowy `SILENT`, bez TX i bez ACK; dla kompletnej aktywnej sieci,
- strumieniowy zapis pełnej sesji i ograniczony bufor GUI,
- import sesji CRT oraz dotychczasowych logów Kvaser CSV,
- rekonstrukcja J1939 TP i ISO-TP,
- klasyfikacja UDS oraz bezpieczny fallback `UNKNOWN`,
- projektowe dekodery DBC z możliwością włączenia i wyłączenia,
- reguły dla protokołów autorskich,
- przenośne projekty badawcze,
- obszary badań, np. EGR, VGT i SCR,
- konfigurowalne znaczniki czasowe z nazwą i skrótem klawiszowym.

Surowe ramki i oryginalne pliki pozostają źródłem prawdy. DBC oraz inne dekodery tworzą odwracalny widok i nie modyfikują materiału wejściowego.

## Instalacja

```powershell
python -m pip install -e ".[dev,kvaser,gui]"
```

## Uruchomienie GUI

```powershell
python .\crt_gui.py
```

lub:

```powershell
crt-gui
```

Graf kompozycji kontrolerów, widoków i infrastruktury opisuje
`docs/APPLICATION_DEPENDENCIES_PL.md`.

Działający punkt bazowy po refaktoryzacji B–G oraz zasady bezpiecznego rozwoju
filtrów opisuje `docs/REFACTORING_HANDOFF_FILTERS_PL.md`.

## Projekt CRT

Każdy projekt jest samodzielnym folderem na dysku. Można go przenieść, skopiować lub spakować bez utraty relacji między sesjami, znacznikami, dekoderami i obszarami badań.

Przykładowa struktura:

```text
DAF_MX13_EGR/
├─ project.crt.json
├─ .crt/
│  ├─ project.sqlite
│  └─ indexes/
├─ sessions/
│  ├─ live/
│  └─ imported/
│     └─ source/
├─ experiments/
├─ notes/
├─ attachments/
├─ decoders/
│  └─ dbc/
├─ exports/
└─ reports/
```

`project.crt.json` zawiera podstawowe dane projektu. `.crt/project.sqlite` przechowuje indeks i relacje, ale surowe logi nadal są zwykłymi plikami wewnątrz projektu.

## Układ GUI

Aplikacja korzysta z modelu pracy podobnego do środowiska programistycznego:

- pionowy pasek aktywności,
- Explorer projektu po lewej,
- centralne zakładki robocze,
- Inspektor po prawej,
- dolny panel `Output / Problemy / Zadania`,
- pasek statusu połączenia i rejestracji.

W Explorerze znajdują się:

```text
Projekt
├─ Przegląd projektu
├─ Live Capture
├─ Obszary badań
├─ Eksperymenty
├─ Sesje CAN
│  ├─ Live
│  └─ Importowane
├─ Dekodery
│  └─ DBC — aktywne n/m
├─ Porównania
├─ Sygnały
├─ Hipotezy
├─ Notatki
├─ Załączniki
└─ Raporty
```

Podwójne kliknięcie zapisanej sesji otwiera ją w osobnej zakładce. Import dużego logu odbywa się w wątku roboczym.

## Znaczniki podczas logowania

Konfiguracja znaczników nie zajmuje już miejsca w głównym widoku. W sekcji `Połączenie i sesja` znajduje się kafelek:

```text
Znaczniki
4 aktywnych / 6
```

Kliknięcie kafelka otwiera osobne okno, w którym można dodać, edytować, usuwać oraz włączać i wyłączać definicje:

```text
Nazwa             Skrót   Obszar
EGR odłączony     F3      EGR
EGR podłączony    F4      EGR
VGT ruch +        F5      VGT
VGT ruch -        F6      VGT
```

Każdy znacznik ma:

- nazwę,
- skrót klawiszowy,
- kolor,
- opcjonalny obszar projektu,
- stan aktywny/nieaktywny.

Po rozpoczęciu rejestracji pod konfiguracją połączenia pojawiają się tylko szybkie przyciski aktywnych znaczników. Skróty działają równolegle. Naciśnięcie nie otwiera żadnego okna dialogowego, a timestamp jest pobierany natychmiast z tego samego monotonicznego zegara co ramki CAN.

Znaczniki są zapisywane w:

```text
<nazwa_sesji>.markers.jsonl
```

oraz indeksowane w bazie projektu. Zapis zachowuje kopię nazwy, skrótu, koloru i obszaru użytych w chwili eksperymentu.

## Dekodery DBC

Zakładkę `Dekodery` można otworzyć z pionowego paska aktywności albo z Explorera projektu. Widok umożliwia:

- import jednego lub wielu plików `*.dbc`,
- kopiowanie plików do `decoders/dbc` projektu,
- sprawdzenie liczby wiadomości zdefiniowanych w pliku,
- włączanie i wyłączanie każdego DBC checkboxem,
- usuwanie DBC z projektu,
- podgląd ścieżki i SHA-256 w Inspektorze.

Pierwszy aktywny DBC ma pierwszeństwo, gdy kilka plików definiuje ten sam CAN ID i typ ramki. Aktywne DBC są używane przy rozpoczęciu następnego `Live Capture`. Zmiana stanu powoduje również ponowne zinterpretowanie otwartych zapisanych sesji.

DBC jest nakładką na surowe dane:

```text
DBC aktywny    → DBC EGR_Status + wartości sygnałów
DBC wyłączony  → UNKNOWN / bazowa interpretacja
```

Wyłączenie DBC nie usuwa pliku ani nie modyfikuje sesji. Trwająca rejestracja zachowuje zestaw dekoderów wybrany przy `Start`, aby interpretacja nie zmieniała się w środku eksperymentu.

Szczegóły działania znajdują się w `docs/decoder-workspace.md`.

## Wiadomości logiczne

`Live Capture` oraz zapisane sesje mają osobne widoki:

```text
Surowe ramki
Wiadomości logiczne
```

Tabela wiadomości pokazuje protokół, transport, PGN lub CAN ID, źródło, cel, długość, liczbę ramek, kompletność, nazwę i payload. Inspektor zawiera pełny payload, ramki źródłowe i pola protokołu. Dla wiadomości DBC pola obejmują nazwę wiadomości, plik DBC, wartości sygnałów oraz jednostki.

## Wydajność GUI

GUI używa dwóch torów danych:

```text
Kvaser
  ├─ pełny strumień → sesja i pliki wynikowe na dysku
  └─ ograniczony podgląd → QAbstractTableModel → QTableView
```

- odbiór, zapis i transport działają poza wątkiem Qt,
- tabele są odświeżane paczkami co 100 ms,
- `Pauza widoku` nie zatrzymuje rejestracji,
- bufor live przechowuje maksymalnie 20 000 ramek i 5 000 wiadomości,
- pamięć podglądu nie rośnie wraz z czasem logowania,
- duże sesje są indeksowane i otwierane fragmentami,
- import logów i rekonstrukcja wiadomości odbywają się asynchronicznie.

## Pliki sesji GUI

Rejestracja wewnątrz projektu tworzy:

```text
*.crt.jsonl
*.crt.jsonl.idx.json
*.frames.csv
*.messages.csv
*.markers.jsonl
```

## Rejestracja z terminala

```powershell
python .\capture_session.py --duration 10 --name bench_test
```

Nasłuch bez limitu:

```powershell
python .\capture_session.py --duration 0 --name long_capture
```

## Analiza zapisanej sesji

```powershell
python .\analyze_session.py .\sessions\pierwszy_test.crt.jsonl
```

## Testy

```powershell
python -m pytest -q
```

GitHub Actions uruchamia dodatkowo kompilację modułów oraz headless Qt smoke test tworzący projekt, kafelek znaczników, zakładkę `Live Capture` i zakładkę `Dekodery` z przełączanym plikiem DBC.
