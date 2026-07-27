# CRT Help Center Stage 1 — ręczne zatwierdzenie

## Stan końcowy

Dnia 2026-07-27 właściciel projektu przeprowadził ręczny test Help Center Stage 1 na Windows i potwierdził:

> Wszystko działa jak należy.

Ręcznie potwierdzony został co najmniej następujący przepływ:

`F1 / menu Pomoc → strona główna → wyszukiwanie → artykuł → linki powiązane → Wstecz/Dalej → ponowne użycie tej samej zakładki`

Help Center działa również bez otwartego projektu i nie wpływa na podstawowe przepływy CRT po otwarciu projektu.

## Funkcjonalny checkpoint

Zwalidowany commit funkcjonalny:

`584e97d2d663647f18ab6e9dd77a2fdfccc479f0`

Checkpoint obejmuje:

- globalne menu `Pomoc`,
- skrót `F1`,
- stronę główną i szybkie przejścia,
- ponad 30 artykułów w 10 kategoriach,
- wyszukiwarkę odporną na polskie znaki, w tym `ł → l`,
- historię Wstecz/Dalej,
- linki pomiędzy tematami,
- jedną ponownie używaną zakładkę,
- pomoc dostępną bez projektu,
- testy katalogu i produkcyjny smoke GUI na Ubuntu i Windows.

## Walidacja automatyczna

Dla funkcjonalnego checkpointu sukcesem zakończyły się między innymi:

- `Help Center Validation` — Ubuntu i Windows,
- pełny job `pytest`,
- `Windows GitHub-Hosted CI`,
- `GUI Regressions`,
- `Live Preview Capacity`,
- wszystkie aktywne walidacje Comparison Visualization Stage 1–2D1.

Windows Self-Hosted CI nie jest wymagany dla statycznego modułu Help, który nie używa Kvasera, CANlib ani sprzętu CAN.

## Formalne zatwierdzenie

Help Center Stage 1 jest ręcznie zaakceptowany jako funkcjonalny checkpoint.

Draft PR #55 pozostaje otwarty, nie jest oznaczony jako ready i nie został scalony. Nie wykonywać merge bez wyraźnego polecenia właściciela.

## Punkt dalszej kontynuacji

Po zakończeniu prac organizacyjnych wokół Help Center rozwój Comparison Visualization ma wrócić dokładnie do:

`Comparison Visualization Stage 2D2 — transakcje UDS na trwałej osi czasu`

## Nowa stała zasada projektu

Od tego checkpointu obowiązuje zasada:

> Każda nowa funkcja CRT, która została ręcznie zatwierdzona jako gotowa, musi w tym samym etapie otrzymać aktualny opis w Help Center.

Brak aktualizacji Pomocy albo jawnej decyzji `nie dotyczy` oznacza, że etap nie spełnia pełnej definicji ukończenia.

Szczegółowe wymagania zapisano w:

`docs/CRT_HELP_MAINTENANCE_POLICY_PL.md`
