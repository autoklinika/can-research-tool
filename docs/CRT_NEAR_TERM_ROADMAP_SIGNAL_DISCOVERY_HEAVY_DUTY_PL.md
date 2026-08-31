# CAN Research Tool — najbliższa droga rozwoju

## Signal Discovery + Heavy-Duty Diagnostic Discovery

Data decyzji: 2026-08-30

Status: **obowiązujący near-term roadmap CRT do dalszego rozwoju**

Ten dokument zapisuje aktualny, uzgodniony kierunek rozwoju CAN Research Tool po analizie aktualnego stanu CRT oraz rozwiązań dostępnych w konkurencyjnych narzędziach inżynierskich.

Nie zastępuje `CRT_RESEARCH_PLATFORM_MASTER_PLAN_PL.md`. Doprecyzowuje jednak **najbliższą kolejność prac i specjalizację produktu**. Jeżeli ogólny Master Plan dopuszcza wiele równoległych kierunków, ten dokument określa, które z nich mają pierwszeństwo w najbliższych etapach.

Najważniejsza decyzja produktowa:

> **CRT ma rozwijać się jako evidence-first CAN reverse-engineering workstation, szczególnie mocny w ECU ciężarówek, maszyn i systemów heavy-duty.**

CRT nie ma być kopią CANoe, Vehicle Spy, SavvyCAN ani ECU Platform. Ma prowadzić inżyniera od nieznanego ruchu CAN do zweryfikowanej wiedzy o sygnałach, protokołach i zachowaniu ECU, przy zachowaniu pełnego śladu dowodowego do surowych ramek.

---

# 1. Fundamenty, których nie wolno naruszać

W dalszym rozwoju obowiązują dotychczasowe kontrakty architektoniczne CRT:

1. **Jeden projekt CRT = jedno badane ECU.**
2. **Surowe ramki i oryginalne sesje są niezmiennym źródłem prawdy.**
3. Filtry, dekodery, DBC, porównania, wyniki discovery, hipotezy i AI tworzą wyłącznie warstwy interpretacji.
4. Każdy istotny wynik analizy powinien mieć możliwość zapisania jako trwały, wersjonowany artefakt.
5. Każdy ważny wniosek powinien zachowywać referencje do dokładnych dowodów, przede wszystkim `session_id + source_row`.
6. Funkcje pasywne i aktywne muszą być logicznie oraz wizualnie rozdzielone.
7. Żadna analiza, otwarcie projektu ani odtworzenie artefaktu nie może niejawnie generować transmisji CAN.
8. AI może pomagać w interpretacji i tworzeniu hipotez, ale nie może zastępować deterministycznej analizy ani ukrywać podstawy wniosku.
9. Najbliższe funkcje mają wykorzystywać istniejące Extension API i trwałe artefakty zamiast tworzyć osobne, izolowane narzędzia.
10. Aktualna platforma docelowa CRT pozostaje Windows zgodnie z obowiązującą polityką walidacji projektu.

---

# 2. Główna luka CRT: Signal Discovery Workspace

CRT potrafi już rejestrować, filtrować, dekodować i porównywać ruch CAN. Największą luką w codziennym reverse engineeringu jest obecnie warstwa pomagająca odpowiedzieć na pytanie:

> **Które bity lub pola w nieznanym CAN ID reprezentują badaną funkcję i jak to udowodnić?**

Dlatego pierwszym dużym kierunkiem ma być **Signal Discovery Workspace**.

## 2.1. Byte/Bit Activity Map

Po wybraniu dokładnego klucza wiadomości CRT powinien automatycznie pokazywać aktywność każdego bajtu i bitu:

- wartość ostatnią,
- minimum i maksimum,
- liczbę różnych wartości,
- częstotliwość zmian,
- udział czasu w stanie 0/1 dla bitów,
- pola stałe,
- pola zmienne,
- prawdopodobne flagi,
- prawdopodobne liczniki,
- możliwe pola wielobajtowe.

Przykład:

```text
CAN ID 0x18FF2700

DATA
12 7A 00 80 FF 03 A4 19

Byte 0   stały
Byte 1   zmienny
Byte 2   stały
Byte 3   2 aktywne bity
Byte 4   stały 0xFF
Byte 5   counter candidate
Byte 6-7 correlated field candidate
```

