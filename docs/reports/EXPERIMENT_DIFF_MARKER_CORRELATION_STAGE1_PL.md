# CAN Research Tool — Experiment Diff / marker correlation Stage 1

Data: 2026-08-31

Status: **implementacja na gałęzi roboczej; wymagany końcowy Windows CI i ręczny odbiór właściciela**

Gałąź:

`agent/experiment-diff-marker-correlation-stage1`

Baza produkcyjna:

`main` = `68f399b03e3a3ca9a9462be82016de8b7be2254e`

Draft PR:

`#63 — Add Experiment Diff marker correlation Stage 1`

---

## 1. Cel

Experiment Diff Stage 1 redukuje wiele zapisanych sesji CAN do rankingu bitów, których zachowanie powtarzalnie zmienia się po wybranym markerze eksperymentu.

Podstawowy przepływ:

```text
ComparisonSet
  -> markery testowe / kontrolne
  -> okna czasu przed i po markerze
  -> exact bit changes
  -> agregacja powtarzalności i timingu
  -> ranking kandydatów
  -> exact source_row przed / po zdarzeniu
```

Etap jest całkowicie pasywny i nie nadaje jeszcze kandydatom znaczenia fizycznego.

---

## 2. Źródła danych

### 2.1. Sesje

Jednostką analizy jest istniejący `ComparisonSet`. Wszystkie sesje pozostają niezmiennym źródłem prawdy.

### 2.2. Markery

Preferowanym źródłem markerów jest trwały sidecar:

`*.markers.jsonl`

Dzięki temu zaimportowane sesje CRT zachowują snapshot markera użyty w chwili eksperymentu. Jeżeli sidecar nie jest dostępny, istnieje read-only fallback do tabeli `session_markers`.

Tożsamość typu markera jest ustalana przede wszystkim przez zapisane `preset_id`. Późniejsza zmiana nazwy presetu nie dzieli historycznych zdarzeń tego samego typu. Dla markerów bez `preset_id` używany jest znormalizowany snapshot nazwy.

---

## 3. Marker testowy i kontrolny

Użytkownik wybiera:

- marker testowy `target`,
- opcjonalny marker kontrolny `control`,
- długość okna przed markerem,
- długość okna po markerze.

Marker kontrolny nie jest wymagany, ale istotnie zwiększa wartość rankingu, ponieważ pozwala odróżnić zmianę związaną z eksperymentem od zmiany występującej również w sytuacji kontrolnej.

Przykład docelowego wyniku:

```text
CAN ID 0x18FF2700 / Byte 2 / Bit 5
Target:  7/7
Control: 0/5
Direction: 0->1, 100%
Mean delay: 14.2 ms
```

---

## 4. Dokładna semantyka jednego zdarzenia

Dla każdego markera i każdego dokładnego klucza wiadomości:

1. w oknie `pre` CRT znajduje ostatnią obserwowaną ramkę przed timestampem markera,
2. ta ramka definiuje stan bazowy bajtów i bitów,
3. w oknie `post` CRT obserwuje kolejne pasujące ramki,
4. dla każdego bitu zapisuje pierwszą ramkę, w której bit różni się od stanu bazowego,
5. jeżeli bit nie zmieni się, zachowuje ostatnią kwalifikującą obserwację po markerze jako dowód `no-change`.

Kandydat ma dokładny klucz:

- kanał,
- CAN ID,
- STD / EXT,
- typ ramki data / RTR / error,
- indeks bajtu,
- indeks bitu.

Stage 1 analizuje pojedyncze bity. Wielobitowe pola Intel/Motorola należą do późniejszego Signal Candidate Engine.

---

## 5. Eligibility i denominatory

Wynik `Target 7/7` nie oznacza automatycznie wszystkich markerów zapisanych w projekcie.

Zdarzenie jest `eligible` dla konkretnego bitu tylko wtedy, gdy:

