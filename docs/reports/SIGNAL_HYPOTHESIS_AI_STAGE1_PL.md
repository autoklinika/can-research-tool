# Signal Hypothesis + lokalne AI — Stage 1

## Cel

Signal Hypothesis jest pierwszą warstwą CRT korzystającą z lokalnego LLM. Jej zadaniem nie jest wykrywanie sygnałów ani zmiana rankingu, lecz **interpretacja jednego gotowego kandydata** z trwałego artefaktu `signal_candidates`.

Kontrakt nadrzędny:

> CRT ma być lepszy dzięki lokalnemu AI, ale nigdy zależny od lokalnego AI.

Pipeline:

`RAW CAN -> Signal Discovery -> Experiment Diff -> Signal Candidate Engine -> Signal Hypothesis (opcjonalne AI) -> później Draft DBC`

## Source-of-truth

Deterministyczny artefakt `signal_candidates` pozostaje źródłem prawdy. Signal Hypothesis nie może zmienić:

- `candidate_score`,
- klasy `strong/medium/weak`,
- Target/Control,
- direction consistency,
- timing,
- Signal Discovery validation,
- exact evidence ani `source_row`.

AI tworzy wyłącznie osobny artefakt sugestii.

## Provider

- ID: `crt.comparison.signal_hypothesis_ai`
- artifact type: `signal_hypothesis`
- schema: `crt.signal_hypothesis` v2
- typ providera: comparison

Permissions:

- `project.read`
- `artifact.read`
- `artifact.write`
- `ai.use`

Celowo brak:

- `session.read`
- `can.tx`

Provider nie ma technicznej ścieżki do RAW CAN ani aktywnej transmisji.

## Dane wysyłane do AI

Do modelu trafia ograniczony, strukturalny kontekst dla jednego kandydata:

- candidate key,
- CAN ID / channel / STD-EXT / Byte / Bit,
- rank, class, deterministic score,
- numeryczne wsparcie Experiment Diff,
- zagregowana walidacja Signal Discovery,
- maksymalnie 8 exact evidence domyślnie,
- dla evidence tylko grupa target/control, stan przed/po, delay, `source_row` i payload wybranej ramki,
- opcjonalny krótki kontekst operatora.

Nie trafia:

- pełna sesja,
- strumień wszystkich ramek,
- plik RAW CAN,
- baza projektu,
- konfiguracja aktywnej transmisji,
- nazwy markerów i ich notatki,
- etykiety eksperymentów takie jak `TEST_EGR`,
- nazwy sesji.

### Label-blind context / anti-bias

Realny test Qwen3.6 pokazał, że model zakotwiczył się na etykiecie `TEST_EGR` i zaczął dopowiadać semantykę EGR, której evidence nie potwierdzało. Dlatego Signal Hypothesis ma teraz politykę `label-redacted-v1`:

- deterministyczne artefakty CRT zachowują oryginalne nazwy i evidence bez zmian,
- przed requestem do LLM usuwane są nazwy markerów, notatki, etykiety eksperymentu i nazwy sesji,
- do modelu pozostają liczby, kierunek zmiany, timing, target/control i exact payload/source_row,
- jedynym świadomym kanałem semantycznej wskazówki jest `operator_context` wpisany przez operatora w GUI.

To usuwa efekt „nazwa testu = znaczenie sygnału” bez utraty audytowalnego evidence w CRT.

## Lokalny adapter AI

Stage 1 implementuje dependency-free klient OpenAI-compatible Chat Completions dla lokalnych serwerów takich jak Ollama.

Konfiguracja:

- Local AI URL,
- model,
- timeout,
- opcjonalnie środowisko `CRT_AI_BASE_URL`, `CRT_AI_MODEL`, `CRT_AI_TIMEOUT_S`, `CRT_AI_API_KEY`, `CRT_AI_MAX_TOKENS`, `CRT_AI_REASONING_EFFORT`.

GUI zapisuje URL/model/timeout lokalnie w `QSettings`.

Dla Signal Hypothesis domyślny request jest ograniczony i audytowalny:

- `reasoning_effort = none`,
- `max_tokens = 768`,
- `temperature = 0`,
- `stream = false`,
- `response_format = json_object`.

Realny pomiar `qwen3.6:35b-hermes64k` pokazał prosty request JSON w ok. 22,9 s. Wcześniejszy pełny request przekraczał 120 s; po wyłączeniu extended reasoning problem timeoutu został usunięty z warstwy requestu.

### Ograniczenie endpointu

Stage 1 akceptuje tylko:

- localhost,
- prywatne IP LAN,
- link-local,
- hosty `.local` / `.lan`,
- jednoczłonowe nazwy hostów LAN.

Publiczne endpointy AI są odrzucane. Celem jest uniknięcie przypadkowego wysłania artefaktów poza lokalną infrastrukturę.

## Odpowiedź AI — kontrakt v2

Model ma zwrócić JSON z polami:

- `name`,
- `physical_meaning`,
- `unit`,
- `scale`,
- `offset`,
- `confidence`,
- `rationale`,
- `next_experiments`,
- `warnings`.

`confidence` jest wyłącznie pewnością modelu i **nie jest** score CRT.

Pusty JSON lub semantycznie pusta odpowiedź są odrzucane przed `artifact.write`.

