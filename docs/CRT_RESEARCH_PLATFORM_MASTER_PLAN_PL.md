# CAN Research Tool — master plan platformy badawczej

## Status dokumentu

Ten dokument opisuje **docelową organizację, zasady architektoniczne i kierunek rozwoju CAN Research Tool**. Nie oznacza, że wszystkie wymienione funkcje są już zaimplementowane.

Plan stanowi podstawę do projektowania kolejnych etapów bez przypadkowego rozbudowywania GUI, bez tworzenia odseparowanych funkcji oraz bez uzależniania aplikacji od pojedynczego dostawcy sprzętu, dekodera albo modelu AI.

Najważniejsza decyzja organizacyjna:

> **Jeden projekt CRT dotyczy jednego badanego ECU.**

Projekt nie jest pojedynczym logiem. Jest kompletną, przenośną teczką badawczą konkretnego sterownika, zawierającą sesje, profil ECU, obszary badań, zestawy porównawcze, wyniki analiz, odzyskane payloady, hipotezy, dekodery, filtry, wzorce, scenariusze, raporty oraz historię badań.

---

# 1. Główne zasady architektoniczne

## 1.1. Jeden projekt = jedno ECU

Przykłady projektów:

- `DAF ETC3 — ECU 001`,
- `Scania S8 — sterownik przed i po naprawie`,
- `Mercedes MCM D3.2 — analiza protokołu`,
- `Cummins CM2350 — procedury programowania`.

W projekcie mogą znajdować się liczne sesje wykonane:

- przed naprawą,
- po naprawie,
- przy różnych konfiguracjach stanowiska,
- z różnymi wersjami oprogramowania,
- z udaną i nieudaną procedurą,
- przy różnych temperaturach i napięciach,
- w różnych obszarach badawczych,
- na różnych kanałach CAN,
- z różnymi wersjami dekoderów i reguł.

## 1.2. Surowe dane pozostają źródłem prawdy

Surowe ramki i oryginalne pliki sesji są niezmiennym materiałem źródłowym.

Filtry, grupowanie, DBC, dekodery, rekonstrukcja protokołów, analiza statystyczna, wzorce oraz CAN Intelligence Engine tworzą wyłącznie warstwy interpretacji.

Żaden moduł analityczny ani model AI nie może po cichu modyfikować materiału wejściowego.

## 1.3. Analizy tworzą trwałe artefakty

Wynik analizy nie powinien istnieć wyłącznie jako chwilowo otwarte okno.

Każda istotna analiza może utworzyć zapisany artefakt zawierający:

- źródłową sesję lub zestaw sesji,
- zakres wykorzystanych ramek,
- parametry analizy,
- wersję algorytmu,
- wersję modułu,
- wersję wzorców,
- wynik,
- poziom pewności,
- ostrzeżenia,
- pliki wynikowe,
- datę wykonania,
- autora lub operatora,
- odniesienia do dowodów.

## 1.4. Funkcje pasywne i aktywne są rozdzielone

Pasywny pomiar, analiza zapisanych sesji i funkcje generujące ruch CAN muszą być logicznie i wizualnie oddzielone.

Transmisja aktywna nie może uruchamiać się automatycznie ani być ukrytym skutkiem otwarcia analizy.

## 1.5. Pełny zapis jest niezależny od prezentacji

Filtry, pauza widoku, grupowanie po CAN ID, ograniczony bufor GUI, statystyki, analizy oraz AI nie mogą wpływać na kompletność i kolejność pełnego zapisu surowych ramek.

## 1.6. CRT jest platformą rozszerzalną

Nowe funkcje powinny być dodawane jako rejestrowane moduły korzystające ze stabilnego API, a nie przez dopisywanie kolejnych wyjątków do głównego okna.

Dotyczy to między innymi:

- filtrów,
- analiz,
- wzorców,
- dekoderów,
- porównań,
- rekonstruktorów transferów,
- eksporterów,
- reguł Intelligence,
- dostawców AI,
- scenariuszy aktywnych.

## 1.7. AI jest warstwą wspomagającą, nie źródłem prawdy

AI może tworzyć hipotezy, objaśnienia, propozycje filtrów, wzorców i kolejnych kroków badania.

AI nie może:

- zmieniać surowych danych,
- oznaczać hipotezy jako potwierdzonej bez decyzji użytkownika,
- wysyłać ramek CAN bezpośrednio,
- uruchamiać scenariuszy aktywnych,
- zastępować deterministycznego dekodera,
- ukrywać ramek będących podstawą wniosku.

---

# 2. Docelowa struktura projektu

```text
PROJEKT ECU
├── Przegląd
├── Profil ECU
├── Live Capture
├── Sesje
├── Obszary badań
├── Zestawy porównawcze
├── Analizy
├── Payloady i transfery
├── Znaleziska
├── Wzorce
├── Scenariusze testowe
├── Filtry
├── Dekodery
├── Reguły Intelligence
├── Asystent AI
├── Notatki i załączniki
└── Raporty
```

## 2.1. Profil ECU

Centralna karta badanego sterownika powinna przechowywać między innymi:

- producenta,
- rodzinę i model,
- numer części,
- numer seryjny,
- VIN,
- wersję HW,
- wersję SW,
- typ procesora,
- znane pamięci,
- liczbę kanałów CAN,
- znane bitrate,
- adresy diagnostyczne,
- stan sterownika,
- datę przyjęcia,
- operatora,
- zdjęcia i załączniki,
- uwagi.