Widok ma posiadać mapę bitów, która pozwala natychmiast zobaczyć, które pozycje zmieniają się często, sporadycznie albo wcale.

## 2.2. Arbitrary Bitfield Plotter

Użytkownik powinien móc zaznaczyć dowolny zakres bitów i bez tworzenia DBC wyświetlić go jako:

- Intel / little endian,
- Motorola / big endian,
- signed,
- unsigned,
- różne długości pola,
- różne start-bit,
- wartość surową,
- opcjonalną skalę i offset.

Wykres musi wspierać:

- zoom,
- kursory czasu i wartości,
- nakładanie kilku kandydatów,
- znaczniki eksperymentu,
- przejście z punktu wykresu do dokładnej ramki źródłowej.

## 2.3. Signal Hypothesis

Wynik ręcznego lub automatycznego odkrycia nie staje się od razu „prawdą”. Powinien utworzyć obiekt hipotezy zawierający co najmniej:

- CAN ID i pełny klucz wiadomości,
- start bit,
- length,
- endianess,
- signed/unsigned,
- scale,
- offset,
- unit,
- nazwę roboczą,
- poziom pewności,
- sesje i eksperymenty użyte do oceny,
- dowody źródłowe,
- komentarz użytkownika,
- status: hipoteza / do sprawdzenia / częściowo potwierdzone / potwierdzone / odrzucone.

---

# 3. Experiment Diff i korelacja ze znacznikami

Drugim najbliższym modułem ma być **Experiment Diff**.

CRT ma wykorzystać swoją istniejącą przewagę: projekty ECU, wiele sesji, znaczniki, comparison sets, trwałe artefakty i dokładne `source_row`.

Przykład:

```text
Sesja A   EGR podłączony
Sesja B   EGR odłączony
Sesja C   EGR podłączony
Sesja D   EGR odłączony
```

Dla markerów operatora lub innych trwałych kotwic CRT powinien automatycznie analizować:

1. które CAN ID zmieniły zachowanie,
2. które bajty i bity zmieniły zachowanie,
3. które zmiany powtarzają się we wszystkich eksperymentach tego samego typu,
4. które zmiany nie występują w sesjach kontrolnych,
5. jaki jest czas reakcji względem markera,
6. jak stabilna jest korelacja,
7. czy zmiana jest chwilowa, trwała, monotoniczna, cykliczna czy binarna.

Docelowy przepływ:

```text
miliony ramek
    ↓
CAN ID zmieniające zachowanie
    ↓
bajty i bity skorelowane z eksperymentem
    ↓
kandydaci sygnałów
    ↓
statystyka + timing + dowody
```

Najważniejszy kontrakt:

> Wynik korelacji nie może być wyłącznie liczbą lub procentem. Musi prowadzić do dokładnych ramek i sesji będących podstawą wniosku.

---

# 4. Signal Candidate Engine

Kolejnym krokiem po Signal Discovery i Experiment Diff ma być deterministyczny **Signal Candidate Engine**.

Dla wybranego CAN ID lub zakresu bitów silnik powinien testować typowe interpretacje:

- unsigned 8/16/24/32,
- signed,
- Intel,
- Motorola,
- różne `start_bit` i `length`,
- bit flags,
- rolling counter,
- licznik modulo,
- BCD,
- ASCII,
- pole stałe,
- pole monotoniczne,
- prawdopodobny checksum / CRC candidate,
- prawdopodobne pola wielobajtowe.

Kandydaci mają być rankingowani na podstawie jawnych, deterministycznych cech, np.:

- korelacji ze znacznikiem lub eksperymentem,
- regularności zmian,
- rozkładu wartości,
- ciągłości,
- zachowania między sesjami,
- zgodności z oczekiwaną wielkością fizyczną, jeżeli użytkownik poda wzorzec referencyjny.

AI może później zasugerować znaczenie kandydata, ale nie może być źródłem samego rankingu dowodowego.

---

# 5. Draft DBC — domknięcie workflow RAW → wiedza

Po zweryfikowaniu hipotezy CRT powinien umożliwić bezpośrednie utworzenie roboczej definicji sygnału.

Docelowy przepływ:

```text
RAW
 ↓
Experiment Diff
 ↓
Signal Candidate
 ↓
Plot + verification
 ↓
Signal Hypothesis
 ↓
Confirmed Signal
 ↓
Draft DBC / Project DBC
```

