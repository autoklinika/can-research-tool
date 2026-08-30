# CRT Help Center Stage 1 — handoff do kolejnej rozmowy

## Repozytorium

`autoklinika/can-research-tool`

## Gałąź

`agent/help-center-stage1`

## Stacked PR

Draft PR #55, baza:

`agent/comparison-visualization-stage2d1-uds-transaction-explorer`

Nie oznaczać PR jako ready i nie wykonywać merge bez jednoznacznego polecenia
właściciela.

## Funkcjonalny checkpoint

`584e97d2d663647f18ab6e9dd77a2fdfccc479f0`

## Dokumentacja

- `docs/reports/CRT_HELP_CENTER_STAGE1_PL.md`,
- `docs/reports/CRT_HELP_CENTER_STAGE1_HANDOFF_NEXT_CHAT_PL.md`,
- `docs/reports/COMPARISON_VISUALIZATION_STAGE2D1_MANUAL_ACCEPTANCE_AND_HELP_HANDOFF_PL.md`.

## Dostarczone funkcje

- menu `Pomoc`,
- `F1` otwierające stronę główną Help Center,
- szybkie akcje do startu, słownika i skrótów,
- jedna zakładka `Pomoc`,
- ponad 30 artykułów w 10 kategoriach,
- wyszukiwarka pełnotekstowa odporna na polskie znaki, w tym `ł`,
- drzewo tematów,
- historia Wstecz/Dalej,
- linki powiązane,
- skróty `Ctrl+F`, `Alt+Left`, `Alt+Right`,
- publiczny hook `open_help_topic()` do przyszłej pomocy kontekstowej,
- lokalne działanie bez projektu, sieci i dostępu do sesji.

## Walidacja

Dla funkcjonalnego checkpointu zielone były:

- Help Center Validation na Ubuntu i Windows,
- testy katalogu i wyszukiwarki,
- produkcyjny smoke GUI,
- pełny pytest,
- Windows GitHub-Hosted CI,
- GUI Regressions,
- dashboard i wszystkie wcześniejsze etapy Comparison Visualization,
- Live Preview Capacity.

Ogólny `Tests/gui-smoke` pozostawał w trakcie podczas zapisu raportu. Windows
Self-Hosted CI nie jest wymagany dla etapu bez sprzętu CAN.

## Test ręczny do wykonania

1. Uruchomić CRT bez projektu.
2. Nacisnąć F1.
3. Sprawdzić stronę główną i drzewo tematów.
4. Wyszukać `zrodlo prawdy`, `jitter percentyl`, `0x78 odpowiedz koncowa`,
   `brak wynikow` i `Kvaser bitrate`.
5. Sprawdzić linki powiązane, historię i skróty.
6. Otworzyć pozycje menu `Szybki start`, `Słownik pojęć` i
   `Skróty klawiaturowe`.
7. Potwierdzić brak duplikowania zakładki `Pomoc`.
8. Otworzyć projekt i sprawdzić, czy główne funkcje programu nadal działają.

Po potwierdzeniu dopisać ręczny checkpoint do raportu i PR #55.

## Dokładny punkt kontynuacji rozwoju CRT

Rozwój Comparison Visualization został świadomie zatrzymany po ręcznie
zaakceptowanym Stage 2D1.

Po zakończeniu Help należy wrócić do:

`Comparison Visualization Stage 2D2 — transakcje UDS na trwałej osi czasu`

Planowany zakres Stage 2D2:

- pas transakcji UDS na trwałej osi czasu,
- odcinki request → first response → final response,
- oznaczenia odpowiedzi pozytywnych, negatywnych, `0x78`, timeoutów i końca
  logu,
- wykorzystanie trwałych wyrównań Stage 2B,
- wykorzystanie artefaktów Stage 2C2 i widoku Stage 2D1,
- synchronizacja wyboru osi z eksploratorem transakcji,
- filtry SID, DID, Routine ID, NRC i statusu,
- nawigacja do dokładnych ramek,
- brak ponownego skanowania surowych sesji.

## Nienaruszalne ograniczenia

Nie zmieniać bez osobnej decyzji architektonicznej:

- CaptureService,
- Kvasera i lifecycle CANlib,
- CAN TX/RX,
- formatu sesji, markerów i kolejności surowych ramek,
- trwałych indeksów,
- bounded modelu zapisanych sesji,
- schematu `.crt/project.sqlite`.
