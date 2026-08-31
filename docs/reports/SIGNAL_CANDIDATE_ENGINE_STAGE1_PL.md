# Signal Candidate Engine Stage 1 — raport techniczny

## Status

Implementacja znajduje się na gałęzi `agent/signal-candidate-engine-stage1` i w draft PR #65. `main` nie jest modyfikowany przez ten etap do czasu ręcznego odbioru i jednoznacznej zgody właściciela.

## Cel

Signal Candidate Engine Stage 1 scala deterministyczne wyniki wcześniejszych etapów CRT w jeden trwały ranking kandydatów sygnałów:

`RAW → Signal Discovery → Experiment Diff → Signal Candidate Engine`

Stage 1 nie nadaje jeszcze kandydatom znaczenia fizycznego i nie tworzy DBC. Jego zadaniem jest wskazać, które konkretne bity mają najlepsze, audytowalne wsparcie eksperymentalne.

## Źródła danych

### Experiment Diff — wymagane

Candidate Engine wymaga co najmniej jednego artefaktu `experiment_marker_correlation` schema v1 dla analizowanego `ComparisonSet`.

Warstwa aplikacyjna wybiera najnowszy artefakt dla każdej unikalnej semantycznie konfiguracji:

- target marker selector,
- control marker selector,
- pre window,
- post window.

Wielokrotne uruchomienie dokładnie tego samego eksperymentu nie zwiększa więc sztucznie wagi kandydata.

### Signal Discovery — opcjonalne

Dla kluczy CAN występujących w wybranych wynikach Experiment Diff CRT wyszukuje najnowszy pasujący artefakt `signal_discovery_activity` dla każdej sesji zestawu.

Signal Discovery jest wyłącznie walidacją/enrichment. Brak artefaktu Signal Discovery:

- nie obniża `candidate_score`,
- nie powoduje odrzucenia kandydata,
- jest jawnie raportowany jako `activity_validation.status = unavailable`.

## Brak ponownego skanowania RAW

Candidate Engine nie otrzymuje `session.read` i nie iteruje po surowych ramkach CAN.

Jego manifest używa wyłącznie:

- `project.read`,
- `artifact.read`,
- `artifact.write`.

Wynik jest więc deterministycznym przetworzeniem wcześniej zapisanych artefaktów dowodowych.

## Extension API — artifact.read

Stage 1 dodaje formalne read-only `artifact.read` do Extension API.

Provider z tym uprawnieniem może pobrać `ArtifactSnapshot`, który:

- jest odczytywany przez istniejący `ArtifactCatalog`,
- wymaga poprawnej integralności SHA-256,
- nie udostępnia uchwytu SQLite ani ścieżki do zapisu,
- przechowuje metadata/payload jako niemodyfikowalne projekcje Mapping/tuple,
- respektuje cancellation token.

Provider bez `artifact.read` otrzymuje `PermissionError` przy próbie odczytu artefaktu.

`ArtifactWriter.write_json()` materializuje read-only Mapping/Sequence do zwykłych kontenerów JSON dopiero na kontrolowanej granicy zapisu artefaktu. Nie zmienia to treści dotychczasowych payloadów dict/list.

## Tożsamość kandydata

Kandydat bitowy jest jednoznacznie identyfikowany przez:

- channel,
- STD/EXT,
- arbitration ID,
- frame kind,
- byte index,
- bit index.

Canonical `candidate_key`:

`<message_key>:B<byte>.<bit>`

Przykład:

`0:STD:321:data:B0.2`

Ten sam `candidate_key` jest grupowany między różnymi eksperymentami.

## Ranking Stage 1

`candidate_score` jest najlepszym jawnym, deterministycznym `score` z Experiment Diff dla danego kandydata.

Candidate Engine nie dodaje ukrytych wag do tego score.

Dodatkowe supports są zachowane i uporządkowane według:

1. score malejąco,
2. liczby zmian target malejąco,
3. control change ratio rosnąco,
4. stabilnego artifact ID.

### Klasa strong

Wymaga jednocześnie:

- `score >= 0.75`,
- co najmniej 3 zmian target,
- direction consistency `>= 0.80`,
- control change ratio `<= 0.25`,
- brak sprzecznego `activity_validation.status = inconsistent`.

Brak Signal Discovery (`unavailable`) nie blokuje klasy strong.

### Klasa medium

- `score >= 0.40`,
- co najmniej 2 zmiany target.

### Klasa weak

