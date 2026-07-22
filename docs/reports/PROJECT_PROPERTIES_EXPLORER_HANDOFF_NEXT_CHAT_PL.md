# CAN Research Tool — handoff po właściwościach projektu i uproszczeniu Explorera

Data: 2026-07-22

Repozytorium: `autoklinika/can-research-tool`

Gałąź: `agent/project-properties-stage1`

PR: #35 `Add safe CRT project properties editing`

Issue: #40 `Usuń nagłówek i przyciski nad drzewem projektu`

## Stan etapu

Etap jest funkcjonalnie zakończony i ręcznie potwierdzony przez użytkownika jako działający.

Końcowy funkcjonalny HEAD przed raportem:

`f39fa5bea5a61da01c88e4c68b480d0cc30bd62e`

Końcowy HEAD gałęzi z tym raportem:

`344990685c08def4b41a52693c325f27d2f9775d`

PR #35 pozostaje draftem. Nie został oznaczony jako gotowy do review i nie został scalony. PR jest stacked na `agent/minimal-analysis-chrome-stage8` (PR #34), którego końcowy HEAD po poprawkach review to:

`b74b20225e7d79a695a81931ced17262329cfd8d`

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
5. Niestandardowy bitrate zapisany w istniejącym manifeście jest dodawany do listy otwartego widoku Live i wybierany jako wartość domyślna kolejnej sesji.

Smoke test właściwości projektu rzeczywiście uruchamia akcję menu, akceptuje modalny dialog, sprawdza rollback po błędzie zapisu oraz obejmuje standardowy i niestandardowy bitrate.

Na bazowym PR #34 poprawiono również widoczność stanów analizy:

- błąd katalogu artefaktów jest widoczny przy inicjalizacji i po zakończeniu analizy,
- udane ponowienie usuwa nieaktualny komunikat błędu,
- niedostępny kontekst pokazuje pasek i status,
- odświeżenie artefaktów nie ukrywa postępu aktywnej analizy,
- failure i cancellation pozostają widoczne.

Smoke Stage 8 obejmuje wszystkie te warianty oraz niezmienność sesji źródłowej.

## Walidacja

Dla końcowego HEAD PR #34 `b74b20225e7d79a695a81931ced17262329cfd8d` potwierdzono:

- `Tests` — PASS,
- `GUI Regressions` — PASS,
- `Live Preview Capacity` — PASS,
- `Windows GitHub-Hosted CI` — PASS.

Dla końcowego HEAD PR #35 `344990685c08def4b41a52693c325f27d2f9775d` potwierdzono:

- `Tests` — PASS,
- `GUI Regressions` — PASS,
- `Live Preview Capacity` — PASS,
- `Windows GitHub-Hosted CI` — PASS.

`Windows Self-Hosted CI` nie blokuje tych etapów, ponieważ zmiany nie korzystają z Kvasera, CANlib ani sprzętu CAN.

Copilot został wykorzystany jako dodatkowy recenzent i wskazał kilka rzeczywistych przypadków brzegowych, które poprawiono. Ostatnia próba automatycznego review została zatrzymana przez limit przydziału Copilota; końcowe zmiany są zabezpieczone dedykowanymi smoke testami i pełnym GitHub-hosted CI.

Pierwszy wcześniejszy przebieg `Tests` miał pojedynczy niezwiązany z tym diffem wyścig czasowy w `test_capture_markers.py` (`225 passed, 1 failed`). Ponowiono wyłącznie nieudany job; drugi przebieg zakończył się sukcesem. Nie zmieniano z tego powodu `CaptureService` ani testu Capture.

Użytkownik uruchomił gałąź lokalnie w VS Code i potwierdził, że zmiana GUI działa poprawnie.

## Zachowane kontrakty

Nie zmieniono:

- `CaptureService`,
- Kvasera ani lifecycle CANlib,
- kodu CAN TX/RX,
- formatu sesji i indeksów,
- kolejności ani kompletności zapisu surowych ramek,
- schematu `project.sqlite`,
- struktury `.crt`,
- zależności projektu.

Zmiana w bazowym PR #34 dotyczy wyłącznie prezentacji statusu istniejącej analizy zapisanej sesji i nie zmienia `SessionAnalysisService`, providera ani artefaktów.

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

1. Przejść cały stacked chain od najniższego niescalonego PR w poprawnej kolejności.
2. Po każdej aktualizacji bazy ponownie sprawdzić diff i CI kolejnego PR.
3. Dopiero po wyraźnej decyzji użytkownika oznaczać PR-y jako ready i wykonywać merge.
4. Po merge PR #35 zamknąć issue #40 jako completed.

Nie wykonywać merge ani zmiany statusu draft bez jednoznacznego polecenia użytkownika.