Przykładowe dane sygnału:

```text
CAN ID       0x18FEEE00
Start bit    24
Length       16
Endian       Intel
Signed       no
Scale        0.125
Offset       0
Unit         rpm
```

Etap ma pozwolić najpierw zapisać sygnał jako **hipotezę**, a dopiero po ręcznym potwierdzeniu dodać go do projektowego DBC.

CRT nie powinien wymuszać przepisywania znalezionych parametrów do zewnętrznego programu.

---

# 6. Specjalizacja heavy-duty

CRT ma być szczególnie dobry przy pracy ze sterownikami:

- ciężarówek,
- autobusów,
- maszyn budowlanych,
- maszyn rolniczych,
- off-highway,
- przemysłowych systemów CAN wykorzystujących podobne stosy protokołów.

Dla tej klasy urządzeń podstawą discovery jest przede wszystkim poprawna analiza **29-bitowego CAN**.

---

# 7. Kluczowy kontrakt protokołowy dla truck: J1939 i UDS

To założenie jest krytyczne i obowiązuje wszystkie przyszłe moduły discovery.

## 7.1. Nie wolno traktować całego 29-bit CAN jako jednego J1939

Na tej samej magistrali 29-bitowej mogą współistnieć co najmniej dwa istotne stosy:

```text
29-bit CAN w truck
│
├── SAE J1939
│   ├── PGN
│   ├── SPN
│   ├── J1939 TP
│   └── J1939-73 diagnostics
│       ├── DM1
│       ├── DM2
│       └── ...
│
└── ISO-TP
    └── UDS
        ├── 0x10
        ├── 0x19
        ├── 0x22
        ├── 0x27
        ├── 0x31
        ├── 0x34
        └── ...
```

Praktycznie ruch UDS w ciężarówkach często występuje na tej samej fizycznej sieci CAN 29-bit używanej przez J1939 i używa adresowania wyglądającego „j1939-owo”. Nie oznacza to jednak, że UDS należy dekodować jako zwykły J1939 PGN.

## 7.2. ISO-TP normal-fixed / UDS candidate

Przykład:

```text
0x18DA00F1   tester → ECU
0x18DAF100   ECU → tester
0x18DB33F1   functional request candidate
```

Dla takich identyfikatorów CRT powinien rozpoznawać strukturę 29-bit ID i klasyfikować je jako kandydatów do:

```text
29-bit CAN
→ ISO-TP normal-fixed
→ UDS request/response candidate
```

Przykład analizy:

```text
0x18DAF100
Priority: 6
PF: 0xDA
Target: 0xF1
Source: 0x00

→ ISO-TP normal-fixed candidate
→ UDS physical response candidate
```

## 7.3. Native J1939

Identyfikatory należące do klasycznego ruchu J1939 powinny przechodzić przez ścieżkę:

```text
29-bit CAN
→ J1939 identifier
→ PGN
→ SPN / proprietary interpretation
```

Przykład:

```text
0x18FEEE00
→ J1939
→ PGN 0xFEEE
→ SPN decoding, jeżeli dostępna jest definicja
```

## 7.4. J1939 Transport Protocol

Identyfikatory:

```text
0x18ECxxxx
0x18EBxxxx
```

powinny być klasyfikowane odpowiednio jako:

```text
J1939 TP.CM
J1939 TP.DT
```

z rekonstrukcją BAM oraz RTS/CTS zgodnie z istniejącym pipeline CRT.

## 7.5. Zasada klasyfikacji

> **Sam fakt użycia 29-bitowego CAN ID nie wystarcza do zaklasyfikowania wiadomości jako J1939.**

CRT ma zachować konserwatywną klasyfikację i dopiero na podstawie struktury ID, transportu, kontekstu oraz dowodów wybrać J1939, ISO-TP/UDS albo `UNKNOWN`.

To jest twardy kontrakt dla wszystkich przyszłych modułów automatycznego discovery.

---

# 8. Heavy-Duty Passive ECU Discovery

Pierwszy etap discovery dla ciężarówek musi być całkowicie pasywny i nie generować TX.

CRT powinien budować profil obserwowanej sieci zawierający m.in.:

## 8.1. Warstwa CAN

