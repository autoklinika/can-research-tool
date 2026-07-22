# CAN Research Tool — instrukcje dla GitHub Copilot

## Kontekst nadrzędny

- Przed zmianami przeczytaj `docs/CRT_RESEARCH_PLATFORM_MASTER_PLAN_PL.md` oraz aktualny raport handoff wskazany w zadaniu.
- Jeden projekt CRT opisuje jedno badane ECU i jest pełną teczką badawczą, a nie pojedynczym logiem.
- Zapisane sesje i surowe ramki są niezmiennym źródłem prawdy.
- Analizy zapisanej sesji tworzą trwałe, wersjonowane artefakty i nie mogą zmieniać danych źródłowych.

## Twarde granice bezpieczeństwa

- Nie zmieniaj `CaptureService`, backendu Kvaser, lifecycle CANlib, formatów sesji ani kolejności i kompletności zapisu surowych ramek, chyba że zadanie wyraźnie na to zezwala.
- Nie dodawaj automatycznego nadawania ramek CAN, automatycznego uruchamiania Capture ani ukrytych skutków ubocznych sprzętowych.
- Nie zwiększaj modeli GUI do pełnej liczby ramek. Zachowuj stronicowanie, ograniczone bufory, pracę asynchroniczną oraz trwałe indeksy SQLite.
- Nie przebudowuj zakończonych etapów ani sąsiednich modułów bez bezpośredniej potrzeby wynikającej z zadania.
- Nie zmieniaj schematu `.crt/project.sqlite`, struktury projektu ani ścieżek sesji przy zmianach czysto interfejsowych.
- Nie zgaduj semantyki protokołów CAN, UDS lub J1939. Oddziel fakty z logów od hipotez.

## Sposób pracy

- Najpierw prześledź istniejący przepływ, zależności i testy; dopiero potem proponuj zmianę.
- Utrzymuj mały, jednoznaczny zakres: jedna funkcja lub etap na gałąź i PR.
- Gdy baza nie jest jeszcze scalona, twórz stacked branch i jawnie wskaż bazowy PR.
- Preferuj istniejące kontrolery, serwisy i fabryki zamiast równoległych implementacji.
- Dodawaj test domenowy dla trwałości danych oraz smoke/regression test dla zmian GUI.
- Pełną walidację wykonuj przez GitHub Actions. Testy wymagające Kvasera, CANlib lub sprzętu pozostaw dla właściwego runnera sprzętowego.
- Nie uznawaj zadania za ukończone, dopóki nie podasz dokładnego HEAD, uruchomionych testów, wyniku CI, zachowanych kontraktów i pozostałego ryzyka.
- Nie wykonuj merge, force-push, rebase ani usuwania gałęzi bez wyraźnego polecenia.

## Review

- W review najpierw szukaj naruszeń integralności surowych danych, regresji lifecycle, blokowania GUI, nieograniczonego zużycia pamięci i niejawnych zmian zakresu.
- Sprawdzaj, czy operacje zapisu są atomowe, ścieżki pozostają wewnątrz projektu, a błędy nie pozostawiają częściowo zmienionego stanu.
- Zgłaszaj tylko problemy wynikające z diffu i podawaj konkretny plik, scenariusz awarii oraz minimalną poprawkę.
- Odpowiadaj po polsku w raportach i komentarzach review. Nazwy klas, funkcji i techniczne identyfikatory pozostawiaj zgodne z kodem.
