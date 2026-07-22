# CAN Research Tool — instrukcje dla GitHub Copilot

## Nadrzędny kontekst

- Przed zmianami przeczytaj `docs/CRT_RESEARCH_PLATFORM_MASTER_PLAN_PL.md` oraz raport handoff wskazany w zadaniu lub issue.
- Nie zakładaj, że właściwą bazą jest `main`. Użyj gałęzi startowej wskazanej w issue lub zleceniu; przy pracy stacked zachowaj wskazaną bazę PR.
- Jeden projekt CRT opisuje jedno badane ECU i jest pełną teczką badawczą, a nie pojedynczym logiem.
- Zapisane sesje i surowe ramki są niezmiennym źródłem prawdy.
- Analizy tworzą trwałe, wersjonowane artefakty i nie mogą modyfikować danych źródłowych.

## Twarde granice bezpieczeństwa

- Nie zmieniaj `CaptureService`, backendu Kvaser, lifecycle CANlib, formatów sesji ani kolejności i kompletności zapisu surowych ramek, chyba że zadanie wyraźnie wymienia te obszary jako dozwolone.
- Jeżeli realizacja wymaga wejścia w chroniony obszar niewymieniony w zadaniu, zatrzymaj implementację i opisz potrzebną decyzję zamiast rozszerzać zakres.
- Nie dodawaj automatycznego nadawania ramek CAN, automatycznego uruchamiania Capture ani ukrytych skutków sprzętowych.
- Nie zwiększaj modeli GUI do pełnej liczby ramek. Zachowuj stronicowanie, ograniczone bufory, pracę asynchroniczną i trwałe indeksy SQLite.
- Nie zmieniaj schematu `.crt/project.sqlite`, struktury projektu ani ścieżek sesji przy zmianach czysto interfejsowych.
- Nie zgaduj semantyki CAN, UDS lub J1939. Oddzielaj fakty z logów od hipotez.
- Nie dodawaj nowych zależności, sekretów, tokenów ani dostępu sieciowego bez wyraźnej potrzeby i zgody.

## Sposób pracy

- Najpierw prześledź istniejący przepływ, zależności, testy i aktualny HEAD; dopiero potem edytuj kod.
- Utrzymuj mały zakres: jedna funkcja lub etap na gałąź i PR.
- Preferuj istniejące kontrolery, serwisy, integracje i fabryki zamiast równoległych implementacji.
- Zmieniaj tylko pliki dozwolone w issue. Każdy dodatkowy plik uzasadnij w opisie PR.
- Dodawaj test domenowy dla trwałości danych oraz smoke/regression test dla zmian GUI.
- Pełną walidację wykonuj przez GitHub Actions. Testy wymagające Kvasera, CANlib lub sprzętu pozostaw dla runnera sprzętowego.
- Nie wykonuj merge, force-push, rebase, usuwania gałęzi ani zmiany bazy PR bez wyraźnego polecenia.

## Wynik pracy

- Otwórz draft PR i utrzymuj jego opis zgodny z rzeczywistym diffem.
- W opisie PR podaj: cel, bazę i HEAD, zmienione pliki, testy, wynik CI, zachowane kontrakty oraz pozostałe ryzyko.
- Odpowiadaj po polsku w raportach i komentarzach. Nazwy klas, funkcji i identyfikatory techniczne pozostaw zgodne z kodem.

## Code review

- Najpierw szukaj naruszeń integralności danych, regresji lifecycle, blokowania GUI, nieograniczonego zużycia pamięci i niejawnego rozszerzenia zakresu.
- Sprawdzaj atomowość zapisu, bezpieczeństwo ścieżek, teardown Qt/SQLite oraz zachowanie po błędzie lub anulowaniu.
- Zgłaszaj tylko problemy wynikające z diffu. Podaj plik, scenariusz awarii, skutek i minimalną poprawkę.
- Brak uwag oznacza brak znalezionych problemów, a nie zgodę na merge.