- kanały,
- bitrate,
- STD/EXT,
- aktywne CAN ID,
- częstotliwości,
- timing i jitter,
- obciążenie magistrali,
- prawdopodobne źródła i cele.

## 8.2. J1939

- Source Address,
- Address Claimed,
- NAME,
- listę obserwowanych PGN,
- częstotliwości PGN,
- J1939 TP BAM,
- J1939 TP RTS/CTS,
- DM1/DM2 i pozostały ruch diagnostyczny,
- SPN/FMI, jeżeli są możliwe do interpretacji,
- proprietary PGN jako osobne obiekty do dalszego Signal Discovery.

## 8.3. ISO-TP / UDS

- potencjalne pary request/response,
- 11-bit i 29-bit normal-fixed,
- źródło i cel,
- kierunek,
- kompletność transportu,
- rozpoznane SID/DID/NRC/Routine ID,
- statystyki timingowe.

Passive Discovery ma tworzyć trwały artefakt profilu sieci/ECU oraz zachowywać dowody źródłowe.

---

# 9. Heavy-Duty Active Diagnostic Discovery

Dopiero po działającym Passive Discovery należy dodać osobny, jawnie aktywowany moduł transmisyjny.

## 9.1. Stan bezpieczeństwa

Interfejs musi wyraźnie rozróżniać:

```text
PASSIVE
```

od:

```text
ACTIVE ARMED
```

Uruchomienie aktywnego discovery wymaga świadomej akcji użytkownika.

## 9.2. Safe read-only defaults

Domyślna konfiguracja aktywnego skanu powinna:

- ograniczać częstotliwość zapytań,
- rozpoczynać od bezpiecznych usług odczytu,
- nie wykonywać automatycznie ECU Reset,
- nie wykonywać automatycznie funkcji zapisu,
- nie wykonywać automatycznie RequestDownload / TransferData,
- nie próbować automatycznie przełamywać SecurityAccess,
- posiadać jawny limit zakresu i czasu skanu.

## 9.3. UDS endpoint discovery

CRT powinien móc wykrywać:

- pary request/response,
- sposób adresowania,
- dostępność ISO-TP,
- UDS candidate / confirmed,
- timing odpowiedzi,
- funkcjonalne i fizyczne adresowanie.

Wynik powinien trafiać do trwałego profilu ECU.

---

# 10. UDS Service Map

Po wykryciu endpointu CRT powinien budować mapę usług, ale nie ograniczać się do prostego `TAK/NIE`.

Dla każdego SID należy zachować:

- sesję diagnostyczną,
- subfunction,
- request payload,
- positive response,
- negative response,
- NRC,
- `0x78 ResponsePending`,
- first response latency,
- final response latency,
- dokładne ramki źródłowe.

Przykład:

```text
0x34 RequestDownload

Default Session:
    NRC ...

Extended Session:
    NRC ...

Programming Session:
    NRC ...
```

Celem jest poznanie **struktury diagnostyki ECU**, a nie tylko wykrycie obecności SID.

---

# 11. Subservice i DID Discovery

Kolejne etapy powinny obejmować:

## 11.1. Subservice Discovery

Między innymi dla:

- DiagnosticSessionControl,
- ECUReset,
- SecurityAccess,
- CommunicationControl,
- RoutineControl,
- ControlDTCSetting.

Każdy wynik musi przechowywać odpowiedź, NRC i dowód.

## 11.2. DID Discovery

Dla `ReadDataByIdentifier` CRT powinien móc stworzyć trwałą mapę DID zawierającą:

- DID,
- status odpowiedzi,
- długość,
- payload,
- powtarzalność,
- candidate encoding,
- ASCII/BCD/raw confidence,
- zmianę wartości między sesjami,
- dowody źródłowe.

Znane DID-y, np. VIN albo identyfikatory HW/SW, mogą otrzymywać deterministyczne interpretacje. Nieznane DID-y powinny trafiać do dalszego Signal/Payload Discovery.

---

# 12. SecurityAccess — analiza struktury, nie automatyczne obchodzenie

CRT może badać strukturę SecurityAccess, w szczególności:

- dostępne level,
- długość seed,
- zmienność seed,
- timing,
- NRC,
- lockout,
- recovery time,
- różnice między sesjami diagnostycznymi.

Przykładowy artefakt:

