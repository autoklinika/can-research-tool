# CAN Research Tool — Project Catalog Stage 1 — raport końcowy

Data zamknięcia etapu: 2026-07-22

## 1. Status etapu

**Project Catalog Stage 1 został funkcjonalnie zakończony i ręcznie zaakceptowany.**

Implementacja umożliwia zarządzanie projektami CRT jako trwałymi kartotekami jednego badanego ECU. Katalog aplikacji pozostaje oddzielony od danych projektu, a projekt zachowuje przenośny profil opisowy.

Gałąź etapu:

`agent/project-catalog-stage1`

PR:

`#43 — Add managed CRT project catalog, profile editing and relocation`

Bazowy commit funkcjonalny po ostatnim rozszerzeniu:

`9dbada0122c35822ae2d94a3ca5a5dbdc3f54d6c`

Commit wcześniejszego handoffu:

`8c2accaaad111c5dd5e0a909792e8d006cd88362`

## 2. Zrealizowany zakres

Etap dostarczył:

- centralny katalog aplikacji `projects.sqlite`,
- przenośny profil projektu `project-profile.json`,
- opis pojazdu, maszyny, ECU i tagów projektu,
- zarządzane okno `Projekty CRT`,
- wyszukiwanie wielowyrazowe,
- filtrowanie projektów według czasu,
- wykrywanie projektów z brakującym folderem,
- ponowne wskazywanie lokalizacji projektu,
- kontrolę zgodności identyfikatora projektu podczas relokacji,
- bezpieczne usuwanie wyłącznie wpisu katalogowego,
- edycję właściwości aktualnie otwartego projektu,
- edycję właściwości dowolnego dostępnego projektu bezpośrednio z listy,
- przycisk `Właściwości…`,
- akcję `Właściwości…` w menu kontekstowym,
- natychmiastowe odświeżanie katalogu i indeksu wyszukiwania po zapisie.

## 3. Najważniejsze decyzje architektoniczne

1. Jeden projekt CRT opisuje jedno badane ECU.
2. Projekt jest pełną teczką badawczą, a nie pojedynczym logiem.
3. Katalog aplikacji nie jest źródłem prawdy dla danych badawczych.
4. Profil projektu jest przenośny razem z folderem projektu.
5. Usunięcie wpisu z katalogu nie usuwa danych projektu.
6. Relokacja wymaga zgodnego identyfikatora projektu.
7. Edycja metadanych nie zmienia surowych sesji ani kolejności ich zapisu.

## 4. Zachowane kontrakty

W etapie nie zmieniono:

- `CaptureService`,
- backendu Kvaser,
- lifecycle CANlib,
- transmisji CAN TX/RX,
- formatu zapisanych sesji,
- kolejności pełnego zapisu surowych ramek,
- istniejących trwałych indeksów wyszukiwania sesji,
- schematu wewnętrznego `project.sqlite` badanego projektu.

## 5. Walidacja

### Walidacja ręczna

Użytkownik potwierdził poprawne działanie:

- katalogu projektów,
- wyszukiwania i filtrów,
- relokacji brakującego projektu,
- właściwości otwartego projektu,
- właściwości projektu otwieranych bezpośrednio z listy,
- natychmiastowego odświeżania listy po zapisie.

Wynik: **PASS**.

### Pokrycie automatyczne

Zakres testów obejmuje między innymi:

- `tests/test_project_catalog.py`,
- `tests_gui/project_catalog_smoke.py`.

GUI smoke sprawdza dostępność akcji `Właściwości…` dla dostępnego projektu oraz blokadę tej akcji dla projektu z brakującym folderem.

### Stan GitHub Actions w chwili zamknięcia raportu

Dla najnowszego HEAD workflow pozostawały w stanie `queued`:

- Tests,
- GUI Regressions,
- Windows GitHub-Hosted CI,
- Windows Self-Hosted CI,
- Live Preview Capacity.

Dwa uruchomienia dla wcześniejszego commita zostały anulowane po przesunięciu HEAD. Nie odnotowano wyniku `failure`, ale nie uzyskano również kompletnego zielonego przebiegu CI.

Dlatego etap jest oznaczony jako **funkcjonalnie zakończony i ręcznie zaakceptowany**, natomiast pełna automatyczna walidacja pozostaje do potwierdzenia po zwolnieniu kolejki GitHub Actions.

## 6. Stan PR #43

- PR jest otwarty,
- PR jest mergeowalny,
- brak otwartych wątków review,
- brak żądań zmian,
- implementacja została ręcznie zatwierdzona,
- raport końcowy znajduje się na tej samej gałęzi.

PR jest stacked na `agent/project-properties-stage1` / PR #35. Przed scaleniem należy zachować poprawną kolejność integracji stacked PR-ów.

## 7. Punkt kontrolny

Po pobraniu zmian lokalnie:

```powershell
Set-Location C:\CAN\can-research-tool
git fetch origin
git switch agent/project-catalog-stage1
git pull --ff-only
git status -sb
```

Oczekiwany stan: czyste drzewo robocze na aktualnym HEAD gałęzi.

## 8. Zalecenie dla następnego etapu

Następny etap należy wybrać na podstawie:

- `docs/CRT_RESEARCH_PLATFORM_MASTER_PLAN_PL.md`,
- aktualnego stanu stacked PR-ów,
- zależności od Project Properties Stage 1 i Project Catalog Stage 1.

Nie należy rozszerzać następnego etapu o przypadkowe zmiany Capture, Kvasera, CANlib ani formatów sesji.

## 9. Prompt do rozpoczęcia nowej dyskusji

```text
Kontynuujemy rozwój CAN Research Tool po funkcjonalnym zakończeniu Project Catalog Stage 1.

Repozytorium:
`autoklinika/can-research-tool`

Zakończona gałąź:
`agent/project-catalog-stage1`

PR:
`#43`

Najpierw przeczytaj dokładnie:

- `docs/CRT_RESEARCH_PLATFORM_MASTER_PLAN_PL.md`
- `docs/reports/PROJECT_CATALOG_STAGE1_FINAL_REPORT_PL.md`
- odpowiednie raporty etapów bazowych, w szczególności Project Properties Stage 1

Sprawdź aktualny HEAD repozytorium, stan PR #43 oraz zależności stacked PR-ów.

Project Catalog Stage 1 został ręcznie potwierdzony jako działający. Dostarcza centralny katalog `projects.sqlite`, przenośny `project-profile.json`, wyszukiwanie, filtry czasu, relokację brakujących projektów oraz edycję właściwości otwartego projektu i dowolnego dostępnego projektu bezpośrednio z listy.

Stan GitHub Actions zapisany w raporcie może być nieaktualny, dlatego na początku sprawdź najnowsze wyniki CI. Nie powtarzaj implementacji zakończonego etapu.

Następnie wskaż kolejny logiczny etap zgodny z Master Plan i rozpocznij jego realizację.

Nie zmieniaj bez wyraźnej potrzeby i osobnej decyzji:

- CaptureService,
- backendu Kvaser,
- lifecycle CANlib,
- CAN TX/RX,
- formatu sesji,
- kolejności pełnego zapisu surowych ramek,
- trwałych indeksów wyszukiwania,
- schematu project.sqlite badanego projektu,
- kontraktów Project Properties Stage 1 i Project Catalog Stage 1.

Przy końcu większego etapu przygotuj punkt kontrolny: commit, push, stan PR oraz raport/handoff do kolejnej rozmowy.
```