Dane profilu mogą pochodzić z trzech źródeł:

1. wpis użytkownika,
2. potwierdzony odczyt diagnostyczny,
3. automatyczna hipoteza CRT lub AI.

Automatycznie rozpoznane informacje muszą pozostać hipotezami do czasu potwierdzenia.

## 2.2. Sesje

Sesja jest niezmiennym zapisem jednego pomiaru.

Każda sesja powinna posiadać metadane laboratoryjne:

- nazwę,
- datę i czas,
- operatora,
- cel badania,
- stan ECU,
- interfejs Kvaser,
- kanał,
- bitrate,
- tryb BENCH lub LISTEN ONLY,
- wersję CRT i commit aplikacji,
- aktywne dekodery,
- aktywne reguły,
- konfigurację stanowiska,
- napięcie zasilania,
- temperaturę, jeżeli jest dostępna,
- uwagi.

## 2.3. Obszary badań

Obszary badań organizują materiał merytorycznie, a nie według typu pliku.

Przykład dla ETC3:

```text
SecurityAccess
├── seed-key poprawny
├── InvalidKey
├── lockout
└── próba po czasie oczekiwania

Programowanie
├── RequestDownload
├── TransferData
├── TransferExit
└── RoutineControl

CBL READ
├── READ83
├── READ85 bank0
├── READ85 bank1
└── porównanie indeksów
```

Jedna sesja może należeć do kilku obszarów badań.

## 2.4. Zestawy porównawcze

Zestaw porównawczy jest trwałym obiektem wskazującym wiele sesji bez kopiowania ich danych.

Przykład:

```text
Nazwa: Scania S8 — przed i po naprawie

Sesja bazowa:
- przed naprawą

Sesje porównywane:
- po wymianie elementów
- po programowaniu
- po teście termicznym
```

Zestaw przechowuje:

- identyfikatory sesji,
- sesję bazową,
- sposób synchronizacji,
- parametry porównania,
- zapisane wyniki analiz.

## 2.5. Analizy i artefakty

Typowe artefakty:

- statystyka sesji,
- profil czasowy,
- oś zdarzeń,
- raport protokołu,
- odzyskany payload,
- porównanie sesji,
- odcisk ECU,
- wykryta anomalia,
- znalezisko Intelligence,
- raport AI,
- raport naprawy.

## 2.6. Znaleziska

Znalezisko jest trwałą hipotezą lub potwierdzonym wnioskiem wynikającym z analizy.

Statusy:

- `Hipoteza`,
- `Do sprawdzenia`,
- `Częściowo potwierdzone`,
- `Potwierdzone`,
- `Odrzucone`.

Znalezisko powinno zawierać:

- opis,
- typ,
- czas lub zakres czasu,
- odwołania do ramek i wiadomości,
- algorytm i jego wersję,
- model AI i jego wersję, jeżeli uczestniczył,
- poziom pewności,
- dowody,
- wątpliwości,
- komentarz użytkownika.

---

# 3. Cztery główne tryby pracy CRT

## 3.1. Pomiar i rejestracja

Kvaser jest traktowany jako silnik pomiarowy, a CRT zarządza eksperymentem.

Zakres docelowy:

- wykrywanie interfejsów i kanałów,
- rozpoznawanie bitrate,
- tryby BENCH i LISTEN ONLY,
- bieżące statystyki magistrali,
- znaczniki,
- wyzwalacze,
- pełny zapis surowych ramek,
- rekonstrukcja wiadomości logicznych,
- analiza czasowa,
- rejestr laboratoryjny.

## 3.2. Analiza pojedynczej sesji

Każdy log otrzymuje dostęp do wszystkich modułów analizy pojedynczej sesji.

Moduły niepasujące do zawartości sesji pozostają nieaktywne albo informują, że nie znaleziono odpowiednich danych.

## 3.3. Analiza wielu sesji

Wybrane sesje są łączone w zestaw porównawczy.

Analizy mogą obejmować:

- różnice CAN ID,
- różnice PGN,
- różnice payloadów,
- różnice częstotliwości i jitteru,
- różnice czasów odpowiedzi,
- zmiany DTC,
- różnice sekwencji UDS,
- transfery obecne tylko w części sesji.

## 3.4. Laboratorium aktywne

Oddzielony moduł do kontrolowanej transmisji:

- ręczne wysyłanie ramek,
- transmisja cykliczna,
- odtwarzanie logów,
- generowanie PGN,
- symulowanie czujników i elementów wykonawczych,
- scenariusze UDS,
- reakcje warunkowe,
- emulacja urządzeń CAN.

---

# 4. Widok pojedynczej sesji

Po otwarciu sesji użytkownik powinien otrzymać jeden spójny obszar roboczy:

```text
Sesja: ETC3_security_access_ok

[Podsumowanie]
[Surowe ramki]
[Wiadomości logiczne]
[Oś czasu]
[Statystyki]
[Analiza czasowa]
[Protokoły]
[Transfery i payloady]
[Znaczniki]
[Znaleziska]
[Asystent AI]
[Notatki]
```

## 4.1. Podsumowanie

Automatyczna karta sesji:

