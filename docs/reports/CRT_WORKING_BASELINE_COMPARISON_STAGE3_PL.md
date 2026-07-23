# CAN Research Tool — działająca wersja bazowa po Comparison Stage 3

## Status

Ta wersja została ręcznie zaakceptowana jako działający checkpoint CRT i jest przeznaczona do integracji z `main`.

Gałąź źródłowa:

`agent/message-sequence-comparison-stage3`

## Zakres działającej wersji

Checkpoint obejmuje skumulowany stan CRT rozwijany w stacked PR-ach, w tym:

- inżynierską powłokę aplikacji,
- Live Capture i zapis pełnego strumienia surowych ramek,
- filtry Live i zapisanych sesji,
- dekodery DBC, ISO-TP, UDS i J1939,
- trwałe indeksy wyszukiwania i nawigację między stronami sesji,
- grupowanie surowych ramek po CAN ID,
- model domenowy analiz, Extension API i trwałe artefakty,
- statystyki pojedynczej sesji,
- zarządzanie projektami CRT i właściwościami projektu,
- zestawy porównawcze,
- porównanie statystyk CAN ID,
- dokładne porównanie wariantów payloadów,
- porównanie sekwencji wiadomości,
- wspólny tryb pełnoekranowy `F11` dla dużych okien.

## Końcowa walidacja lokalna — Windows

Dnia 2026-07-23 użytkownik wykonał na rzeczywistej gałęzi Stage 3:

- `python tests_gui/project_properties_smoke.py` — PASS,
- testy providerów porównawczych — `16 passed`,
- `python tests_gui/comparison_statistics_smoke.py` — PASS,
- `python tests_gui/payload_difference_smoke.py` — PASS,
- `python tests_gui/message_sequence_comparison_smoke.py` — PASS,
- `python -m gui.main` — aplikacja uruchomiona i zamknięta bez błędu.

Ostrzeżenia Qt dotyczące katalogu fontów i `propagateSizeHints()` pochodzą z trybu `offscreen` i nie są błędami testów.

## Naprawiona regresja przed integracją

Naprawiono obsługę niestandardowego domyślnego bitrate w oknie właściwości projektu. Wartość zapisana w manifeście, np. `666000`, jest dodawana do listy i poprawnie wybierana.

Smoke test właściwości projektu posiada bezwarunkowy teardown `try/finally`, który zamyka dialogi, okno, zadania Qt i uchwyty SQLite również po błędzie asercji. Eliminuje to wtórny `WinError 32` dla `project.sqlite`.

## Zachowane kontrakty

Integracja nie zmienia założeń bezpieczeństwa:

- surowe ramki i pliki sesji pozostają źródłem prawdy,
- pełny zapis nie jest ograniczany przez filtry ani bufory GUI,
- brak automatycznej transmisji CAN,
- warstwa porównań jest pasywna,
- Kvaser i lifecycle CANlib pozostają oddzielone od providerów analiz,
- istniejące formaty sesji i kolejność pełnego zapisu ramek pozostają zachowane.

## Strategia integracji

Końcowa gałąź Stage 3 zastępuje długi stack historycznych PR-ów. Do `main` powinna zostać scalona jednym końcowym PR-em integracyjnym, najlepiej metodą squash. Starsze PR-y stacka należy następnie zamknąć jako zastąpione przez integrację, bez osobnego merge każdego etapu.

## Końcowy PR integracyjny

PR #48 został przestawiony bezpośrednio na `main`. Gałąź zawiera aktualny `main`, zachowuje Master Plan i konfigurację Copilota bez zmian, a ten commit uruchamia pełny końcowy zestaw GitHub Actions przed merge.
