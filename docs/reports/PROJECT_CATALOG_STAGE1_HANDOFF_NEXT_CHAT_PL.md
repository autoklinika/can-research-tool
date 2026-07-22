# Project Catalog Stage 1 — handoff

## Stan

Etap funkcjonalny został zakończony i ręcznie zaakceptowany.

- Repozytorium: `autoklinika/can-research-tool`
- Gałąź: `agent/project-catalog-stage1`
- PR: `#43`
- Ostatni commit funkcjonalny: `9dbada0122c35822ae2d94a3ca5a5dbdc3f54d6c`
- PR jest otwarty, draft i mergeowalny.
- Brak otwartych wątków review i żądań zmian.

## Zrealizowany zakres

- centralny katalog projektów CRT,
- przenośny profil projektu,
- dane pojazdu lub maszyny,
- dane badanego ECU,
- wyszukiwanie wielowyrazowe i filtry czasu,
- otwieranie projektu z zarządzanej listy,
- wykrywanie brakującego folderu,
- ponowne wskazanie lokalizacji z kontrolą identyfikatora projektu,
- bezpieczne usuwanie wpisu bez usuwania plików projektu,
- pełna edycja właściwości otwartego projektu,
- edycja właściwości dowolnego dostępnego projektu bezpośrednio z listy,
- natychmiastowe odświeżenie listy i wyszukiwarki po zapisie.

## Najważniejsze pliki

- `app/project_catalog.py`
- `gui/project_dialog.py`
- `gui/project_properties_dialog.py`
- `gui/project_catalog_dialog.py`
- `gui/project_properties_shell.py`
- `tests/test_project_catalog.py`
- `tests_gui/project_catalog_smoke.py`

## Walidacja ręczna

Użytkownik potwierdził poprawne działanie tworzenia, otwierania, wyszukiwania oraz edycji właściwości projektu, także bezpośrednio z listy projektów.

## GitHub Actions

Dla commita funkcjonalnego uruchomiono workflow:

- Tests,
- GUI Regressions,
- Windows GitHub-Hosted CI,
- Windows Self-Hosted CI,
- Live Preview Capacity.

W chwili zapisu raportu workflow nadal oczekiwały w kolejce lub miały status pending. Przed scaleniem trzeba sprawdzić wyniki Actions dla aktualnego HEAD.

## Zachowane kontrakty

Nie zmieniono warstwy Capture, Kvasera, lifecycle CANlib, CAN TX/RX, formatu sesji, indeksów sesji ani kolejności zapisu surowych ramek.

## Start kolejnej rozmowy

1. Przeczytaj ten raport.
2. Sprawdź aktualny HEAD gałęzi.
3. Sprawdź wszystkie workflow dla aktualnego HEAD.
4. Jeżeli wymagane testy są zielone, wykonaj końcową walidację PR #43.
5. Kolejny etap wybierz zgodnie z `docs/CRT_RESEARCH_PLATFORM_MASTER_PLAN_PL.md`.