- czas rozpoczęcia i zakończenia,
- liczba ramek,
- liczba CAN ID,
- bitrate,
- kanał,
- obciążenie magistrali,
- rozpoznane protokoły,
- liczba wiadomości UDS,
- liczba błędów,
- wykryte transfery,
- aktywne znaczniki,
- najważniejsze wnioski.

## 4.2. Surowe ramki

Podstawowe sposoby prezentacji:

- lista chronologiczna,
- grupowanie po CAN ID.

Planowane rozszerzenia:

- podświetlanie zmieniających się bajtów,
- wykrywanie pól stałych i zmiennych,
- licznik wystąpień,
- okres wiadomości,
- jitter,
- możliwe liczniki,
- możliwe sumy kontrolne.

## 4.3. Wiadomości logiczne

Wspólna prezentacja semantyczna:

- RAW,
- J1939,
- J1939 TP,
- ISO-TP,
- UDS,
- DBC,
- protokoły autorskie,
- reguły użytkownika.

## 4.4. Oś czasu

Oś czasu łączy surowe dane z interpretacją wysokiego poziomu.

```text
00.000 s  ECU rozpoczęło transmisję
01.253 s  DiagnosticSessionControl 0x10 03
01.267 s  Pozytywna odpowiedź 0x50 03
02.013 s  SecurityAccess request-seed
02.021 s  Seed: 5A 19 4C 00
02.145 s  SecurityAccess send-key
02.153 s  Dostęp przyznany
03.400 s  RequestDownload
03.430 s  Rozpoczęcie TransferData
```

---

# 5. Automatyczne rozpoznawanie sieci CAN

Po podłączeniu ECU kreator pomiaru może wykonać:

1. wykrycie dostępnych interfejsów,
2. wykrycie kanałów,
3. pasywne sprawdzenie bitrate,
4. ocenę obciążenia magistrali,
5. wykrycie aktywnych CAN ID,
6. rozpoznanie wzorców J1939, ISO-TP, UDS i CANopen,
7. wskazanie prawdopodobnych adresów diagnostycznych,
8. utworzenie profilu sieci ECU.

Rozpoznawanie bitrate powinno rozpoczynać się pasywnie. Aktywne sondowanie musi być jawnie włączone i oznaczone jako transmisja.

```text
Profil sieci ECU

Kanał 0
Bitrate: 250 kbit/s
Format dominujący: EXT
Prawdopodobny J1939: tak
Adres ECU diagnostycznego: 0x00
Adres testera: 0xF9
Wykryte odpowiedzi UDS: tak
Obciążenie magistrali: 7,8%
```

---

# 6. Inteligentny analizator ramek

CRT nie powinien zatrzymywać się na wyświetlaniu surowych bajtów.

Przykład dla J1939:

```text
Ramka 18FEF100
↓
J1939 PGN 65265
↓
rozpoznana wiadomość lub sygnał
↓
wartość zmieniła się
↓
oznacz jako istotną zmianę
```

Przykład dla UDS:

```text
10 03
↓
DiagnosticSessionControl

22 F1 90
↓
ReadDataByIdentifier — VIN

27 07
↓
SecurityAccess — request seed
```

Analiza semantyczna musi zawsze prowadzić do ramek źródłowych.

---

# 7. Nagrywanie z wyzwalaczami

Wyzwalacze nie powinny domyślnie usuwać pełnego materiału źródłowego.

Preferowany model:

```text
Pełna sesja źródłowa
        +
automatyczne znaczniki
        +
wycięte klipy zdarzeń
```

Przykłady wyzwalaczy:

- pojawienie się SID `0x27`,
- pierwsze NRC `0x35`,
- określony CAN ID,
- payload lub maska,
- przekroczenie czasu odpowiedzi,
- zanik cyklicznej wiadomości,
- pojawienie się error frame,
- zmiana sygnału,
- rozpoczęcie RequestDownload.

```text
Dodaj znacznik
Zachowaj 10 sekund przed zdarzeniem
Zachowaj 20 sekund po zdarzeniu
Utwórz klip analityczny
Kontynuuj pełną sesję
```

Tryb zapisujący wyłącznie zdarzenia może istnieć jako świadomie wybrany tryb specjalny, ale nie powinien być domyślnym sposobem badań.

---

# 8. Statystyki magistrali

## 8.1. Statystyki na żywo

- wykorzystanie magistrali,
- liczba ramek na sekundę,
- liczba błędów,
- liczba aktywnych CAN ID,
- dominujące ID,
- rozkład STD i EXT,
- rozkład DLC,
- liczba wiadomości protokołowych,
- najbardziej aktywne adresy źródłowe,
- histogram priorytetów J1939.

## 8.2. Statystyki zapisanej sesji

- minimalna, średnia i maksymalna częstotliwość ID,
- udział procentowy każdego ID,
- okresowość wiadomości,
- zmienność payloadu,
- bajty stałe i zmienne,
- możliwe liczniki,
- możliwe sumy kontrolne,
- luki w komunikacji,
- okresy zwiększonej aktywności,
- nowe i zanikające ID.

Statystyki powinny działać zarówno dla pojedynczej sesji, jak i dla zestawu porównawczego.

---

# 9. Precyzyjna analiza czasowa

Analiza czasowa jest jednym z głównych wyróżników CRT.

## 9.1. Ramki CAN