Pozostałe kandydaty.

## Walidacja aktywności z Signal Discovery

Jeżeli istnieją pasujące artefakty, Candidate Engine agreguje dla kandydata:

- liczbę artefaktów,
- liczbę pokrytych sesji,
- coverage względem sesji ComparisonSet,
- liczbę obserwacji variable/constant,
- transition count,
- transition opportunity count,
- transition rate,
- set ratio,
- dokładne identyfikatory i SHA artefaktów źródłowych.

Status:

- `consistent` — co najmniej jeden pasujący artefakt pokazuje bit jako zmienny,
- `inconsistent` — pasujące artefakty istnieją, ale wszystkie pokazują bit jako stały,
- `unavailable` — brak pasującego artefaktu.

## Exact evidence

Candidate Engine nie tworzy nowych przybliżonych dowodów. Dziedziczy evidence z Experiment Diff i dopisuje pochodzenie eksperymentu.

Każde zachowane zdarzenie może zawierać:

- experiment artifact ID,
- target/control opis eksperymentu,
- session ID/name,
- marker snapshot,
- changed true/false,
- before/after state,
- delay,
- exact `before.source_row`,
- exact `after.source_row`,
- sequence/timestamp/DLC/payload zachowane przez Experiment Diff.

Lista jest jawnie bounded i zawiera `evidence_event_count` oraz `evidence_truncated`.

GUI umożliwia nawigację:

- `Otwórz stan PRZED`,
- `Otwórz stan PO`.

Nawigacja używa dokładnego `session_id + source_row`.

## Artefakt wynikowy

Typ:

`signal_candidates`

Schema:

`crt.signal_candidates` v1

Zawiera m.in.:

- wersje providera/algorytmu,
- ComparisonSet snapshot,
- exact IDs/SHA wejściowych artefaktów,
- jawny `ranking_contract`,
- summary strong/medium/weak,
- uporządkowane candidates,
- all supports,
- Signal Discovery validation,
- bounded exact evidence.

`ranking_contract.ai_used = false`.

## GUI

Dedykowana karta:

`Signal Candidates`

W produkcyjnym oknie porównania pokazuje:

- automatycznie wybrane źródła,
- przycisk `Zbuduj kandydatów`,
- progress/cancellation,
- trwałe zapisane wyniki,
- rank,
- strong/medium/weak,
- score,
- CAN ID / channel / STD-EXT / byte / bit,
- najlepszy eksperyment,
- Target/Control,
- direction,
- mean delay,
- Signal Discovery validation,
- wszystkie supports,
- exact evidence i nawigację do source_row.

## AI — granica Stage 1

AI nie jest częścią Signal Candidate Engine Stage 1.

Pierwszy planowany punkt integracji lokalnego AI to następny etap:

`Signal Hypothesis Stage 1`.

Planowany kontrakt:

`signal_candidates artifact + selected exact evidence → optional AI adapter → suggestion/hypothesis`

AI będzie mogło proponować m.in.:

- nazwę sygnału,
- prawdopodobne znaczenie fizyczne,
- jednostkę,
- scale/offset,
- możliwą interpretację pola wielobitowego,
- następny eksperyment potwierdzający.

AI nie może:

- zmieniać candidate_score,
- zastępować evidence,
- modyfikować RAW,
- blokować Candidate Engine,
- uruchamiać CAN TX/UDS/J1939,
- być wymagane do uruchomienia CRT.

Niedostępność AI ma oznaczać `AI unavailable/skipped`, nie awarię analizy deterministycznej.

## Walidacja automatyczna

Dodane testy obejmują:

- `artifact.read` permission boundary,
- immutable ArtifactSnapshot,
- wykrywanie SHA tampering,
- pełny pipeline Experiment Diff → Candidate Engine,
- deduplikację powtórzonego tego samego eksperymentu,
- Signal Discovery enrichment dla 2/2 sesji,
- expected strong candidate,
- exact evidence source_row,
- niezmienione SHA sesji źródłowych,
- zachowanie przy braku Experiment Diff,
- produkcyjny GUI smoke,
- Help Center smoke.

Dedykowany workflow Windows:

`Signal Candidate Engine Stage 1 Validation`

## Stan odbioru

Na tym etapie implementacja wymaga jeszcze końcowej walidacji CI dla finalnego HEAD oraz ręcznego testu właściciela. Do czasu tego odbioru PR #65 pozostaje draftem i nie może zostać scalony do `main`.
