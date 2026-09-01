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
- provider version: `1.0.2`
- algorithm version: `3`
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
- najlepszy support Experiment Diff,
- opcjonalna walidacja Signal Discovery,
- maksymalnie 8 exact evidence domyślnie,
- dla evidence tylko wybrane pola: grupa, stan przed/po, delay, marker, `source_row`, payload wybranej ramki,
- jawny `response_contract` v2,
- opcjonalny krótki kontekst operatora.

Nie trafia:

- pełna sesja,
- strumień wszystkich ramek,
- plik RAW CAN,
- baza projektu,
- konfiguracja aktywnej transmisji.

## Lokalny adapter AI

Stage 1 implementuje dependency-free klient OpenAI-compatible Chat Completions dla lokalnych serwerów takich jak Ollama.

Konfiguracja:

- Local AI URL,
- model,
- timeout 1–120 s,
- opcjonalnie środowisko `CRT_AI_BASE_URL`, `CRT_AI_MODEL`, `CRT_AI_TIMEOUT_S`, `CRT_AI_API_KEY`.

GUI zapisuje URL/model/timeout lokalnie w `QSettings`.

Domyślna wartość modelu w Stage 1 pozostaje `qwen3.6:35b-hermes64k`; model jest konfigurowalny i CRT nie wymaga konkretnej rodziny LLM.

### Ograniczenie endpointu

Stage 1 akceptuje tylko:

- localhost,
- prywatne IP LAN,
- link-local,
- hosty `.local` / `.lan`,
- jednoczłonowe nazwy hostów LAN.

Publiczne endpointy AI są odrzucane. Celem jest uniknięcie przypadkowego wysłania artefaktów poza lokalną infrastrukturę.

## Odpowiedź AI — kontrakt v2

Transport wymusza `response_format = {"type": "json_object"}`, ale poprawny JSON **nie jest wystarczający**. Provider wykonuje dodatkową walidację semantyczną przed utworzeniem artefaktu.

Model musi zwrócić wszystkie pola:

- `name`,
- `physical_meaning`,
- `unit`,
- `scale`,
- `offset`,
- `confidence`,
- `rationale`,
- `next_experiments`,
- `warnings`.

Wymagania:

- `name`, `physical_meaning` i `rationale` muszą być niepustymi stringami,
- `confidence` musi być skończoną liczbą 0–1; CRT nie clampuje błędnej wartości,
- `next_experiments` musi zawierać co najmniej jeden konkretny eksperyment weryfikacyjny,
- `warnings` musi zawierać co najmniej jedno ostrzeżenie,
- `unit`, `scale`, `offset` mogą być `null`, jeżeli brak podstaw do ich określenia,
- zły typ pola powoduje odrzucenie odpowiedzi.

Jeżeli znaczenie fizyczne jest nieznane, model nie ma zwracać `{}` ani pustych pól. Prompt wymaga neutralnego fallbacku, np. `unknown_bit_state_candidate`, jawnego opisu niepewności, niskiego confidence, testu rozstrzygającego i ostrzeżenia, że nazwa markera nie jest dowodem semantyki.

`confidence` jest wyłącznie pewnością modelu i **nie jest** score CRT.

### Odrzucona odpowiedź

Jeżeli JSON jest pusty, niekompletny lub semantycznie wadliwy:

- provider kończy operację błędem **przed `artifact.write`**,
- nie powstaje nowy `signal_hypothesis`,
- Candidate Engine i źródła pozostają niezmienione,
- błąd zawiera krótki, ograniczony `response_excerpt` surowej odpowiedzi modelu,
- wadliwa odpowiedź nie jest promowana do wyniku.

Dla zaakceptowanej odpowiedzi artefakt zapisuje `response_sha256`, `response_contract_version=2` i informację o użytym `json_object`; pełna surowa odpowiedź nie jest duplikowana w artefakcie.

## Migracja wcześniejszego kontraktu

Pierwszy realny test z lokalnym Ollama wykazał, że poprzedni kontrakt v1 akceptował dowolny JSON-object i normalizował brakujące pola do pustych wartości. W rezultacie możliwe było zapisanie wyniku typu `bez nazwy / confidence 0.00 / brak rationale`.

To zachowanie zostało usunięte. Aktualny artefakt ma `schema_version=2`. `SignalHypothesisService` pokazuje jako aktualne hipotezy tylko schema v2. Starsze schema v1 pozostają w projekcie jako ślad historyczny, ale nie są traktowane jako aktualne hipotezy.

## Status hipotezy

Każdy poprawnie zwalidowany artefakt Stage 1 zapisuje:

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
- `ai_failure_blocks_crt = false`,
- `semantic_response_validation = true`.

## Awaria AI

Błąd połączenia, timeout, niepoprawny JSON, odrzucona semantycznie odpowiedź albo anulowanie:

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
- lista zapisanych aktualnych hipotez schema v2,
- wyświetlenie nazwy, znaczenia, unit/scale/offset, confidence, rationale, next experiments i warnings.

Samo otwarcie karty nie tworzy klienta sieciowego i nie wykonuje żadnego requestu.

## CI

Dedykowany workflow:

`Signal Hypothesis AI Stage 1 Validation`

Windows GitHub-hosted. CI **nie łączy się z realnym serwerem AI**. Używa fake local AI i sprawdza:

- Extension API / `ai.use`,
- candidate artifact -> hypothesis,
- zachowanie score i SHA źródeł,
- bounded context bez RAW,
- strict response contract v2,
- odrzucenie `{}` i niekompletnego JSON bez utworzenia artefaktu,
- odrzucenie pustej semantycznie hipotezy,
- odrzucenie confidence poza 0–1 zamiast clampowania,
- bounded `response_excerpt` dla diagnostyki,
- odrzucenie publicznego endpointu,
- zachowanie przy AI unavailable,
- production GUI smoke,
- brak requestu przy samym otwarciu karty,
- Help Center.

## Manual acceptance

Po zielonym CI test na realnym lokalnym Ollama:

1. Otwórz zestaw z wcześniej zbudowanym `Signal Candidates`.
2. Karta `Signal Hypothesis`.
3. Local AI URL: lokalny endpoint Ollama `/v1`.
4. Model: `qwen3.6:35b-hermes64k` lub inny jawnie wybrany model lokalny.
5. Timeout dla dużego modelu: do 120 s.
6. Zaznacz `0x321 / Byte0 / Bit2` z testowych wirtualnych logów.
7. Kliknij `Zaproponuj hipotezę AI`.
8. Oczekiwane:
   - operacja kończy się bez blokady GUI,
   - powstaje tylko zwalidowany `signal_hypothesis` schema v2,
   - source candidate nadal ma score `1.000` i class `strong`,
   - status `suggested / verified=false`,
   - AI proponuje ostrożną interpretację albo neutralnie wskazuje niepewność,
   - next experiment ma charakter weryfikacyjny, nie automatycznie potwierdzający,
   - warnings nie jest puste.
9. Jeżeli model zwróci pusty/niepełny JSON:
   - CRT ma pokazać `AI response rejected` wraz z krótkim `response_excerpt`,
   - nie może powstać nowy artefakt hipotezy.
10. Następnie wyłącz/zablokuj AI endpoint i ponów:
   - tylko Signal Hypothesis ma pokazać `AI unavailable/error`,
   - Signal Candidates i pozostałe zakładki nadal działają.

## Po Stage 1

Najbliższy etap po ręcznej akceptacji:

- mechanizm operatorowego `verify/reject/edit` dla hipotezy,
- następnie Draft DBC oparty wyłącznie o hipotezy jawnie zweryfikowane przez operatora.