- inter-frame spacing,
- częstotliwość wiadomości,
- jitter,
- minimalny i maksymalny okres,
- brakujące cykle,
- nagłe przerwy,
- kolejność ramek,
- korelacja czasowa pomiędzy ID.

## 9.2. UDS

Dla każdej pary request-response:

```text
Żądanie: 22 F1 90
Odpowiedź: 62 F1 90 ...
Czas odpowiedzi: 8,3 ms
```

Statystyki:

- minimum,
- maksimum,
- średnia,
- mediana,
- percentyle,
- timeouty,
- odpowiedzi pending `0x78`,
- liczba ponowień.

## 9.3. Wiele kanałów

Dla przyszłych interfejsów wielokanałowych:

- synchronizacja kanałów,
- korelacja zdarzeń,
- opóźnienia pomiędzy magistralami,
- wykrywanie przekazywania wiadomości przez gateway.

---

# 10. Automatyczne rozpoznawanie ECU

CRT może budować odcisk zachowania badanego sterownika na podstawie:

- numerów HW i SW,
- VIN,
- adresów diagnostycznych,
- PGN,
- CAN ID,
- odpowiedzi UDS,
- sekwencji startowych,
- częstotliwości ramek,
- charakterystycznych payloadów,
- zachowania SecurityAccess,
- sposobu programowania.

Wynik powinien być probabilistyczny i wyjaśnialny.

```text
Najbardziej prawdopodobna rodzina: Bosch EDC17

Pewność: 78%

Dowody:
- zgodny układ adresów diagnostycznych,
- zgodne DID HW/SW,
- 12 charakterystycznych CAN ID,
- zgodny wzorzec sesji programowania.

Niezgodności:
- brak oczekiwanego PGN,
- inny czas odpowiedzi SecurityAccess.
```

CRT nie może przedstawiać niepotwierdzonej klasyfikacji jako pewnego faktu.

---

# 11. Automatyczna analiza logów

Po zakończeniu sesji CRT może uruchomić zestaw nieinwazyjnych analiz.

```text
Wykryto 37 CAN ID.
5 identyfikatorów pojawiło się po uruchomieniu sesji diagnostycznej.
Rozpoznano 14 transakcji UDS.
Wykryto SecurityAccess poziomu 0x07/0x08.
Wystąpiła jedna odpowiedź InvalidKey NRC 0x35.
Wykryto RequestDownload pod adres 0x00A20000.
TransferData zawierał 37 bloków.
Odzyskano kandydat payloadu o długości 4590 bajtów.
```

Planowane moduły automatyczne:

- wykrycie nowych i zanikających CAN ID,
- analiza zmienności payloadów,
- klasyfikacja protokołów,
- analiza UDS,
- analiza J1939,
- wykrywanie transferów,
- analiza czasowa,
- wykrywanie anomalii,
- generowanie osi zdarzeń,
- tworzenie kandydatów znalezisk.

---

# 12. Porównywanie sesji

Typowe zastosowanie:

```text
ECU przed naprawą
vs
ECU po naprawie
```

CRT powinien wskazać:

- nowe i brakujące CAN ID,
- nowe i brakujące PGN,
- brakujące odpowiedzi,
- różnice czasów odpowiedzi,
- zmienione payloady,
- zmiany liczników,
- różnice częstotliwości,
- różnice jitteru,
- zmiany DTC,
- transfery obecne tylko w jednej sesji.

## 12.1. Synchronizacja logów

Sesje mogą mieć różną długość i różny moment rozpoczęcia.

Punkty synchronizacji:

- znacznik,
- pierwsze wystąpienie CAN ID,
- konkretna usługa UDS,
- włączenie zapłonu,
- określony payload,
- ręcznie wskazany czas.

---

# 13. Odzyskiwanie transferów i payloadów

Moduł powinien obsługiwać:

- UDS RequestDownload,
- UDS RequestUpload,
- TransferData,
- TransferExit,
- ISO-TP,
- J1939 TP,
- protokoły blokowe użytkownika,
- transfery wykrywane przez reguły.

Wynikiem nie jest wyłącznie plik BIN.

Każdy odzyskany payload powinien posiadać:

- nazwę,
- źródłową sesję,
- zakres ramek,
- CAN ID request i response,
- adres docelowy,
- deklarowaną długość,
- rzeczywistą długość,
- liczbę bloków,
- brakujące bloki,
- duplikaty,
- SHA-256,
- metodę rekonstrukcji,
- wersję algorytmu,
- poziom pewności,
- ostrzeżenia.

Artefakty wynikowe:

- `payload.bin`,
- widok HEX,
- mapa bloków,
- lista braków,
- raport rekonstrukcji,
- odwołania do ramek źródłowych.

Payload nie może zostać oderwany od informacji o swoim pochodzeniu.

---

# 14. CAN Intelligence Engine

CAN Intelligence Engine jest centralną warstwą tworzącą z danych pomiarowych wyjaśnialne wnioski.

Nie zastępuje surowych danych i nie ukrywa podstawy rozumowania.

```text
10 03
22 F1 90
27 07
27 08
34 00 44 ...
36 01 ...
36 02 ...
37
31 01 ...
```

Przykładowy opis semantyczny:

```text
Rozpoczęto rozszerzoną sesję diagnostyczną.
Odczytano identyfikator ECU.
Wykonano procedurę SecurityAccess.
ECU zaakceptowało klucz.
Rozpoczęto transfer danych do pamięci.
Przesłano kolejne bloki.
Zakończono transfer.
Uruchomiono procedurę przetwarzania lub wykonania danych.
```

