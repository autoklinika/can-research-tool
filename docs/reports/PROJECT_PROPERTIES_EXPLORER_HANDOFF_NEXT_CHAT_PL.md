# CAN Research Tool — handoff po właściwościach projektu i uproszczeniu Explorera

Data: 2026-07-22

Repozytorium: `autoklinika/can-research-tool`

Gałąź: `agent/project-properties-stage1`

PR: #35 `Add safe CRT project properties editing`

Issue: #40 `Usuń nagłówek i przyciski nad drzewem projektu`

## Stan etapu

Etap jest funkcjonalnie zakończony i ręcznie potwierdzony przez użytkownika jako działający.

Aktualny funkcjonalny HEAD przed końcową aktualizacją tego raportu:

`2b8ea2a86160c476d4c94ed45e4d9be917cf43c1`

PR #35 pozostaje draftem. Nie został oznaczony jako gotowy do review i nie został scalony. PR jest stacked na `agent/minimal-analysis-chrome-stage8` (PR #34), którego aktualny HEAD po końcowych poprawkach review to:

`f329221a30d179acdccfc51d04b916684c9c2a61`

## Zrealizowany zakres

### Właściwości projektu

Dodano akcję `Plik → Właściwości projektu…`, która pozwala edytować wyłącznie mutowalne metadane projektu:

- nazwę wyświetlaną,
- opis,
- domyślny bitrate,
- domyślny tryb odbioru.

Folder projektu pozostaje tylko do odczytu. Identyfikator projektu, `created_at_utc`, istniejące sesje, obszary badań, struktura `.crt` oraz baza `.crt/project.sqlite` nie są przebudowywane ani przenoszone.

Po poprawnym zapisie natychmiast odświeżane są:

- tytuł okna,
- pasek statusu,
- Explorer projektu,
- pasek kontekstu,
- widok Przegląd,
- domyślne ustawienia już otwartego widoku Live dla kolejnej sesji.

Trwająca rejestracja zachowuje `StartCaptureRequest` utworzony przy naciśnięciu Start.

### Uproszczenie Explorera projektu

Usunięto obszar nad drzewem projektu widoczny wcześniej w lewym panelu:

- powtórzoną nazwę projektu,
- pełną ścieżkę projektu,
- przycisk `+ Obszar`,
- przycisk `Importuj`.

`projectTree` zajmuje teraz całą przestrzeń zawartości Explorera.

Zachowane funkcje:

- główny węzeł drzewa nadal pokazuje nazwę projektu,
- tooltip głównego węzła nadal zawiera ścieżkę projektu,
- `Plik → Importuj log…` nadal działa,
- import pozostaje dostępny również w widoku Przegląd,
- dodawanie obszaru pozostaje dostępne w widoku Przegląd.

Usunięto również martwe sygnały `import_requested` i `add_area_requested`, ich nieużywane połączenia w oknie głównym oraz selektory motywów `projectExplorerHeader` i `projectExplorerName`, które pozostały po usuniętych widgetach.

## Dodatkowe poprawki wykryte podczas review

Podczas końcowego review znaleziono i poprawiono rzeczywiste problemy w pierwotnym zakresie PR #35:

1. Przy błędzie zapisu manifestu poprzedni manifest jest przywracany również w pamięci, dzięki czemu aplikacja nie używa wartości, których zapis na dysku się nie powiódł.
2. Już otwarty widok Live otrzymuje nowe domyślne bitrate i tryb odbioru dla kolejnej sesji.
3. Usunięto lokalny limit 200 znaków w dialogu właściwości, który mógł skrócić istniejącą długą nazwę projektu przy zapisie innego pola.
4. Usunięto martwe selektory QSS dla skasowanego nagłówka i etykiety nazwy Explorera, zachowując style widoku Przegląd.

Smoke test właściwości projektu został rozszerzony tak, aby rzeczywiście uruchamiał akcję menu i akceptował modalny dialog zamiast omijać przepływ GUI.

Na bazowym PR #34 poprawiono również widoczność błędu katalogu artefaktów zarówno przy inicjalizacji widoku, jak i po zakończeniu analizy. Smoke Stage 8 obejmuje teraz stan poprawnego zakończenia, failure, cancellation, niedostępny kontekst oraz błąd odczytu katalogu artefaktów.

## Walidacja

Dla funkcjonalnego HEAD PR #35 `2b8ea2a86160c476d4c94ed45e4d9be917cf43c1` potwierdzono:

- `Tests` — PASS,
- `GUI Regressions` — PASS,
- `Live Preview Capacity` — PASS,
- `Windows GitHub-Hosted CI` — PASS.

Końcowa aktualizacja raportu uruchamia nowy pełny przebieg CI PR #35 już względem zaktualizowanej bazy PR #34. `Windows Self-Hosted CI` nie blokuje tego etapu, ponieważ zmiany nie korzystają z Kvasera, CANlib ani sprzętu CAN.

Pierwszy wcześniejszy przebieg `Tests` miał pojedynczy niezwiązany z tym diffem wyścig czasowy w `test_capture_markers.py` (`225 passed, 1 failed`). Ponowiono wyłącznie nieudany job; drugi przebieg zakończył się sukcesem. Nie zmieniano z tego powodu `CaptureService` ani testu Capture.

Użytkownik uruchomił gałąź lokalnie w VS Code i potwierdził, że zmiana GUI działa poprawnie.

## Zachowane kontrakty

Nie zmieniono:

- `CaptureService`,
- Kvasera ani lifecycle CANlib,
- kodu CAN TX/RX,
- formatu sesji i indeksów,
- kolejności ani kompletności zapisu surowych ramek,
- warstwy analiz zapisanej sesji poza poprawką widoczności statusu w bazowym PR #34,
- schematu `project.sqlite`,
- struktury `.crt`,
- zależności projektu.

## Zasada użycia Copilota po tym etapie

Copilot nie będzie podstawowym wykonawcą większych zmian ani zadań na gałęziach stacked.

Przyjęty tryb pracy:

- główna implementacja i prowadzenie zmian pozostają po stronie ChatGPT oraz kontrolowanego workflow GitHub,
- użytkownik podejmuje decyzje dotyczące zakresu, gotowości i merge,
- Copilot jest używany głównie jako dodatkowy recenzent PR,
- Copilot Coding Agent może być użyty tylko do małych, izolowanych zadań, gdy baza i zakres są jednoznaczne oraz po wyraźnej decyzji użytkownika,
- nie należy ponawiać eksperymentu z ręcznym uruchamianiem Copilot Coding Agent na gałęziach stacked bez uprzedniego rozwiązania problemu wyboru bazy i dostępności custom agenta.

Powód: dwa wcześniejsze uruchomienia dla issue #40 utworzyły błędne PR #41 i #42 do `main`, co zwiększyło liczbę kroków i nie przyniosło oszczędności czasu. Oba PR zostały zamknięte bez merge.

## Następny punkt kontrolny

Przed scaleniem należy:

1. Potwierdzić końcowe CI i review PR #34.
2. Potwierdzić końcowe CI i review PR #35 względem aktualnej bazy PR #34.
3. Przejść cały stacked chain od najniższego niescalonego PR w poprawnej kolejności.
4. Dopiero po wyraźnej decyzji użytkownika oznaczać PR-y jako ready i wykonywać merge.
5. Po merge PR #35 zamknąć issue #40 jako completed.

Nie wykonywać merge ani zmiany statusu draft bez jednoznacznego polecenia użytkownika.
