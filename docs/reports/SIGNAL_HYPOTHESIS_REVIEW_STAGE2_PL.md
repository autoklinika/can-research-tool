# Signal Hypothesis Review — Stage 2

## Cel

Stage 2 dodaje operatorowy workflow `verify / reject / edit` dla trwałych artefaktów `signal_hypothesis`.

Najważniejsza zasada:

> Oryginalna hipoteza AI jest niezmienna. Każda decyzja operatora powstaje jako nowy artefakt append-only.

## Przepływ

`signal_candidates -> signal_hypothesis (AI, suggested) -> signal_hypothesis_review (operator)`

Stage 2 nie uruchamia AI i nie czyta RAW CAN.

## Artefakt

- type: `signal_hypothesis_review`
- schema: `crt.signal_hypothesis_review`
- schema_version: `1`
- provider: `crt.comparison.signal_hypothesis_review`

Każdy artefakt zapisuje:

- ID i SHA źródłowego `signal_hypothesis`,
- dokładny candidate key / CAN ID / Byte / Bit,
- decyzję operatora,
- notatkę audytową,
- listę edytowanych pól,
- pełny snapshot `effective_hypothesis`,
- guardraile potwierdzające brak mutacji źródła, brak AI, brak RAW i brak CAN TX.

## Decyzje operatora

### Potwierdź

Tworzy nowy review ze statusem `verified`.

Jeżeli operator wcześniej zmienił pola w edytorze, potwierdzenie zapisuje właśnie tę efektywną wersję oraz listę zmienionych pól. Źródłowy artefakt AI nadal pozostaje `suggested / verified=false`.

### Odrzuć

Tworzy nowy review ze statusem `rejected`.

Powód odrzucenia w `operator_note` jest obowiązkowy. Odrzucenie nie usuwa wcześniejszego potwierdzenia ani edycji — historia jest append-only, a najnowsza decyzja jest aktualnym stanem operatorskim.

### Zapisz edycję

Tworzy review ze statusem `edited` i `verified=false`.

Edycja wymaga faktycznej zmiany co najmniej jednego pola. Stage 2 pozwala edytować:

- name,
- physical_meaning,
- unit,
- scale,
- offset,
- rationale.

`next_experiments` i `warnings` pozostają snapshotem źródłowej hipotezy; ich rola jest pomocnicza, nie są wejściem do przyszłego Draft DBC.

## GUI

Stage 2 rozszerza istniejącą kartę `Signal Hypothesis` o sekcję `Decyzja operatora`:

- edytowalna nazwa,
- znaczenie/opis,
- unit / scale / offset,
- rationale,
- notatka decyzji,
- `Zapisz edycję`,
- `Potwierdź`,
- `Odrzuć`,
- status najnowszej decyzji i licznik historii.

Po wybraniu hipotezy GUI pokazuje efektywną treść z najnowszego review. Brak review oznacza, że hipoteza nadal jest tylko sugestią AI.

## Source-of-truth i audyt

- `signal_hypothesis` jest historycznym, niezmiennym wynikiem AI,
- `signal_hypothesis_review` jest autorytatywną decyzją operatora,
- najnowszy review reprezentuje aktualny stan operatorski,
- wszystkie starsze review pozostają w projekcie,
- SHA źródłowej hipotezy i sesji nie mogą się zmienić.

## Bezpieczeństwo

Provider review ma wyłącznie:

- `project.read`,
- `artifact.read`,
- `artifact.write`.

Celowo nie ma:

- `ai.use`,
- `session.read`,
- `can.tx`.

## Walidacja

Dedykowany workflow `Signal Hypothesis Review Stage 2 Validation` działa wyłącznie na Windows GitHub-hosted.

Sprawdza:

- verify bez edycji,
- edit z listą zmienionych pól,
- verify po edycji,
- reject z wymaganym powodem,
- brak artefaktu po niepoprawnej decyzji,
- append-only history,
- brak zmian źródłowego Signal Hypothesis,
- brak zmian SHA sesji,
- produkcyjny GUI smoke dla wszystkich trzech decyzji,
- regresję Stage 1 Signal Hypothesis.

## Następny etap

Draft DBC może później korzystać wyłącznie z najnowszego `signal_hypothesis_review` o statusie `verified`. Sama hipoteza AI `suggested` nigdy nie będzie wystarczającym wejściem do potwierdzonego Draft DBC.