Każdy wniosek musi zawierać:

- treść,
- typ,
- czas lub zakres czasu,
- odwołania do ramek,
- algorytm i jego wersję,
- poziom pewności,
- dowody,
- wątpliwości,
- status użytkownika.

```text
Możliwy payload wykonywany w RAM

Adres: 0x00A20000
Długość: 0x11EE
Pewność: 86%

Dowody:
- RequestDownload zawierał adres 0x00A20000,
- otrzymano pozytywną odpowiedź 0x74,
- TransferData przesłał 4590 bajtów,
- transfer zakończył się odpowiedzią 0x77,
- po transferze wykonano RoutineControl.
```

---

# 15. Generator ruchu CAN i scenariusze testowe

Laboratorium aktywne powinno obsługiwać:

- ręczne wysyłanie ramki,
- wysyłanie cykliczne,
- odtwarzanie logu,
- odtwarzanie wybranych ID,
- generowanie J1939 PGN,
- symulację sygnałów DBC,
- symulowanie EGR, VGT, BPV, SCR i czujników,
- scenariusze UDS,
- reakcje warunkowe.

```text
Po otrzymaniu PGN X:
    odczekaj 20 ms
    wyślij PGN Y

Co 100 ms:
    wyślij pozycję EGR

Po otrzymaniu UDS 22 F1 90:
    odpowiedz z zapisanym VIN
```

## 15.1. Zabezpieczenia

- transmisja domyślnie wyłączona,
- wyraźny wskaźnik trybu aktywnego,
- jawne potwierdzenie celu,
- ograniczenie do wskazanego kanału,
- limity częstotliwości,
- awaryjny przycisk STOP,
- brak automatycznego uruchamiania scenariusza,
- pełny log wysłanych ramek,
- odseparowanie od pasywnego CaptureService.

---

# 16. Rejestr laboratoryjny

Każda sesja powinna automatycznie zapisywać możliwie pełny kontekst eksperymentu:

```text
Projekt ECU
Operator
Data i czas
Stan ECU
Cel badania
Kvaser i numer kanału
Bitrate
Tryb elektryczny
Wersja CRT
Commit aplikacji
Aktywne filtry
Aktywne dekodery
Aktywne reguły
Konfiguracja stanowiska
VIN
HW
SW
Napięcie zasilania
Temperatura
Uwagi
```

W przyszłości dane mogą pochodzić również z:

- zasilacza laboratoryjnego,
- multimetru,
- oscyloskopu,
- czujnika temperatury,
- wejść cyfrowych,
- AirModule.

Celem jest możliwość odtworzenia warunków każdej analizy.

---

# 17. System rozszerzeń CRT

System rozszerzeń jest podstawą łatwego dodawania nowych funkcji bez przebudowy całej aplikacji.

## 17.1. Główna struktura

```text
CRT Core
├── Extension Registry
├── Filter Providers
├── Analysis Providers
├── Pattern Providers
├── Decoder Providers
├── Comparison Providers
├── Artifact Providers
├── Export Providers
├── AI Providers
└── Active Scenario Providers
```

`Extension Registry` odpowiada za:

- wykrywanie modułów,
- walidację manifestów,
- sprawdzanie wersji API,
- rejestrowanie możliwości,
- udostępnianie funkcji GUI,
- kontrolę zależności,
- wyłączanie niekompatybilnych rozszerzeń,
- raportowanie błędów ładowania.

## 17.2. Kontrakt modułu

Każdy moduł powinien deklarować:

```text
ID modułu
Nazwa
Wersja modułu
Wersja API CRT
Typ rozszerzenia
Obsługiwane źródła
Wymagane dane
Parametry wejściowe
Typ wyniku
Czy działa na żywo
Czy działa na jednej sesji
Czy działa na wielu sesjach
Czy korzysta z AI
Czy wymaga transmisji CAN
Wymagane uprawnienia
```

Przykład:

```text
ID: crt.analysis.uds_timing
Typ: analysis
Źródło: session, comparison_set
Wymagane dane: logical_messages.uds
Wynik: UdsTimingArtifact
Tryb Live: tak
AI: nie
CAN TX: nie
```

## 17.3. Typy rozszerzeń

### Filter Provider

Dostarcza:

- pola filtra,
- typy wartości,
- operatory,
- walidację,
- kompilację do deterministycznego predykatu,
- opis dla edytora GUI,
- opcjonalny podgląd wyniku.

Przykładowe przyszłe filtry:

- częstotliwość CAN ID,
- jitter,
- zmiana konkretnego bajtu,
- wykryty licznik,
- UDS SID,
- NRC,
- adres pamięci,
- typ transferu,
- status znaleziska,
- wynik modułu analizy.

GUI nie powinno mieć wszystkich pól wpisanych na stałe. Powinno pobierać definicje z rejestru filtrów.

### Analysis Provider

Otrzymuje jawny kontekst analizy i tworzy wersjonowany artefakt.

Przykłady:

- statystyki CAN ID,
- analiza jitteru,
- czasy odpowiedzi UDS,
- wykrywanie liczników,
- wykrywanie sum kontrolnych,
- rekonstrukcja TransferData,
- korelacja ramek,
- wykrywanie anomalii.