```text
SecurityAccess Map

Level 01:
  seed request       supported
  seed length        4 B
  samples            20
  unique seeds       20/20
  lockout detected   yes
  NRC after failures ...
  recovery           ...
```

Near-term CRT **nie ma być automatycznym brute-forcerem ani narzędziem do obchodzenia zabezpieczeń**. Celem jest analiza zachowania diagnostycznego i tworzenie powtarzalnych dowodów badawczych.

---

# 13. J1939 Diagnostic Discovery

Równolegle z UDS CRT ma rozwijać heavy-duty discovery właściwe dla native J1939.

Docelowy profil powinien zawierać m.in.:

```text
J1939 ECU PROFILE

SA
NAME
Manufacturer
Function / Vehicle System

Observed PGNs
Requested PGNs
Transport usage
Diagnostics
```

Analiza ma obejmować:

- Address Claimed / NAME,
- PGN inventory,
- częstotliwości i timing,
- J1939 TP,
- DM1,
- DM2,
- kolejne istotne DM,
- SPN/FMI,
- różnice diagnostyczne między sesjami,
- proprietary PGN przekazywane do Signal Discovery.

---

# 14. DoIP i XCP — później, ale architektura ma je przewidywać

## 14.1. DoIP

Po ustabilizowaniu discovery na CAN należy dodać backend Ethernet i DoIP:

```text
Ethernet
→ DoIP discovery
→ routing activation
→ logical addresses
→ UDS
```

DoIP powinien korzystać z tych samych domenowych obiektów UDS Service Map, DID Map, timing, findings i evidence, zamiast tworzyć osobny świat diagnostyczny.

## 14.2. XCP

XCP/CCP pozostaje niższym priorytetem niż J1939, UDS i DoIP. Architektura Extension API ma jednak nie blokować późniejszego dodania measurement/calibration discovery.

---

# 15. Active Lab — po funkcjach discovery

Manual TX, cyclic TX, replay, scenariusze i symulacja ECU pozostają ważne, ale nie powinny wyprzedzić Signal Discovery.

Docelowo Active Lab obejmie:

- ręczne wysyłanie ramek,
- transmisję cykliczną,
- replay sesji,
- replay z triggerami,
- generowanie wiadomości J1939,
- scenariusze UDS,
- reakcje warunkowe,
- restbus / ECU simulation.

Active Lab musi być osobnym, jawnie uzbrojonym środowiskiem i nie może zmieniać zasad pasywnego Capture.

---

# 16. Kolejność najbliższych etapów

Aktualny priorytet rozwoju:

| Priorytet | Moduł | Cel |
|---|---|---|
| **P0.1** | **Signal Discovery Workspace** | bit/byte activity, arbitrary bitfield, ręczne odkrywanie sygnałów |
| **P0.2** | **Experiment Diff / marker correlation** | korelacja zmian z eksperymentem i kontrolą |
| **P0.3** | **Signal Plotter + cursors** | szybka weryfikacja hipotez na osi czasu |
| **P0.4** | **Signal Candidate Engine** | automatyczne testowanie interpretacji bitfieldów |
| **P0.5** | **Draft DBC / Signal Hypotheses** | domknięcie RAW → potwierdzony sygnał → DBC |
| **P1.1** | **Heavy-Duty Passive Discovery** | automatyczna mapa J1939 + ISO-TP/UDS bez TX |
| **P1.2** | **Heavy-Duty Active Diagnostic Discovery** | kontrolowane wykrywanie endpointów i usług |
| **P1.3** | **UDS Service/Subservice/DID Map** | trwała mapa diagnostyki ECU z NRC, timingiem i evidence |
| **P1.4** | **J1939 Diagnostic Discovery** | NAME/SA/PGN/DM/SPN/FMI i proprietary PGN |
| **P1.5** | **Active Lab: manual/cyclic TX + replay** | reprodukcja i kontrolowane eksperymenty |
| **P1.6** | **DoIP** | UDS po Ethernet dla nowszych ECU |
| **P1.7** | **import/export BLF/ASC/MF4/TRC itd.** | interoperacyjność z zewnętrznym ekosystemem |
| **P2** | scripting/scenarios | automatyzacja eksperymentów |
| **P2** | XCP/CCP | measurement/calibration discovery |
| **P2** | restbus / ECU simulation | emulacja węzłów i całych fragmentów sieci |
| **P2** | kolejne backendy CAN | PEAK, Vector, J2534 itd. |
| **Audit** | CAN FD | ustalić i udokumentować pełny zakres supportu |
| **Future** | CAN XL | niski priorytet dla obecnego obszaru badań |

