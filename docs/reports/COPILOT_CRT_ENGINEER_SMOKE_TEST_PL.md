# Smoke test GitHub Copilot — CRT Engineer

- Data testu: 2026-07-22
- Repozytorium: `autoklinika/can-research-tool`
- Gałąź bazowa: `main`
- Bazowy HEAD: `4a674bf703e247b0ef36da5546c74825eaa63f06`

## Przeczytane dokumenty

1. `docs/CRT_RESEARCH_PLATFORM_MASTER_PLAN_PL.md`
2. `docs/COPILOT_WORKFLOW_PL.md`
3. `.github/copilot-instructions.md`
4. `.github/agents/crt-engineer.agent.md` (profil agenta wskazany w zadaniu)

## Rola agenta CRT Engineer — podsumowanie

CRT Engineer realizuje małe, ściśle określone zadania w wydzielonej gałęzi i draft PR, z zachowaniem kontraktów integralności danych CRT oraz bez rozszerzania zakresu.

## Zachowane kontrakty

- brak zmian `CaptureService`,
- brak zmian Kvasera,
- brak zmian lifecycle CANlib,
- brak zmian formatu sesji,
- brak zmian SQLite,
- brak zmian GUI,
- brak zmian kolejności i kompletności zapisu surowych ramek.

## Zakres zmiany

Zmiana jest wyłącznie dokumentacyjna: dodano jeden nowy plik raportu smoke testu.

## Walidacja

- `git diff --check`: PASS (brak błędów; wyjście puste)
- Testy runtime: niewymagane dla zmiany wyłącznie dokumentacyjnej.

## Wynik

PASS