### Pattern Provider

Dostarcza pakiety wiedzy i sygnatury:

- konkretne rodziny ECU,
- wzorce SecurityAccess,
- procedury programowania,
- sekwencje startowe,
- charakterystyczne DID,
- charakterystyczne PGN,
- sygnatury transferów,
- reguły czasowe.

Pakiet wzorca może dotyczyć na przykład:

```text
Bosch EDC17
Mercedes MCM
DAF ETC3
Cummins CM2350
SecurityAccess
RequestDownload
J1939 DM1
niestandardowy bootloader
```

Aktualizacja wiedzy o ECU nie powinna wymagać modyfikacji głównego kodu CRT.

### Decoder Provider

Obsługuje:

- DBC,
- J1939,
- ISO-TP,
- UDS,
- protokoły producenta,
- formaty blokowe,
- reguły użytkownika.

### Comparison Provider

Dostarcza określony rodzaj porównania wielu sesji:

- CAN ID,
- payloady,
- częstotliwości,
- czasy odpowiedzi,
- osie zdarzeń,
- protokoły,
- transfery,
- zachowanie ECU przed i po naprawie.

### Artifact Provider

Definiuje trwałe wyniki, ich schemat, prezentację, eksport i migrację wersji.

### Export Provider

Pozwala dodawać eksporty bez zmian w głównym GUI:

- CSV,
- JSON,
- raport Markdown,
- raport PDF,
- BIN,
- paczka dowodowa,
- formaty kompatybilne z innymi narzędziami.

### Active Scenario Provider

Definiuje funkcje aktywne, ale zawsze podlega osobnym zabezpieczeniom transmisji.

## 17.4. Struktura rozszerzenia

Docelowy pakiet może wyglądać tak:

```text
extensions/
└── uds_timing/
    ├── manifest.json
    ├── provider.py
    ├── schemas.py
    ├── ui.py
    ├── migrations.py
    ├── tests/
    └── README.md
```

Przykładowy manifest:

```json
{
  "id": "crt.analysis.uds_timing",
  "name": "UDS Response Timing",
  "version": "1.0.0",
  "crt_api": "1",
  "type": "analysis",
  "inputs": ["session", "comparison_set"],
  "outputs": ["uds_timing_artifact"],
  "live_supported": true,
  "requires_ai": false,
  "requires_can_tx": false
}
```

## 17.5. Stabilne API rozszerzeń

Rozszerzenia nie powinny importować przypadkowych klas GUI ani wewnętrznych implementacji bazy danych.

Powinny korzystać wyłącznie ze stabilnych kontraktów, na przykład:

```text
ProjectContext
SessionSource
FrameQuery
LogicalMessageQuery
AnalysisContext
ComparisonContext
ArtifactWriter
FindingWriter
FilterFieldRegistry
PatternRegistry
ExtensionManifest
CancellationToken
ProgressReporter
```

Dzięki temu przebudowa GUI, sposobu przechowywania indeksu lub kontrolerów nie zniszczy wszystkich modułów.

## 17.6. Rejestrowanie funkcji w GUI

Moduł deklaruje, gdzie jest dostępny:

- akcja dla pojedynczej sesji,
- akcja dla zestawu porównawczego,
- zakładka Live,
- panel projektu,
- menu kontekstowe,
- kreator filtra,
- kreator raportu.

Główne GUI generuje odpowiednie akcje na podstawie rejestru, zamiast posiadać listę funkcji wpisaną na stałe.

## 17.7. Izolacja i niezawodność

Błąd rozszerzenia nie może zatrzymać CaptureService ani uszkodzić projektu.

Wymagania:

- jawne granice wyjątków,
- możliwość wyłączenia modułu,
- anulowanie długich analiz,
- limit pamięci i czasu dla zadań,
- wykonanie analiz poza wątkiem GUI,
- atomowy zapis artefaktów,
- brak bezpośredniego zapisu do plików sesji,
- test zgodności z API CRT.

## 17.8. Wersjonowanie i migracje

Każdy moduł oraz każdy artefakt powinien zapisywać:

- wersję CRT,
- commit CRT,
- wersję API rozszerzeń,
- wersję modułu,
- wersję algorytmu,
- wersję wzorców,
- wersję schematu artefaktu,
- parametry wykonania.

Starsze artefakty powinny pozostać czytelne albo podlegać jawnej migracji.

---

# 18. Integracja z AI i ślad dowodowy

Integracja AI jest opcjonalną warstwą wspomagającą badania. CRT nie powinien zależeć od jednego konkretnego modelu ani dostawcy.

## 18.1. AI Provider

```text
AI Provider
├── model lokalny
├── usługa chmurowa
├── model firmowy
├── model wyspecjalizowany
└── tryb wyłączony
```

Wspólny interfejs może udostępniać:

```text
analyze_context()
explain_finding()
suggest_next_steps()
generate_report()
propose_filter()
propose_pattern()
propose_comparison()
propose_analysis()
```

CRT powinien móc zmienić dostawcę AI bez zmiany modelu projektu i formatu sesji.

## 18.2. AI Context Package

AI nie powinno automatycznie otrzymywać całego projektu ani niekontrolowanego eksportu wszystkich logów.

CRT tworzy jawny pakiet kontekstu:

