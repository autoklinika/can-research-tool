# CRT — Signal Discovery Stage 1 — handoff

Data: 2026-08-30

## Aktualny punkt

Rozwijany etap:

`Signal Discovery Workspace Stage 1 — Byte/Bit Activity Map + ręczny Arbitrary Bitfield Inspector/Plotter + evidence navigation do source_row`

Gałąź:

`agent/signal-discovery-stage1`

Draft PR:

`#61`

Baza:

`main = daf0e8328ee30932e1a286ad44cebb3616f1fdba`

Nie wykonywać merge do `main` i nie oznaczać PR jako ready bez wyraźnej zgody właściciela.

---

## Co jest zaimplementowane

1. built-in analysis provider `crt.analysis.signal_discovery_activity`,
2. pełny skan aktywności dokładnego klucza CAN,
3. Byte/Bit Activity Map,
4. continuity-aware transition rate przy zmiennym DLC,
5. dokładne source_row MIN/MAX,
6. bounded deterministyczna próbka do 5000 ramek,
7. arbitrary bitfield:
   - Intel,
   - Motorola CANdb++/DBC,
   - signed/unsigned,
   - start bit 0…,
   - length 1–64,
   - scale/offset,
8. własny wykres bez dodatkowej zależności charting,
9. punkt wykresu → dokładny source_row,
10. trwały artefakt `crt.signal_discovery_activity` v1,
11. dedykowany Windows-only workflow,
12. testy rdzenia,
13. produkcyjny GUI smoke,
14. artykuł Help Center `signal-discovery`,
15. smoke Help Center,
16. raport techniczny Stage 1.

---

## Wykryte i poprawione podczas implementacji

### Motorola test boundary

Pierwszy CI wykazał błędne oczekiwanie testu dla CANdb++ saw-tooth. `start_bit=0,length=9` jest legalne. Poprawiono test, nie dekoder.

### Zmienny DLC

Przerwa, w której bajt nie istnieje, nie może tworzyć fikcyjnego przejścia wartości. Dodano jawny `transition_opportunity_count` i mianownik liczony tylko dla ciągłych obserwacji.

### Activity Map B7…B0

Pierwsza wersja tabeli generowała o jedną wartość za dużo i dublowała B1. Poprawiono mapowanie na:

`B7 B6 B5 B4 B3 B2 B1/B0`

oraz dodano regresję GUI sprawdzającą ostatnią kolumnę.

### Porządek PR

GitHub automatycznie otworzył techniczny #60 jako niedraftowy. Konektor nie potrafił wykonać `Convert to draft` z powodu błędu GraphQL `fullDatabaseId`. #60 został zamknięty bez merge, a właściwy PR #61 został utworzony od razu jako draft.

---

## Co trzeba zrobić przed ręcznym testem

1. poczekać na końcowe workflowy dla finalnego HEAD,
2. sprawdzić dedykowany `Signal Discovery Stage 1 Validation`,
3. sprawdzić `Windows GitHub-Hosted CI`, `GUI Regressions`, `Help Center Validation`, `Tests` i istotne regresje,
4. w przypadku błędu naprawić przyczynę na gałęzi,
5. wpisać finalny checkpoint SHA do PR/raportu,
6. dopiero potem poprosić właściciela o ręczny odbiór Windows.

---

## Plan ręcznego odbioru

Na rzeczywistej zapisanej sesji:

1. otworzyć sesję,
2. wejść w `Signal Discovery`,
3. wybrać CAN ID, który realnie występuje w logu,
4. uruchomić `Analizuj aktywność`,
5. sprawdzić czy mapa bajtów/bitów wygląda logicznie,
6. wybrać bajt i otworzyć MIN oraz MAX,
7. potwierdzić przejście do właściwych surowych ramek,
8. ustawić ręczny bitfield i przeliczyć wykres,
9. kliknąć punkt wykresu i otworzyć źródło,
10. potwierdzić dokładną ramkę,
11. sprawdzić Intel i Motorola na znanym/intuicyjnym polu, jeśli log na to pozwala,
12. otworzyć Pomoc i wyszukać `signal discovery`,
13. ocenić czy UX jest czytelny i przydatny do realnego reverse engineeringu.

---

## Co będzie następne po akceptacji Stage 1

Najbliższy logiczny etap roadmapy:

`Experiment Diff / marker correlation`

Cel:

`sesja/eksperyment A vs B → CAN ID zmieniające zachowanie → bajty/bity skorelowane z eksperymentem → ranking kandydatów → dokładne dowody source_row`

Dopiero później:

- Signal Candidate Engine,
- Signal Hypothesis,
- Draft DBC,
- Heavy-Duty Passive Discovery.
