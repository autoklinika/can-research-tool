# CAN Research Tool — master plan platformy badawczej

## Status dokumentu

Ten dokument opisuje **docelową organizację i kierunek rozwoju CAN Research Tool**. Nie oznacza, że wszystkie wymienione funkcje są już zaimplementowane.

Plan stanowi podstawę do projektowania kolejnych etapów bez przypadkowego rozbudowywania GUI i bez tworzenia odseparowanych funkcji, których później nie da się spójnie połączyć.

Najważniejsza decyzja organizacyjna:

> **Jeden projekt CRT dotyczy jednego badanego ECU.**

Projekt nie jest pojedynczym logiem. Jest kompletną, przenośną teczką badawczą konkretnego sterownika, zawierającą sesje, profil ECU, obszary badań, porównania, wyniki analiz, odzyskane payloady, hipotezy, dekodery, filtry, scenariusze i raporty.

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
- w różnych obszarach badawczych.

## 1.2. Surowe dane pozostają źródłem prawdy

Surowe ramki i oryginalne pliki sesji są niezmiennym materiałem źródłowym.

Filtry, grupowanie, DBC, dekodery, rekonstrukcja protokołów, analiza statystyczna i CAN Intelligence Engine tworzą wyłącznie warstwy interpretacji.

Żaden moduł analityczny nie może po cichu modyfikować materiału wejściowego.

## 1.3. Analizy tworzą trwałe artefakty

Wynik analizy nie powinien istnieć wyłącznie jako chwilowo otwarte okno.

Każda istotna analiza może utworzyć zapisany artefakt zawierający:

- źródłową sesję lub zestaw sesji,
- zakres wykorzystanych ramek,
- parametry analizy,
- wersję algorytmu,
- wynik,
- poziom pewności,
- ostrzeżenia,
- pliki wynikowe,
- datę wykonania.

## 1.4. Funkcje pasywne i aktywne są rozdzielone

Pasywny pomiar, analiza zapisanych sesji i funkcje generujące ruch CAN muszą być logicznie i wizualnie oddzielone.

Transmisja aktywna nie może uruchamiać się automatycznie ani być ukrytym skutkiem otwarcia analizy.

## 1.5. Pełny zapis jest niezależny od prezentacji

Filtry, pauza widoku, grupowanie po CAN ID, ograniczony bufor GUI oraz przyszłe statystyki nie mogą wpływać na kompletność i kolejność pełnego zapisu surowych ramek.

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
├── Scenariusze testowe
├── Filtry
├── Dekodery
├── Reguły Intelligence
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
3. automatyczna hipoteza CRT.

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
- raport naprawy.

## 2.6. Znaleziska

Znalezisko jest trwałą hipotezą lub potwierdzonym wnioskiem wynikającym z analizy.

Statusy:

- `Hipoteza`,
- `Do sprawdzenia`,
- `Potwierdzone`,
- `Odrzucone`.

Znalezisko powinno zawierać:

- opis,
- typ,
- czas lub zakres czasu,
- odwołania do ramek i wiadomości,
- algorytm i jego wersję,
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

Przykład:

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

Przykładowy wynik:

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

Przykładowe działanie:

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

Przykład:

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

Przykładowe podsumowanie:

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

Przykładowa sekwencja:

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

Przykładowe zaawansowane znalezisko:

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

Przykład scenariusza:

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

# 17. Modułowa architektura analiz

Każdy moduł analityczny powinien jawnie deklarować:

```text
Nazwa modułu
Obsługiwane źródła
Wymagane dane
Parametry wejściowe
Typ wyniku
Czy działa na żywo
Czy działa na jednej sesji
Czy działa na wielu sesjach
Czy wymaga transmisji
Wersja algorytmu
```

Przykład:

```text
Moduł: UDS Response Timing

Źródło:
- pojedyncza sesja
- zestaw porównawczy

Wejście:
- wiadomości UDS

Wynik:
- TimingProfile

Tryb aktywny:
- nie
```

Taki kontrakt pozwala dodawać kolejne funkcje bez przebudowy całego GUI.

---

# 18. Docelowy Explorer projektu

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
├── Scenariusze
├── Filtry
├── Dekodery
├── Reguły Intelligence
└── Raporty
```

---

# 19. Proponowana kolejność rozwoju

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

## Etap 2 — statystyki i analiza czasowa

- statystyki pojedynczej sesji,
- obciążenie magistrali,
- częstotliwości,
- jitter,
- inter-frame spacing,
- czas odpowiedzi UDS,
- automatyczne podsumowanie logu.

## Etap 3 — porównywanie sesji

- różnice CAN ID,
- różnice payloadów,
- różnice częstotliwości,
- różnice protokołów,
- synchronizacja logów,
- porównanie przed i po naprawie.

## Etap 4 — transfery i payloady

- wykrywanie transferów,
- rekonstrukcja payloadów,
- mapa bloków,
- kontrola kompletności,
- trwałe artefakty BIN i raporty.

## Etap 5 — CAN Intelligence Engine

- oś zdarzeń,
- hipotezy,
- wnioski semantyczne,
- znaleziska z dowodami,
- baza wzorców ECU.

## Etap 6 — automatyczne profilowanie sieci i ECU

- rozpoznawanie bitrate,
- adresy i protokoły,
- profil sieci,
- fingerprint ECU,
- profile porównawcze.

## Etap 7 — laboratorium aktywne

- generator ruchu,
- replay,
- scenariusze,
- emulacja urządzeń,
- automatyczne testy stanowiskowe.

---

# 20. Decyzja końcowa

Docelowy model CRT:

```text
JEDEN PROJEKT = JEDNO ECU

Sesje są niezmiennym materiałem źródłowym.

Każda sesja ma dostęp do wszystkich analiz pojedynczego logu.

Wiele sesji można łączyć w zestawy porównawcze.

Obszary badań grupują materiał tematycznie.

Analizy tworzą trwałe, wersjonowane artefakty.

CAN Intelligence Engine tworzy hipotezy z dowodami i poziomem pewności.

Funkcje aktywne są fizycznie i logicznie oddzielone od pasywnego pomiaru.

Pełny surowy ruch CAN pozostaje źródłem prawdy.
```

Najbliższym krokiem projektowym powinno być przygotowanie modelu danych dla:

- profilu ECU,
- zestawów porównawczych,
- uruchomień analiz,
- artefaktów,
- znalezisk,
- relacji z sesjami i obszarami badań.

Dopiero na tym fundamencie należy budować pierwsze moduły statystyk i analizy czasowej.
