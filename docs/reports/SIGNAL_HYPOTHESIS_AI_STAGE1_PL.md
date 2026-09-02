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

Realny test Qwen3.6 pokazał, że model zakotwiczył się na etykiecie `TEST_EGR` i zaczął dopowiadać semantykę EGR, której evidence nie potwierdzało. Dlatego Signal Hypothesis ma politykę label-redacted:

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
- `max_tokens = 1536`,
- `temperature = 0`,
- `stream = false`,
- `response_format = json_object`.

Realny pomiar `qwen3.6:35b-hermes64k` pokazał prosty request JSON w ok. 22,9 s. Wcześniejszy pełny request przekraczał 120 s; po wyłączeniu extended reasoning problem timeoutu został usunięty. Limit 768 tokenów okazał się zbyt mały dla pełnego JSON i został zwiększony do 1536. Jeżeli endpoint mimo to kończy odpowiedź z `finish_reason=length`, CRT zgłasza jawny błąd „response truncated”, zamiast traktować ucięty JSON jak prawidłową hipotezę.

### Ograniczenie endpointu

Stage 1 akceptuje tylko:

- localhost,
- prywatne IP LAN,
- link-local,
- hosty `.local` / `.lan`,
- jednoczłonowe nazwy hostów LAN.

Publiczne endpointy AI są odrzucane.

## Odpowiedź AI — kontrakt v2

Wymagane pola odpowiedzi:

- `name`,
- `physical_meaning`,
- `rationale`,
- `next_experiments`,
- `warnings`.

Opcjonalne:

- `unit`,
- `scale`,
- `offset`,
- `confidence`.

Pusty JSON lub semantycznie pusta odpowiedź są odrzucane przed `artifact.write`.

Bezpieczna naprawa braków nie tworzących nowej semantyki:

- brak `unit` -> `null`,
- brak `scale` -> `null`,
- brak `offset` -> `null`,
- brak `confidence` przy istniejącej treściwej hipotezie -> `0.0` oraz jawny warning.

Nie są automatycznie uzupełniane brakujące `name`, `physical_meaning`, `rationale`, `next_experiments` ani `warnings` przed guardrailami. Jeśli semantyczny rdzeń jest niekompletny, wynik jest odrzucany.

Przy odrzuceniu komunikat zawiera bounded `response_excerpt`. Poprawny artefakt zapisuje `response_sha256`, `response_contract_version=2` i `response_language=pl-PL`. Pełna surowa odpowiedź modelu nie jest zapisywana.

## Deterministyczne guardraile epistemiczne

### Brak operator_context

Jeżeli operator nie poda kontekstu semantycznego, zapis jest neutralizowany do:

- `name = unknown_bit_state_candidate`,
- nieznanego stanu binarnego skorelowanego z target/control,
- `confidence = 0.0`,
- deterministic rationale z Target/Control/direction/timing,
- neutralnych testów przejścia odwrotnego i kontroli,
- bez domenowych twierdzeń modelu.

### Niepusty operator_context

Kontekst operatora jest traktowany wyłącznie jako wskazówka domenowa, nie dowód semantyki bitu. Przed zapisem CRT deterministycznie wymusza:

- `name = operator_context_correlated_candidate`,
- opis „kandydat może być związany z obszarem wskazanym przez operatora”,
- brak przypisania funkcji bitu i znaczenia stanów 0/1,
- brak roli command/feedback, aktuatora, progu, stanu domyślnego, jednostki, scale i offset,
- confidence maksymalnie `0.35`,
- rationale z deterministycznego evidence CRT,
- stałe ostrzeżenia o różnicy między korelacją i potwierdzoną semantyką.

Realny test pokazał także, że Qwen potrafił pomylić `B0.2` z „bitem 4” i zaproponować nieuzasadnione manipulacje fizyczne. Dlatego `next_experiments` przy `operator_context` nie są już bezpośrednio zapisywane z odpowiedzi modelu. CRT generuje je deterministycznie dla **dokładnego CAN ID / Byte / Bit** oraz obserwowanego direction/timing:

1. powtórzenie tego samego eksperymentu operatora i sprawdzenie tej samej zmiany,
2. bezpieczne odwrócenie bodźca i sprawdzenie przejścia odwrotnego,
3. niezależny test kontrolny bez bodźca operatora.

Dzięki temu model nie może zapisać testu dla złego bitu ani dopisać nieuzasadnionego działania fizycznego.

## Status hipotezy

Każdy artefakt Stage 1 zapisuje:

- `status = suggested`,
- `verified = false`,
- `ai_generated = true`.

Nie ma automatycznego potwierdzania ani automatycznej promocji do DBC.

## Awaria AI

Błąd połączenia, timeout, ucięta odpowiedź, niepoprawny JSON albo anulowanie:

- kończy tylko operację Signal Hypothesis,
- nie modyfikuje Candidate Engine,
- nie modyfikuje źródłowych sesji,
- nie blokuje GUI CRT,
- nie blokuje Signal Discovery / Experiment Diff / Candidate Engine / evidence / eksportów.

GUI wykonuje AI w `QThreadPool`.

## GUI Stage 1

Karta `Signal Hypothesis` umożliwia:

- konfigurację Local AI URL,
- model,
- timeout,
- wybór artefaktu Signal Candidates,
- tabelę kandydatów,
- opcjonalny kontekst operatora,
- uruchomienie/anulowanie AI,
- podgląd zapisanej suggested hypothesis.

Samo otwarcie karty nie tworzy klienta sieciowego i nie wykonuje requestu.

## CI

Dedykowany workflow `Signal Hypothesis AI Stage 1 Validation` działa na `windows-latest`. Legacy Ubuntu workflow nie uruchamia się automatycznie.

CI nie łączy się z realnym serwerem AI i sprawdza m.in.:

- Extension API / `ai.use`,
- candidate artifact -> hypothesis,
- zachowanie score i SHA źródeł,
- bounded context bez RAW,
- label redaction,
- polski response contract,
- response truncation,
- brakujące pola opcjonalne,
- odrzucenie `{}`,
- brak kontekstu -> neutralny guardrail,
- operator_context -> domain-hint-only guardrail,
- agresywną halucynację `1=otwarcie` / `command` / confidence 0.9,
- błędny „bit 4” i nieuzasadnione testy fizyczne -> deterministyczne eksperymenty dla dokładnego kandydata,
- production GUI smoke,
- Help Center.

## Manual acceptance

Testowy kandydat: `0x321 / Byte 0 / Bit 2`, score `1.000`, class `strong`, Target `6/6`, Control `0/4`, direction `0->1`, średnie opóźnienie około `70 ms`.

Zweryfikowano już na realnym lokalnym `qwen3.6:35b-hermes64k`:

- endpoint działa,
- reasoning off usuwa wcześniejszy problem >120 s,
- polski output działa,
- bez kontekstu operatora zapis jest neutralny i nie wymyśla EGR,
- z kontekstem EGR zapis nie przypisuje już otwarcia/zamknięcia ani funkcji bitu,
- wykryty podczas realnego testu problem złego „bitu 4” w `next_experiments` został usunięty deterministycznym guardrailem v2 i oczekuje końcowego ponownego testu na Ollamie.

## Po Stage 1

Po końcowej ręcznej akceptacji:

- mechanizm operatorowego `verify/reject/edit` dla hipotezy,
- następnie Draft DBC oparty wyłącznie o hipotezy jawnie zweryfikowane przez operatora.