Realny test pokazał również, że Qwen może zwrócić treściwą hipotezę, ale pominąć część pól kontraktu. Dlatego polityka `safe-nonsemantic-v1` dopuszcza wyłącznie bezpieczną naprawę braków, które nie tworzą nowej semantyki:

- brak `unit` -> `null`,
- brak `scale` -> `null`,
- brak `offset` -> `null`,
- brak `confidence` przy istniejącej treściwej hipotezie -> `0.0` oraz jawny warning, że model pominął confidence.

Nie są automatycznie uzupełniane `name`, `physical_meaning`, `rationale`, `next_experiments` ani `warnings`. Jeśli ich brakuje lub są puste, wynik jest odrzucany.

Przy odrzuceniu komunikat zawiera bounded `response_excerpt`. Poprawny artefakt zapisuje `response_sha256`, `response_contract_version=2` oraz w `ai.usage` informacje o polityce kontekstu/naprawy odpowiedzi. Pełna surowa odpowiedź modelu nie jest zapisywana.

## Status hipotezy

Każdy artefakt Stage 1 zapisuje:

- `status = suggested`,
- `verified = false`,
- `ai_generated = true`.

Nie ma automatycznego potwierdzania ani automatycznej promocji do DBC.

## Guardrails zapisane w artefakcie

Artefakt zawiera jawny kontrakt:

- `source_of_truth = signal_candidates`,
- `candidate_score_modified = false`,
- `raw_session_access = false`,
- `can_tx = false`,
- `active_diagnostics = false`,
- `automatic_confirmation = false`,
- `ai_failure_blocks_crt = false`.

## Awaria AI

Błąd połączenia, timeout, niepoprawny JSON albo anulowanie:

- kończy tylko operację Signal Hypothesis,
- nie modyfikuje Candidate Engine,
- nie modyfikuje źródłowych sesji,
- nie blokuje GUI CRT,
- nie blokuje Signal Discovery / Experiment Diff / Candidate Engine / evidence / eksportów.

GUI wykonuje AI w `QThreadPool`, więc request nie blokuje głównego wątku Qt.

Anulowanie aktywnego HTTP jest best-effort; request zakończy się najpóźniej po skonfigurowanym timeout.

## GUI Stage 1

Nowa karta `Signal Hypothesis` w oknie analizy zestawu porównawczego:

- konfiguracja Local AI URL,
- model,
- timeout,
- wybór zapisanego artefaktu Signal Candidates,
- tabela kandydatów,
- opcjonalny kontekst operatora,
- `Zaproponuj hipotezę AI`,
- `Anuluj`,
- progress/status,
- lista zapisanych hipotez,
- wyświetlenie nazwy, znaczenia, unit/scale/offset, confidence, rationale, next experiments i warnings.

Samo otwarcie karty nie tworzy klienta sieciowego i nie wykonuje żadnego requestu.

## CI

Dedykowany workflow:

`Signal Hypothesis AI Stage 1 Validation`

Windows GitHub-hosted. CI **nie łączy się z realnym serwerem AI**. Używa fake local AI i sprawdza m.in.:

- Extension API / `ai.use`,
- candidate artifact -> hypothesis,
- zachowanie score i SHA źródeł,
- bounded context bez RAW,
- redakcję `TEST_EGR` / nazw markerów / nazw sesji z machine context,
- zachowanie jawnego `operator_context`,
- response contract v2,
- bezpieczny fallback brakujących unit/scale/offset/confidence,
- odrzucenie pustego `{}`,
- request contract: reasoning off + bounded completion + JSON mode,
- odrzucenie publicznego endpointu,
- zachowanie przy AI unavailable,
- production GUI smoke,
- Help Center.

## Manual acceptance

Po zielonym CI test na realnym lokalnym Ollama:

1. Otwórz zestaw z wcześniej zbudowanym `Signal Candidates`.
2. Karta `Signal Hypothesis`.
3. Local AI URL: lokalny endpoint Ollama `/v1`.
4. Model: `qwen3.6:35b-hermes64k`.
5. Timeout: 120 s.
6. Zaznacz `0x321 / Byte0 / Bit2` z testowych wirtualnych logów.
7. Pierwszy test wykonaj z pustym `Kontekst operatora`.
8. Oczekiwane:
   - operacja kończy się bez blokady GUI,
   - powstaje `signal_hypothesis`,
   - source candidate nadal ma score `1.000` i class `strong`,
   - status `suggested / verified=false`,
   - bez kontekstu operatora AI nie powinno wywnioskować „EGR” tylko z nazwy testu, bo nazwa nie trafia do promptu,
   - hipoteza powinna opisać nieznany bit skorelowany z targetem i zaproponować test weryfikacyjny.
9. Następnie można wpisać jawny kontekst operatora i sprawdzić, czy model używa go wyłącznie jako wskazówki, a nie potwierdzenia.
10. Wyłącz/zablokuj AI endpoint i ponów:
   - tylko Signal Hypothesis ma pokazać `AI unavailable/error`,
   - Signal Candidates i pozostałe zakładki nadal działają.

## Po Stage 1

Najbliższy etap po ręcznej akceptacji:

- mechanizm operatorowego `verify/reject/edit` dla hipotezy,
- następnie Draft DBC oparty wyłącznie o hipotezy jawnie zweryfikowane przez operatora.
