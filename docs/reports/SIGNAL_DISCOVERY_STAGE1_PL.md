# CAN Research Tool — Signal Discovery Workspace Stage 1

Data: 2026-08-30

Status: **implementacja na gałęzi roboczej; wymagany końcowy Windows CI i ręczny odbiór właściciela**

Gałąź:

`agent/signal-discovery-stage1`

Baza produkcyjna:

`main` = `daf0e8328ee30932e1a286ad44cebb3616f1fdba`

Draft PR:

`#61 — Add Signal Discovery byte/bit activity and bitfield workspace`

---

## 1. Cel etapu

Stage 1 rozpoczyna realizację near-term kierunku **Signal Discovery Workspace**. Celem jest skrócenie ręcznego reverse engineeringu od nieznanego CAN ID do pierwszych zweryfikowanych kandydatów sygnałów, bez naruszania evidence-first architektury CRT.

Etap odpowiada na trzy podstawowe pytania:

1. które bajty i bity wybranej wiadomości zmieniają się w zapisanej sesji,
2. jak wygląda dowolnie wybrany bitfield po interpretacji Intel/Motorola, signed/unsigned, scale/offset,
3. z której dokładnej surowej ramki pochodzi obserwacja pokazana jako minimum, maksimum lub punkt wykresu.

---

## 2. Zakres funkcjonalny

### 2.1. Dokładny klucz wiadomości

Analiza jest wykonywana dla jednego klucza obejmującego:

- kanał,
- CAN ID,
- STD 11-bit / EXT 29-bit,
- rodzaj `data`, `remote` albo `error`.

Ten sam numeryczny CAN ID w STD i EXT jest traktowany jako dwa różne klucze.

### 2.2. Byte / Bit Activity Map

Dla wszystkich pasujących ramek w całej sesji wyliczane są między innymi:

- liczba wystąpień,
- minimum i maksimum DLC,
- informacja o zmiennym DLC,
- dla każdego obserwowanego bajtu:
  - liczba obecności i braków,
  - pierwsza i ostatnia wartość,
  - minimum i maksimum,
  - liczba różnych wartości,
  - liczba zmian,
  - częstotliwość zmian,
  - dokładne `source_row` pierwszej/ostatniej/minimalnej/maksymalnej obserwacji,
- dla każdego bitu:
  - liczba stanów 1 i 0,
  - udział stanu 1,
  - liczba przejść,
  - częstotliwość przejść,
  - informacja o stałości bitu.

Przy zmiennym DLC brak bajtu przerywa ciągłość obserwacji. CRT nie liczy sztucznego przejścia wartości ani bitów pomiędzy dwiema ramkami rozdzielonymi ramką, w której dany bajt nie istniał.

### 2.3. Arbitrary Bitfield Inspector / Plotter

Użytkownik może ręcznie ustawić:

- `start_bit`,
- długość 1–64 bitów,
- Intel / little endian,
- Motorola / big endian,
- signed / unsigned,
- scale,
- offset.

Semantyka Motoroli korzysta z numeracji CANdb++/DBC saw-tooth. Dekoder nie wymaga wcześniejszej definicji DBC.

### 2.4. Wykres

Wykres pokazuje wartości wybranego bitfielda w czasie.

Aby zachować bounded model GUI:

- pełne statystyki aktywności są liczone na **wszystkich** pasujących ramkach,
- do artefaktu wykresu przechowywana jest deterministyczna, równomierna próbka do 5000 pasujących ramek,
- każda próbka zachowuje dokładne:
  - `source_row`,
  - `sequence`,
  - `timestamp_ns`,
  - DLC,
  - payload.

### 2.5. Nawigacja dowodowa

Nawigacja MIN/MAX oraz z punktu wykresu używa istniejącego `StoredSearchNavigator` i dokładnego `source_row`.

CRT nie wyszukuje ponownie CAN ID w celu znalezienia „podobnej” ramki. Wynik prowadzi do dokładnego dowodu, który został zapisany podczas analizy.

---

## 3. Architektura

### Backend

Nowy provider:

`app/extensions/builtin/signal_discovery.py`

Provider ID:

`crt.analysis.signal_discovery_activity`

Typ:

`ExtensionType.ANALYSIS`

Uprawnienia:

- `PROJECT_READ`,
- `SESSION_READ`,
- `ARTIFACT_WRITE`.

Provider korzysta z istniejącego `AnalysisContext` i `FrameQuery`. Nie powstaje osobny system odczytu sesji.

### Trwały artefakt

Typ:

`signal_discovery_activity`

Schemat:

`crt.signal_discovery_activity` v1

