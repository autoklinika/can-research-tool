# Global Filter Engine v1 — stan zamknięty

**Status:** funkcjonalnie zakończony i objęty testami regresyjnymi  
**Gałąź:** `agent/live-buffer-performance-fix`  
**PR:** `#18`  
**Data:** 2026-07-18

## Zakres v1

Global Filter Engine v1 obejmuje:

- presety projektu z drzewem `AND / OR / NOT`,
- tryby `Include`, `Exclude` i `Highlight`,
- pola surowej ramki CAN oraz wiadomości J1939, ISO-TP i UDS,
- osobne, niemodalne okno edytora filtrów,
- uruchamianie okna przez `Ctrl+D`,
- globalne skróty przełączające poszczególne presety,
- wykrywanie konfliktów skrótów z innymi presetami, akcjami CRT i znacznikami,
- projektowy tryb łączenia presetów Include: `AND` albo `OR`,
- filtrowanie strumieniowe podczas aktywnego Live Capture,
- filtrowanie zapisanych i importowanych sesji jako jawny opt-in,
- stałą informację o aktywnych presetach oraz trybie `AND/OR`,
- kompilację presetów przed oceną dużych buforów,
- workery i ochronę generacji wyników.

## Semantyka wielu presetów

Tryb projektowy dotyczy aktywnych presetów `Include`:

- `AND` — rekord musi pasować do wszystkich dostępnych presetów Include,
- `OR` — rekord musi pasować do co najmniej jednego dostępnego presetu Include.

Pozostałe tryby zachowują stałą semantykę:

- dopasowanie dowolnego presetu `Exclude` ukrywa rekord,
- `Highlight` nigdy nie zmienia widoczności,
- warunek niedostępny w danym kontekście jest neutralny i raportowany diagnostycznie.

## Semantyka Live Capture

Podczas aktywnego Capture:

1. Włączenie lub zmiana filtra nie przelicza historycznego bufora GUI.
2. Czyszczony jest wyłącznie widok prezentacyjny.
3. Filtr obowiązuje od kolejnych odebranych paczek.
4. Widok filtrowany przechowuje maksymalnie 5000 ostatnich dopasowanych ramek.
5. Pełny zapis surowych ramek i wiadomości trwa bez zmian.
6. Wyłączenie wszystkich presetów pozostawia zaznaczone `Zastosuj filtry` w stanie oczekiwania.
7. Ponowna aktywacja presetu automatycznie wznawia filtrowanie.

Po zatrzymaniu Capture dostępne pozostaje historyczne przeliczenie istniejącego bufora w workerze.

## Skróty presetów

- Skrót jest przechowywany w presecie i działa w całej aplikacji.
- Skrót przełącza preset aktywny lub nieaktywny.
- Wszystkie niepuste skróty presetów muszą być unikalne.
- Skrót nie może kolidować z akcją CRT, np. `Ctrl+D`, ani aktywnym znacznikiem.
- Nieprawidłowego presetu nie można aktywować skrótem.
- Zapisywany skrót jest normalizowany przez `QKeySequence`.

## Kontrakty, których nie wolno naruszyć

1. Filtry nigdy nie wpływają na odbiór CAN ani zapis sesji.
2. `CaptureService`, Kvaser i lifecycle CANlib pozostają poza silnikiem filtrów.
3. Surowa ramka jest zapisywana przed dekodowaniem i oceną widoku.
4. Filtry zapisanej sesji są domyślnie wyłączone.
5. Nieprawidłowy aktywny preset blokuje zapis konfiguracji.
6. Wynik starszego workera nie może zastąpić nowszej generacji.
7. Bufory GUI pozostają ograniczone.

## Test końcowy przed scaleniem

Na stanowisku należy wykonać:

```text
Start Capture
→ włącz Zastosuj filtry
→ przełącz presety skrótami
→ wyłącz wszystkie presety i ponownie aktywuj jeden
→ sprawdź AND i OR
→ potwierdź nazwy aktywnych filtrów w Live
→ zapisz pełną sesję
→ zatrzymaj Capture
→ otwórz zapisaną sesję
→ jawnie włącz filtry sesji
→ potwierdź te same wyniki i tryb AND/OR
```

Po pozytywnym teście stanowiskowym moduł filtrów można traktować jako zamknięty. Dalsze funkcje, takie jak filtry payload mask, częstotliwości, zmienności, menu kontekstowe tabeli lub generowanie filtrów przez analizę, powinny powstać w osobnym etapie.