```text
Profil ECU
Wybrane sesje
Zakresy czasu
Wybrane surowe ramki
Wiadomości logiczne
Statystyki
Znaczniki
Znaleziska
Transfery
Wyniki porównań
Aktywne dekodery
Wersje algorytmów
Pytanie użytkownika
```

Pakiet powinien zawierać:

- identyfikatory źródeł,
- zakresy ramek,
- informację o pominiętych danych,
- wersje dekoderów,
- wersje wzorców,
- SHA-256 artefaktów,
- ograniczenia kontekstu,
- zastosowaną anonimizację.

## 18.3. Prywatność danych

Projekt ECU może zawierać poufne dane:

- VIN,
- numery seryjne,
- oprogramowanie ECU,
- payloady,
- procedury producenta,
- dane klienta.

Przed wysłaniem do zewnętrznego AI użytkownik musi widzieć:

- jakie dane zostaną wysłane,
- do jakiego dostawcy,
- czy zawierają pliki binarne,
- czy zawierają VIN lub identyfikatory,
- jaki jest zakres sesji,
- czy zastosowano anonimizację.

Tryb lokalnego AI powinien być możliwy bez wysyłania danych poza stanowisko.

## 18.4. Wyniki AI jako hipotezy

AI nie zapisuje faktu. Tworzy `AI Finding`.

```text
Treść:
Prawdopodobnie wykonano transfer loadera do RAM.

Pewność AI:
74%

Źródła:
- sesja 17,
- ramki 2301–2417,
- artefakt TransferData 12,
- RequestDownload 0x00A20000.

Status:
Do sprawdzenia
```

Użytkownik może zmienić status na:

- `Potwierdzone`,
- `Odrzucone`,
- `Do sprawdzenia`,
- `Częściowo potwierdzone`.

## 18.5. Ślad dowodowy

Każda odpowiedź AI zapisana w projekcie powinna zawierać:

- dostawcę,
- identyfikator modelu,
- wersję modelu, jeżeli jest dostępna,
- datę wykonania,
- skrót pakietu kontekstu,
- źródłowe sesje,
- zakresy ramek,
- źródłowe artefakty,
- wygenerowaną treść,
- poziom pewności,
- status zatwierdzenia,
- komentarz operatora.

Wniosek musi prowadzić do konkretnych dowodów, a nie wyłącznie do tekstu wygenerowanego przez model.

## 18.6. AI jako kreator filtrów

Użytkownik może opisać filtr językiem naturalnym:

> Pokaż ramki z NRC 0x35, które wystąpiły po SecurityAccess.

Poprawny przepływ:

```text
Opis użytkownika
        ↓
AI proponuje standardowe drzewo filtra CRT
        ↓
Deterministyczny kompilator waliduje pola i operatory
        ↓
GUI pokazuje warunki użytkownikowi
        ↓
Użytkownik zatwierdza
        ↓
CRT stosuje filtr
```

AI nie wykonuje własnego filtrowania obok istniejącego silnika. Tworzy wyłącznie propozycję standardowej definicji.

## 18.7. AI jako kreator wzorców

AI może przygotować szkic wzorca na podstawie wybranych sesji:

- charakterystyczne CAN ID,
- powtarzalne sekwencje UDS,
- typowe czasy,
- DID,
- PGN,
- sygnatury payloadów,
- warunki pozytywne i negatywne.

Szkic musi zostać:

1. zapisany jako wersja robocza,
2. zwalidowany przez deterministyczne komponenty,
3. przetestowany na sesjach referencyjnych,
4. zatwierdzony przez użytkownika.

## 18.8. AI jako asystent analizy

AI może:

- objaśniać wybrane ramki,
- podsumowywać sesję,
- porównywać wyniki modułów,
- tworzyć opis osi zdarzeń,
- sugerować kolejne eksperymenty,
- wskazywać brakujące dane,
- przygotowywać raport techniczny,
- pomagać nawigować do dowodów.

AI powinno korzystać przede wszystkim z wyników deterministycznych modułów, a nie próbować samodzielnie interpretować milionów surowych ramek bez przygotowanego kontekstu.

## 18.9. AI i funkcje aktywne

AI musi być całkowicie oddzielone od bezpośredniego toru transmisji CAN.

Dopuszczalny przepływ:

```text
AI proponuje scenariusz
        ↓
CRT waliduje składnię i ograniczenia
        ↓
Użytkownik przegląda ramki, czasy i warunki
        ↓
Użytkownik jawnie zatwierdza
        ↓
Moduł aktywny wykonuje scenariusz
```

Niedopuszczalne:

```text
AI → bezpośrednie wysyłanie CAN
```

## 18.10. Powtarzalność analiz AI

Ponieważ wyniki modeli mogą się zmieniać, zapis powinien utrwalać:

- dokładny kontekst,
- parametry zapytania,
- identyfikator modelu,
- wersję szablonu promptu,
- odpowiedź,
- datę,
- wynik walidacji.

Ponowne uruchomienie AI nie powinno po cichu nadpisywać wcześniejszego znaleziska. Powinno tworzyć nową wersję albo nowy przebieg analizy.

## 18.11. Deterministyczne algorytmy mają pierwszeństwo

Jeżeli deterministyczny dekoder ustalił:

- SID,
- DID,
- NRC,
- adres,
- długość,
- numer bloku,
- czas odpowiedzi,

to AI nie może zastępować tej wartości inną wartością bez jawnego wskazania konfliktu.