- odpowiedni klucz CAN został zaobserwowany w oknie przed markerem,
- odpowiedni bajt istniał w payloadzie,
- po markerze istnieje kwalifikująca obserwacja tego samego bajtu w oknie `post`.

Brak ramki lub brak bajtu przy zmiennym DLC nie jest sztucznie liczony jako brak zmiany.

Artefakt zapisuje osobno:

- całkowitą liczbę markerów target/control,
- liczbę `eligible` dla kandydata,
- liczbę zdarzeń z wykrytą zmianą.

Dzięki temu UI może pokazać np. `2/2`, `0/2`, ale również `2/4` albo `0/0` bez ukrywania braku pokrycia danych.

---

## 6. Timing

Dla zdarzeń ze zmianą:

```text
delay_ns = timestamp pierwszej zmiany - timestamp markera
```

Dla kandydata target zapisywane są:

- liczba próbek timingu,
- minimum,
- maksimum,
- średnia,
- mediana.

Dla `no-change` delay pozostaje pusty, ponieważ nie istnieje timestamp pierwszej zmiany.

---

## 7. Jawny deterministyczny score

Stage 1 używa:

```text
score = target_support
      * target_coverage
      * control_specificity
      * direction_consistency
```

Gdzie:

- `target_support` = zmienione targety / eligible targety,
- `target_coverage` = eligible targety / wszystkie targety,
- `control_specificity` = `1 - control_change_rate` dla kwalifikujących kontroli; bez danych kontrolnych = 1,
- `direction_consistency` = udział dominującego kierunku `0->1` albo `1->0` w zmianach target.

Score nie jest prawdopodobieństwem fizycznego znaczenia sygnału. Jest deterministycznym rankingiem dowodowym służącym do zawężenia materiału.

**AI nie uczestniczy w obliczeniu score.**

---

## 8. Evidence-first

Każdy zachowany evidence event zawiera:

- `session_id`,
- nazwę sesji,
- pełny snapshot markera,
- target/control,
- changed / no-change,
- stan bitu przed i po,
- delay dla zmiany,
- ramkę `before`:
  - exact `source_row`,
  - sequence,
  - timestamp,
  - DLC,
  - payload,
- ramkę `after`:
  - exact `source_row`,
  - sequence,
  - timestamp,
  - DLC,
  - payload.

Lista evidence jest jawnie bounded przez limit artefaktu.

Ważny kontrakt:

> również twierdzenie `Control 0/N` ma być audytowalne.

Dlatego artefakt przechowuje nie tylko zdarzenia ze zmianą, lecz także kwalifikujące `no-change` evidence. Użytkownik może otworzyć ramkę przed markerem i obserwację po markerze, na której badany bit nadal ma ten sam stan.

---

## 9. Trwały artefakt

Provider:

`crt.comparison.experiment_marker_correlation`

Artefakt:

`experiment_marker_correlation`

Schemat:

`crt.experiment_marker_correlation` v1

Artefakt posiada źródła dla wszystkich sesji zestawu i fingerprinty sesji.

---

## 10. GUI

W produkcyjnym oknie porównania dodana jest karta:

`Experiment Diff`

Karta zawiera:

- wybór markera testowego,
- opcjonalny marker kontrolny,
- okno pre/post,
- uruchomienie/anulowanie analizy w tle,
- selector zapisanych artefaktów,
- ranking kandydatów,
- selector powtórzeń/evidence,
- nawigację do exact ramki przed markerem,
- nawigację do exact ramki po markerze.

Kolumny rankingu pokazują m.in.:

- score,
- CAN ID,
- byte/bit,
- Target,
- Control,
- kierunek,
- spójność,
- średni i medianowy delay.

---

## 11. Bezpieczeństwo

Stage 1 jest całkowicie pasywny.

Bez zmian pozostają:

- `CaptureService`,
- backend Kvaser / CANlib,
- CAN TX/RX,
- format surowej sesji,
- markery źródłowe,
- kolejność ramek,
- existing comparison artifacts.

