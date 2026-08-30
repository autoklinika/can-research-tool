# CRT Help Center Stage 1 — raport końcowy

## 1. Cel etapu

Celem etapu było dodanie do CAN Research Tool obszernej, lokalnej i
przeszukiwalnej zakładki `Pomoc`, opisującej funkcje programu, typowe przepływy
pracy, ograniczenia techniczne oraz zasady bezpiecznej interpretacji wyników.

Pomoc ma działać również wtedy, gdy żaden projekt nie jest otwarty. Nie może
skanować sesji, korzystać z sieci ani modyfikować danych projektu.

## 2. Domknięcie wcześniejszej pracy

Przed rozpoczęciem Help formalnie zapisano ręczne potwierdzenie Stage 2D1 i
punkt późniejszej kontynuacji.

Końcowy funkcjonalny checkpoint Stage 2D1:

`305bd57bdb863f5e2b498b7673e5ae017cc125dc`

Dokument zamknięcia:

`docs/reports/COMPARISON_VISUALIZATION_STAGE2D1_MANUAL_ACCEPTANCE_AND_HELP_HANDOFF_PL.md`

Po zakończeniu Help rozwój porównań ma wrócić dokładnie do:

`Comparison Visualization Stage 2D2 — transakcje UDS na trwałej osi czasu`

## 3. Dostarczony interfejs

### 3.1 Globalne wejście do Pomocy

Dodano menu `Pomoc` zawierające:

- `Pomoc CRT` — skrót `F1`,
- `Szybki start`,
- `Słownik pojęć`,
- `Skróty klawiaturowe`,
- `O CAN Research Tool`.

Akcja `Pomoc CRT` jest również dostępna na pasku aktywności. F1 otwiera stronę
główną Help Center ze spisem tematów i szybkimi przejściami.

### 3.2 Jedna trwała zakładka

Help jest otwierany jako zakładka `Pomoc` w głównym workspace. Kolejne akcje
menu nie tworzą duplikatów, lecz aktywują istniejącą zakładkę i przechodzą do
wskazanego artykułu.

### 3.3 Nawigacja

Widok zawiera:

- drzewo kategorii i tematów,
- pełnotekstowe pole wyszukiwania,
- przyciski `Wstecz`, `Dalej` i `Start pomocy`,
- linki do tematów powiązanych,
- status bieżącej strony i liczby wyników,
- skróty `Ctrl+F`, `Alt+Left` i `Alt+Right`.

Dodano publiczny hook `open_help_topic(topic_id)` przeznaczony do przyszłych
przycisków pomocy kontekstowej w konkretnych oknach CRT.

## 4. Wyszukiwanie

Wyszukiwanie obejmuje:

- tytuł,
- skrócony opis,
- słowa kluczowe,
- nagłówki sekcji,
- akapity, listy, procedury, uwagi i ostrzeżenia.

Zapytanie wielowyrazowe wymaga obecności wszystkich tokenów. Wyniki są
rankingowane z pierwszeństwem tytułu, słów kluczowych i opisu.

Normalizacja jest niewrażliwa na wielkość liter i polskie znaki. W czasie CI
wykryto, że Unicode NFKD nie rozkłada litery `ł`. Dodano jawne mapowanie
`ł → l`, dzięki czemu zapytanie `zrodlo prawdy` poprawnie odnajduje temat
`Źródło prawdy i niezmienność danych`.

## 5. Zakres merytoryczny

Katalog zawiera ponad 30 artykułów w dziesięciu kategoriach:

1. `Pierwsze kroki`,
2. `Projekt i organizacja badań`,
3. `Rejestracja i ramki CAN`,
4. `Zapisane sesje i wyszukiwanie`,
5. `Dekodowanie i protokoły`,
6. `Porównywanie logów`,
7. `Artefakty i dowody`,
8. `Bezpieczeństwo i wydajność`,
9. `Rozwiązywanie problemów`,
10. `Słownik i skróty`.

Opisano między innymi:

- rolę CRT i model projektu jednego ECU,
- niezmienne surowe sesje jako źródło prawdy,
- tworzenie, otwieranie, przenoszenie i zabezpieczanie projektów,
- profil ECU, obszary badań, sesje i import,
- Live Capture, markery, surowe ramki i dokładny klucz wiadomości,
- filtry Live i globalne,
- stronicowane sesje, indeksy i wyszukiwanie między stronami,
- DBC, ISO-TP oraz podstawy UDS,
- zestawy porównawcze i dashboard,
- trwałą oś czasu i kotwice,
- timing, jitter, przerwy i percentyle,
- latencję UDS, `0x78 ResponsePending` i timeouty,
- eksplorator transakcji UDS, DID, subfunkcje, Routine ID i NRC,
- artefakty, fingerprinty i nawigację do `source_row`,
- bounded model GUI i różnicę między dokładnym licznikiem a próbką,
- kopie zapasowe, wydajność i zadania w tle,
- diagnozę pustego widoku, błędnego dekodowania i problemów Kvaser/CANlib,
- bezpieczne odzyskiwanie po błędzie,
- słownik oraz skróty klawiaturowe.

## 6. Architektura

### 6.1 Katalog aplikacyjny

`app/help_catalog.py`

Zawiera niemutowalne struktury:

- `HelpTopic`,
- `HelpSection`,
- kolejność kategorii,
- katalog tematów,
- wyszukiwarkę,
- renderer strony startowej i artykułów HTML.

Treść jest oddzielona od widoku Qt i testowalna bez uruchamiania GUI.

### 6.2 Widok Qt

`gui/help_center_view.py`

Dostarcza:

