# GitHub Copilot w CAN Research Tool — model pracy

## Role

W projekcie CRT obowiązuje podział odpowiedzialności:

- **Hubert** — właściciel produktu i ostateczna decyzja o zakresie oraz merge.
- **ChatGPT** — architekt, koordynator etapów, integrator, analiza CI i końcowa walidacja.
- **Copilot** — dodatkowy reviewer oraz wykonawca małych, dokładnie wydzielonych zadań.

Copilot nie prowadzi samodzielnie dużych etapów architektonicznych i nie otrzymuje ogólnego polecenia „rozwijaj CRT”.

## Konfiguracja repozytorium

- `.github/copilot-instructions.md` — reguły obowiązujące w całym repozytorium.
- `.github/instructions/*.instructions.md` — dodatkowe reguły dla chronionych ścieżek.
- `.github/agents/crt-engineer.agent.md` — profil agenta implementacyjnego **CRT Engineer**.
- `.github/ISSUE_TEMPLATE/copilot-task.yml` — formularz do przygotowania zadania dla Copilota.

## Tryb 1 — Copilot jako reviewer

To jest tryb domyślny.

1. Otwieramy draft PR.
2. Uruchamiamy właściwe GitHub Actions.
3. Dodajemy Copilota jako reviewera.
4. Każdą uwagę weryfikujemy względem Master Planu, handoffu i rzeczywistego diffu.
5. Copilot nie zatwierdza merge. Brak komentarzy oznacza tylko, że nie wykrył problemu.

Zalecane ustawienie repozytorium: automatyczne review Copilota dla draft PR i nowych pushy. Dzięki temu dostaje każdą kolejną wersję diffu.

## Tryb 2 — małe zadanie implementacyjne

1. Utwórz issue przez formularz **Zadanie dla Copilot CRT**.
2. Podaj dokładną gałąź startową i oczekiwany HEAD.
3. Wskaż dozwolone pliki, obszary zakazane, kryteria akceptacji i wymagane testy.
4. Przypisz issue do Copilota.
5. W oknie przypisania wybierz:
   - właściwe repozytorium,
   - wskazaną gałąź startową,
   - agenta **CRT Engineer**.
6. Copilot tworzy draft PR. Nie pozwalamy mu wykonywać merge.
7. ChatGPT analizuje diff, CI i komentarze review przed decyzją użytkownika.

## Zadania odpowiednie dla Copilota

- dodanie precyzyjnego testu regresyjnego,
- mała zmiana tekstu, akcji menu lub formularza,
- uzupełnienie dokumentacji po zatwierdzonej implementacji,
- mechaniczne zastosowanie istniejącego wzorca w jednym module,
- naprawa dobrze zdiagnozowanego błędu z jednoznacznym testem.

## Zadania pozostające po stronie ChatGPT

- projektowanie architektury i granic etapów,
- zmiany CaptureService, Kvasera, CANlib i formatów sesji,
- migracje SQLite lub projektu,
- zmiany wpływające na kolejność albo kompletność surowych ramek,
- analiza nieznanych protokołów CAN/UDS/J1939,
- duże refaktoryzacje i integracja wielu stacked PR.

## Minimalny standard issue

Każde zadanie dla Copilota musi zawierać:

- bazową gałąź i commit,
- jeden mierzalny cel,
- dokumenty do przeczytania,
- dozwolone pliki,
- obszary zakazane,
- kryteria akceptacji,
- testy i wymagane workflow,
- informację, czy potrzebny jest runner sprzętowy.

## Minimalny standard PR Copilota

PR powinien być draftem i zawierać:

- cel oraz faktyczny zakres,
- bazę i HEAD,
- listę zmienionych plików,
- testy wykonane lokalnie i przez CI,
- zachowane kontrakty,
- ryzyko, ograniczenia i test ręczny.

## Punkt kontrolny

Po większym etapie zawsze wykonujemy:

1. końcową walidację GitHub Actions,
2. review ChatGPT i Copilota,
3. ręczny smoke test, gdy zmiana dotyczy GUI lub sprzętu,
4. commit i push,
5. handoff do kolejnego etapu,
6. merge wyłącznie po decyzji użytkownika.