---

# 17. Co ma wyróżniać CRT

CRT nie powinien próbować wygrać liczbą checkboxów z CANoe lub Vehicle Spy.

Przewagą ma być workflow badawczy:

```text
nieznany ECU
   ↓
pełny, niezmienny capture
   ↓
passive protocol discovery
   ↓
experiment + markers
   ↓
comparison / correlation
   ↓
bit / byte candidates
   ↓
signal candidates
   ↓
plots + timing
   ↓
source evidence
   ↓
hypothesis
   ↓
manual confirmation
   ↓
DBC / decoder / rule
```

Dla heavy-duty drugi równoległy workflow:

```text
29-bit CAN
   ↓
conservative classification
   ├── J1939 / J1939 TP / J1939-73
   ├── ISO-TP / UDS normal-fixed
   └── UNKNOWN
          ↓
   protocol-specific discovery
          ↓
   persistent ECU profile
          ↓
   exact evidence
```

---

# 18. Kryteria jakości przyszłych funkcji

Każdy nowy moduł z tego roadmapu powinien spełniać co najmniej:

1. Nie modyfikuje surowych sesji.
2. Nie zmienia kompletności ani kolejności Capture.
3. Działa poza wątkiem GUI dla kosztownych analiz.
4. Obsługuje anulowanie długich operacji.
5. Nie materializuje bez potrzeby pełnych wielomilionowych sesji w GUI.
6. Zachowuje deterministyczny wynik dla tych samych danych i parametrów tam, gdzie jest to możliwe.
7. Tworzy trwały artefakt dla ważnego wyniku.
8. Zachowuje fingerprint źródeł i wersję algorytmu.
9. Umożliwia przejście od wniosku do dokładnego `source_row`.
10. Jasno rozdziela hipotezę od potwierdzonego wniosku.
11. Aktywna transmisja wymaga jawnego uzbrojenia.
12. Nowa funkcja jest opisana w Help Center zgodnie z obowiązującą polityką CRT.
13. Walidacja produktu jest wykonywana na Windows; sprzętowe funkcje Kvaser wymagają właściwego testu stanowiskowego.

---

# 19. Aktualny punkt startowy

Dokument został utworzony względem `main`:

```text
f6c21c6ebd4da081035b1b2a671fccd1bee5ab0e
```

Na dzień utworzenia dokumentu istnieje również niezamergowany stack rozwojowy Comparison Visualization, zawierający m.in. dashboard porównań, trwałe wyrównanie osi czasu, timing/jitter oraz analizę transakcji i latencji UDS.

Te prace pozostają wartościowym fundamentem pod Experiment Diff i Heavy-Duty Diagnostic Discovery. Ten roadmap nie wykonuje ich merge ani nie zmienia ich statusu.

---

# 20. Najbliższy konkretny krok implementacyjny

Po zatwierdzeniu tego roadmapu pierwszym nowym etapem funkcjonalnym powinien być:

> **Signal Discovery Workspace Stage 1 — Byte/Bit Activity Map + ręczny Arbitrary Bitfield Inspector/Plotter, z pełnym evidence navigation do `source_row`.**

Stage 1 nie powinien jeszcze automatycznie zgadywać znaczenia sygnału ani tworzyć DBC. Najpierw należy zbudować deterministyczny, szybki i wygodny warsztat do ręcznego odkrywania bitów i pól, na którym później oprzemy Experiment Diff i Signal Candidate Engine.

---

## Decyzja końcowa

Najbliższa droga rozwoju CRT jest świadomie ustawiona na dwa silnie powiązane cele:

1. **odkrywanie znaczenia nieznanych danych CAN na podstawie eksperymentów i dowodów**, oraz
2. **profesjonalne discovery diagnostyki ECU heavy-duty z poprawnym rozróżnieniem J1939 native diagnostics i ISO-TP/UDS na 29-bit CAN**.

To ma być specjalizacja CRT i punkt odniesienia dla kolejnych etapów projektu.
