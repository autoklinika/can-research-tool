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
- provider version: `1.0.0`
- algorithm version: `1`
- artifact type: `signal_hypothesis`
- schema: `crt.signal_hypothesis` v1
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

### Ograniczenie endpointu

Stage 1 akceptuje tylko:

- localhost,
- prywatne IP LAN,
- link-local,
- hosty `.local` / `.lan`,
- jednoczłonowe nazwy hostów LAN.

Publiczne endpointy AI są odrzucane. Celem jest uniknięcie przypadkowego wysłania artefaktów poza lokalną infrastrukturę.

## Odpowiedź AI

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

Jeżeli jednostka, skala lub offset nie są uzasadnione, model ma zwrócić `null`.

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

Windows GitHub-hosted. CI **nie łączy się z realnym serwerem AI**. Używa fake local AI i sprawdza:

- Extension API / `ai.use`,
- candidate artifact -> hypothesis,
- zachowanie score i SHA źródeł,
- bounded context bez RAW,
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
4. Model: aktualny model lokalny.
5. Zaznacz `0x321 / Byte0 / Bit2` z testowych wirtualnych logów.
6. Kliknij `Zaproponuj hipotezę AI`.
7. Oczekiwane:
   - operacja kończy się bez blokady GUI,
   - powstaje `signal_hypothesis`,
   - source candidate nadal ma score `1.000` i class `strong`,
   - status `suggested / verified=false`,
   - AI proponuje ostrożną interpretację związaną z EGR lub wskazuje niepewność,
   - next experiment ma charakter weryfikacyjny, nie automatycznie potwierdzający.
8. Następnie wyłącz/zablokuj AI endpoint i ponów:
   - tylko Signal Hypothesis ma pokazać `AI unavailable/error`,
   - Signal Candidates i pozostałe zakładki nadal działają.

## Po Stage 1

Najbliższy etap po ręcznej akceptacji:

- mechanizm operatorowego `verify/reject/edit` dla hipotezy,
- następnie Draft DBC oparty wyłącznie o hipotezy jawnie zweryfikowane przez operatora.