Analiza ma prywatny, `passive_only=True`, `ai_enabled=False` registry. Provider nie jest wciskany do zwykłego bezparametrowego dropdownu istniejących providerów comparison; korzysta z dedykowanej warstwy `ExperimentDiffService`.

---

## 12. AI

Lokalne AI nie jest używane w Stage 1.

To celowe. Najpierw CRT tworzy stabilny deterministyczny artefakt i ranking evidence. W późniejszym etapie lokalne AI może dostać ograniczony artefakt i np.:

- wyjaśnić najbardziej prawdopodobne znaczenie kandydatów,
- pogrupować podobne zmiany,
- zaproponować następny eksperyment,
- zasugerować pola do Signal Candidate Engine.

Awaria AI nie może wpływać na działanie Experiment Diff ani pozostałych funkcji CRT.

---

## 13. Walidacja automatyczna

### Core

`tests/test_experiment_marker_correlation.py`

Test syntetyczny wymaga:

- 2 target markerów,
- 2 control markerów,
- CAN ID `0x123`, Byte 0, Bit 2,
- targety `0->1` po 12 ms i 16 ms,
- wynik target `2/2`,
- control `0/2`,
- direction consistency 100%,
- mean/median 14 ms,
- exact target evidence `source_row 0 -> 1`,
- exact control no-change evidence `source_row 2 -> 3`,
- brak modyfikacji SHA-256 sesji.

Drugi test potwierdza grupowanie markerów przez immutable captured `preset_id` mimo zmiany snapshotu nazwy.

### Production GUI smoke

`tests_gui/experiment_diff_smoke.py`

Sprawdza:

- discovery markerów,
- uruchomienie background analysis,
- ranking `2/2` vs `0/2`,
- timing 14 ms,
- zapis/reload artefaktu,
- exact evidence target,
- exact no-change control evidence,
- brak modyfikacji sesji,
- obecność karty `Experiment Diff` w produkcyjnym comparison window.

### Dedicated Windows CI

`.github/workflows/experiment-diff-marker-correlation-stage1.yml`

Nazwa:

`Experiment Diff Marker Correlation Stage 1 Validation`

Platforma:

`windows-latest`

Pierwszy checkpoint core + production GUI przeszedł poprawnie przed finalnym rozszerzeniem evidence no-change i Help Center. Końcowy HEAD musi ponownie przejść pełny workflow.

---

## 14. Help Center

Temat:

`experiment-diff-marker-correlation — Experiment Diff — korelacja zmian z markerami`

Opisuje:

- target/control,
- eligibility,
- okna czasu,
- score,
- timing,
- exact evidence,
- no-change controls,
- brak AI w rankingu,
- brak CAN TX.

---

## 15. Świadomie poza zakresem Stage 1

Nie implementujemy jeszcze:

- korelacji pól wielobitowych,
- automatycznego Signal Candidate Engine,
- rolling counter/checksum/CRC candidate,
- Signal Hypothesis,
- Draft DBC,
- automatycznego znaczenia fizycznego sygnału,
- integracji lokalnego AI,
- aktywnego skanowania UDS/J1939,
- żadnego CAN TX.

---

## 16. Warunek ręcznego odbioru

Przed merge wymagane są:

1. zielony dedicated Windows CI na finalnym HEAD,
2. zielony Windows GitHub-Hosted CI i właściwe GUI/Help regressions,
3. test na rzeczywistych zapisanych sesjach z markerami,
4. potwierdzenie sensowności rankingu kandydatów,
5. potwierdzenie `PRZED -> exact source_row`,
6. potwierdzenie `PO -> exact source_row`,
7. jeżeli istnieje marker kontrolny — sprawdzenie evidence także dla `no-change`,
8. ręczne sprawdzenie artykułu Help Center.

PR #63 pozostaje draftem. Bez osobnej, jednoznacznej zgody właściciela nie oznaczać jako ready i nie wykonywać merge do `main`.