- `HelpCenterWidget`,
- drzewo `QTreeWidget`,
- pole `QLineEdit`,
- lokalny `QTextBrowser`,
- historię stron,
- obsługę linków `help://topic/<id>`,
- skróty klawiaturowe.

### 6.3 Integracja shella

`gui/help_center_shell.py`

`HelpCenterMainWindow` rozszerza istniejący shell porównań bez zmiany jego
usług domenowych. `ApplicationContainer` tworzy ten shell jako produkcyjne
okno aplikacji.

Aktualizacja istniejącego smoke `engineering_shell_smoke.py` ogranicza się do
nowego, zamierzonego kontraktu menu: pięć dotychczasowych menu plus `Pomoc` i
akcja F1.

## 7. Poprawki wykryte przez CI

### 7.1 Polskie `ł`

Objaw: `search_help_topics("zrodlo prawdy")` zwracało pusty wynik.

Przyczyna: NFKD usuwa znak diakrytyczny z `ź` i `ó`, ale nie zamienia `ł` na
`l`.

Naprawa: jawna transliteracja `ł → l` przed normalizacją NFKD.

### 7.2 Semantyka F1

Objaw: smoke oczekiwał strony głównej, natomiast F1 otwierał artykuł
`Wprowadzenie do CAN Research Tool`.

Naprawa: F1 otwiera teraz stronę główną Help Center. Akcje `Szybki start`,
`Słownik`, `Skróty` oraz pomoc kontekstowa nadal przechodzą bezpośrednio do
artykułu.

### 7.3 Kontrakt menu shella

Dodanie menu `Pomoc` ujawniło oczekiwaną regresję w teście, który wymagał
identycznej listy pięciu menu. Smoke został rozszerzony o ścisłą kontrolę
szóstego menu oraz skrótu F1.

## 8. Testy

Dodano:

- `tests/test_help_catalog.py`,
- `tests_gui/help_center_smoke.py`,
- workflow `.github/workflows/help-center.yml`.

Testy katalogu obejmują:

- unikalność identyfikatorów,
- poprawność kategorii i linków powiązanych,
- obecność tematów wszystkich głównych funkcji,
- wyszukiwanie wielowyrazowe,
- wyszukiwanie bez polskich znaków,
- ranking trafności,
- renderowanie HTML i linków.

Produkcyjny smoke GUI obejmuje:

- start CRT bez projektu,
- menu `Pomoc` i F1,
- stronę główną,
- wyszukiwanie,
- otwieranie artykułów,
- historię Wstecz/Dalej,
- słownik i skróty,
- użycie jednej instancji zakładki.

## 9. Walidacja funkcjonalnego checkpointu

Zwalidowany commit funkcjonalny:

`584e97d2d663647f18ab6e9dd77a2fdfccc479f0`

Zakończone sukcesem:

- `Help Center Validation` — Ubuntu i Windows,
- testy katalogu i wyszukiwarki,
- produkcyjny smoke GUI,
- pełny job `pytest`,
- `Windows GitHub-Hosted CI`,
- `GUI Regressions`,
- `Comparison Dashboard Validation`,
- `Comparison Timeline Validation`,
- `Comparison Timeline Stage 2B Validation`,
- `Comparison Inter-Frame Timing Stage 2C1 Validation`,
- `Comparison UDS Latency Stage 2C2 Validation`,
- `Comparison UDS Transaction Explorer Stage 2D1 Validation`,
- `Live Preview Capacity`.

Ogólny job `Tests/gui-smoke` wykonywał nadal długi test tworzenia workspace w
momencie zapisu raportu. Dedykowany produkcyjny smoke Help oraz pełny zestaw
GUI Regressions były zielone.

Windows Self-Hosted CI nie jest wymagany dla statycznego etapu bez sprzętu CAN.

## 10. Zachowane kontrakty

Etap nie zmienia:

- `CaptureService`,
- Kvasera i lifecycle CANlib,
- CAN TX/RX,
- formatu sesji i markerów,
- kompletności i kolejności surowego zapisu,
- indeksów sesji,
- bounded modelu zapisanych logów,
- schematu `.crt/project.sqlite`,
- algorytmów i artefaktów Comparison Visualization Stage 1–2D1.

Help jest lokalnym, statycznym widokiem tylko do odczytu.

## 11. Test ręczny

1. Uruchomić CRT bez otwierania projektu.
2. Nacisnąć `F1`.
3. Potwierdzić stronę główną, spis kategorii i szybkie przejścia.
4. Wyszukać kolejno:
   - `zrodlo prawdy`,
   - `jitter percentyl`,
   - `0x78 odpowiedz koncowa`,
   - `brak wynikow`,
   - `Kvaser bitrate`.
5. Otworzyć tematy z drzewa i linków powiązanych.
6. Sprawdzić `Wstecz`, `Dalej`, `Start pomocy`, `Ctrl+F`, `Alt+Left` i
   `Alt+Right`.
7. Z menu otworzyć `Szybki start`, `Słownik pojęć` i `Skróty klawiaturowe`.
8. Potwierdzić, że cały czas istnieje tylko jedna zakładka `Pomoc`.
9. Otworzyć normalny projekt i potwierdzić działanie Przeglądu, Live Capture,
   zapisanych sesji, dekoderów, filtrów i porównań.

## 12. Następny krok

Po ręcznym potwierdzeniu Help Center można:

1. uzupełniać artykuły przy każdym kolejnym etapie CRT,
2. dodać przyciski pomocy kontekstowej do wybranych okien,
3. wrócić do zapisanego punktu:

`Comparison Visualization Stage 2D2 — transakcje UDS na trwałej osi czasu`.