Artefakt zawiera fingerprint źródłowej sesji, dokładny klucz wiadomości, pełne statystyki aktywności i bounded próbkę dowodową.

### GUI

Nowy widok:

`gui/signal_discovery_view.py`

Signal Discovery jest osobną kartą zapisanej sesji, ale korzysta z istniejącego `SessionAnalysisService`, artefaktów oraz bounded navigatora. Nie jest osobnym programem ani alternatywnym modelem danych.

---

## 4. Bezpieczeństwo i zachowane kontrakty

Stage 1 jest całkowicie pasywny.

Bez zmian pozostają:

- `CaptureService`,
- backend Kvaser i lifecycle CANlib,
- CAN TX/RX,
- format sesji i markerów,
- kolejność i kompletność surowych ramek,
- schemat indeksów,
- bounded/stronicowany model zapisanych sesji,
- `.crt/project.sqlite`.

Surowa sesja jest tylko odczytywana. Test GUI dodatkowo kontroluje SHA-256 pliku sesji przed i po analizie.

---

## 5. Testy

### Rdzeń

`tests/test_signal_discovery.py`

Zakres:

- Intel DBC LSB start bit,
- Motorola CANdb++ saw-tooth,
- signed Motorola,
- granice pól poza payloadem,
- scale/offset,
- zachowanie dokładnego `source_row`,
- STD/EXT jako oddzielne klucze,
- zmienny DLC,
- continuity-aware transition rate,
- bounded sample.

`tests/test_session_analysis_service.py`

Sprawdza rejestrację Signal Discovery jako zaufanego built-in providera.

### Produkcyjny GUI smoke

`tests_gui/signal_discovery_smoke.py`

Przepływ:

`projekt → zapisana sesja → Signal Discovery → analiza 0x123 → Activity Map → bitfield plot → MIN/MAX → dokładny source_row`

Smoke sprawdza także:

- komplet B7…B0 w tabeli,
- SHA-256 źródłowej sesji bez zmian,
- dokładną nawigację z punktu wykresu.

### Dedykowany workflow

`.github/workflows/signal-discovery-stage1.yml`

Nazwa:

`Signal Discovery Stage 1 Validation`

Platforma:

`windows-latest`

Windows self-hosted nie jest wymagany, ponieważ etap nie korzysta z fizycznego Kvasera i nie wykonuje CAN TX/RX.

---

## 6. Błąd wykryty przez pierwszą walidację

Pierwszy Windows checkpoint wykrył nie błąd dekodera, lecz błędne założenie testu Motoroli.

Dla CANdb++ saw-tooth:

`start_bit=0, length=9`

jest poprawne, ponieważ po bicie 0 bieżącego bajtu następny bit znajduje się w pozycji 7 kolejnego bajtu.

Test został poprawiony zgodnie z semantyką DBC. Dekoder nie został zmieniony pod błędne oczekiwanie testu.

---

## 7. Aktualizacja Help Center

Dodano temat:

`signal-discovery — Signal Discovery — aktywność bitów i ręczny bitfield`

Artykuł opisuje:

- lokalizację funkcji,
- dokładny klucz wiadomości,
- Byte/Bit Activity Map,
- Intel i Motorola,
- signed/unsigned,
- scale/offset,
- różnicę między pełną statystyką a bounded próbką 5000,
- evidence navigation do `source_row`,
- pasywny charakter funkcji,
- ograniczenia Stage 1.

Smoke Help Center sprawdza wyszukiwanie i otwarcie nowego artykułu.

---

## 8. Świadomie poza zakresem Stage 1

Ten etap nie implementuje jeszcze:

- Experiment Diff / korelacji markerów,
- automatycznego Signal Candidate Engine,
- detekcji rolling counter / checksum / CRC candidate,
- Signal Hypothesis,
- Draft DBC,
- Heavy-Duty Passive Discovery,
- aktywnego UDS/J1939 discovery,
- żadnego automatycznego TX.

---

## 9. Warunek zamknięcia etapu

Przed uznaniem Stage 1 za ręcznie zaakceptowany wymagane są:

1. zielony dedykowany Windows CI na końcowym HEAD,
2. zielone właściwe regresje CRT,
3. ręczny test użytkownika na Windows z rzeczywistą zapisaną sesją,
4. potwierdzenie czytelności Activity Map i wykresu,
5. potwierdzenie MIN/MAX oraz punkt → dokładna ramka,
6. ręczne sprawdzenie artykułu Help Center.

PR #61 pozostaje draftem. Nie wykonywać merge ani nie oznaczać jako ready bez osobnej, jednoznacznej zgody właściciela.