AI może wyjaśnić znaczenie albo zasugerować hipotezę, ale dane techniczne pochodzące z dekodera pozostają podstawą.

---

# 19. Docelowy Explorer projektu

```text
ETC3 — ECU 001
├── Przegląd
├── Profil ECU
├── Live Capture
├── Sesje
│   ├── 2026-07-06 seed-key OK
│   ├── 2026-07-06 InvalidKey
│   └── 2026-07-07 READ85
├── Obszary badań
│   ├── SecurityAccess
│   ├── Programowanie
│   └── CBL READ
├── Zestawy porównawcze
│   ├── Seed-key
│   └── Bank0 kontra Bank1
├── Analizy
│   ├── Statystyki
│   ├── Profile czasowe
│   └── Osie zdarzeń
├── Payloady i transfery
│   ├── A20000_11EE.bin
│   └── SFF reference
├── Znaleziska
│   ├── Możliwy loader RAM
│   └── Algorytm blokowania
├── Wzorce
├── Scenariusze
├── Filtry
├── Dekodery
├── Reguły Intelligence
├── Asystent AI
└── Raporty
```

---

# 20. Proponowana kolejność rozwoju

## Etap 1 — model organizacyjny projektu

Najpierw należy zaprojektować:

- profil jednego ECU,
- relacje sesji,
- obszary badań,
- zestawy porównawcze,
- analizy,
- artefakty,
- znaleziska.

Bez tego kolejne funkcje staną się niezależnymi ekranami bez wspólnego modelu danych.

## Etap 2 — fundament API rozszerzeń

Przed masowym dodawaniem nowych analiz należy przygotować:

- `Extension Registry`,
- manifest modułu,
- stabilne kontrakty danych,
- rejestr filtrów,
- rejestr analiz,
- rejestr wzorców,
- wersjonowanie artefaktów,
- izolację błędów modułów,
- test zgodności rozszerzeń.

## Etap 3 — statystyki i analiza czasowa

- statystyki pojedynczej sesji,
- obciążenie magistrali,
- częstotliwości,
- jitter,
- inter-frame spacing,
- czas odpowiedzi UDS,
- automatyczne podsumowanie logu.

Pierwsze moduły powinny zostać zbudowane przez nowe API rozszerzeń, aby stały się wzorcem dla kolejnych funkcji.

## Etap 4 — porównywanie sesji

- różnice CAN ID,
- różnice payloadów,
- różnice częstotliwości,
- różnice protokołów,
- synchronizacja logów,
- porównanie przed i po naprawie.

## Etap 5 — transfery i payloady

- wykrywanie transferów,
- rekonstrukcja payloadów,
- mapa bloków,
- kontrola kompletności,
- trwałe artefakty BIN i raporty.

## Etap 6 — CAN Intelligence Engine

- oś zdarzeń,
- hipotezy,
- wnioski semantyczne,
- znaleziska z dowodami,
- baza wzorców ECU.

## Etap 7 — kontrolowana integracja AI

- abstrakcja `AI Provider`,
- pakiet kontekstu,
- prywatność i anonimizacja,
- zapis śladu dowodowego,
- propozycje filtrów,
- propozycje wzorców,
- podsumowania i raporty,
- brak bezpośredniego dostępu do CAN TX.

## Etap 8 — automatyczne profilowanie sieci i ECU

- rozpoznawanie bitrate,
- adresy i protokoły,
- profil sieci,
- fingerprint ECU,
- profile porównawcze.

## Etap 9 — laboratorium aktywne

- generator ruchu,
- replay,
- scenariusze,
- emulacja urządzeń,
- automatyczne testy stanowiskowe.

---

# 21. Decyzja końcowa

Docelowy model CRT:

```text
JEDEN PROJEKT = JEDNO ECU

Sesje są niezmiennym materiałem źródłowym.

Każda sesja ma dostęp do wszystkich analiz pojedynczego logu.

Wiele sesji można łączyć w zestawy porównawcze.

Obszary badań grupują materiał tematycznie.

Analizy tworzą trwałe, wersjonowane artefakty.

Nowe filtry, analizy, dekodery, wzorce, porównania i eksportery
są rejestrowanymi modułami korzystającymi ze stabilnego API CRT.

CAN Intelligence Engine tworzy hipotezy z dowodami i poziomem pewności.

AI jest opcjonalną warstwą wspomagającą interpretację.

AI nie modyfikuje danych źródłowych, nie zastępuje deterministycznych
dekoderów i nie steruje bezpośrednio magistralą CAN.

Każdy wynik AI posiada źródła, dowody, wersję modelu
oraz status zatwierdzenia przez użytkownika.

Funkcje aktywne są fizycznie i logicznie oddzielone od pasywnego pomiaru.

Pełny surowy ruch CAN pozostaje źródłem prawdy.
```

Najbliższym krokiem projektowym powinno być przygotowanie modelu danych oraz stabilnych kontraktów dla:

- profilu ECU,
- zestawów porównawczych,
- uruchomień analiz,
- artefaktów,
- znalezisk,
- relacji z sesjami i obszarami badań,
- rejestru rozszerzeń,
- manifestów modułów,
- pakietów wzorców,
- przyszłych dostawców AI.

Dopiero na tym fundamencie należy budować pierwsze moduły statystyk i analizy czasowej.