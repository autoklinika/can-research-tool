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
- reguły dla protokołów autorskich,
- przenośne projekty badawcze,
- obszary badań, np. EGR, VGT i SCR,
- konfigurowalne znaczniki czasowe z nazwą i skrótem klawiszowym.

Surowe ramki i oryginalne pliki pozostają źródłem prawdy. Dekodery tworzą dodatkowy widok i nie modyfikują materiału wejściowego.

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

## Projekt CRT

Każdy projekt jest samodzielnym folderem na dysku. Można go przenieść, skopiować lub spakować bez utraty relacji między sesjami, znacznikami i obszarami badań.

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
├─ Porównania
├─ Sygnały
├─ Hipotezy
├─ Dekodery
├─ Notatki
├─ Załączniki
└─ Raporty
```

Podwójne kliknięcie zapisanej sesji otwiera ją w osobnej zakładce. Import dużego logu odbywa się w wątku roboczym.

## Znaczniki podczas logowania

Przed naciśnięciem `Start` można zdefiniować dowolny zestaw znaczników:

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

Po rozpoczęciu rejestracji aktywne znaczniki są dostępne jednocześnie jako skróty i duże przyciski. Naciśnięcie nie otwiera żadnego okna dialogowego. Timestamp jest pobierany natychmiast z tego samego monotonicznego zegara co ramki CAN.

Znaczniki są zapisywane w:

```text
<nazwa_sesji>.markers.jsonl
```

oraz indeksowane w bazie projektu. Zapis zachowuje kopię nazwy, skrótu, koloru i obszaru użytych w chwili eksperymentu.

## Wydajność GUI

GUI używa dwóch torów danych:

```text
Kvaser
  ├─ pełny strumień → sesja i pliki wynikowe na dysku
  └─ ostatnie 20 000 ramek → bufor live → QAbstractTableModel → QTableView
```

- odbiór, zapis i transport działają poza wątkiem Qt,
- tabela jest odświeżana paczkami co 100 ms,
- `Pauza widoku` nie zatrzymuje rejestracji,
- pamięć podglądu nie rośnie wraz z czasem logowania,
- duże sesje są indeksowane i otwierane fragmentami,
- import logów odbywa się asynchronicznie.

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

GitHub Actions uruchamia dodatkowo kompilację wszystkich modułów oraz headless Qt smoke test otwierający projekt i zakładkę `Live Capture`.
