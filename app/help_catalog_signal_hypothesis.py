from __future__ import annotations

from . import help_catalog as _help_catalog
from .help_catalog import HelpSection, HelpTopic


SIGNAL_HYPOTHESIS_HELP_TOPIC = HelpTopic(
    id="signal-hypothesis-ai",
    category="Analiza i porównania",
    title="Signal Hypothesis — lokalne AI i hipotezy sygnałów",
    summary=(
        "Jak CRT używa opcjonalnego lokalnego AI do interpretacji gotowych Signal Candidates "
        "bez zmiany deterministycznego rankingu i bez dostępu do RAW CAN."
    ),
    keywords=(
        "signal hypothesis",
        "AI",
        "local AI",
        "Ollama",
        "Qwen",
        "signal candidates",
        "hipoteza",
        "suggested",
        "verified",
        "scale",
        "offset",
        "DBC",
        "response contract",
        "schema v2",
        "label redaction",
        "anti bias",
        "pl-PL",
        "polski",
    ),
    sections=(
        HelpSection(
            "Rola Signal Hypothesis",
            paragraphs=(
                "Signal Hypothesis Stage 1 zaczyna się dopiero po deterministycznym Signal Candidate Engine. AI nie szuka kandydatów w surowym CAN i nie może zmienić score, klasy strong/medium/weak, Target/Control ani exact evidence.",
                "Wynikiem jest osobny trwały artefakt signal_hypothesis. Każda nowa hipoteza ma status suggested, verified=false i ai_generated=true. Nie jest automatycznie traktowana jako potwierdzony sygnał.",
            ),
        ),
        HelpSection(
            "Co trafia do lokalnego AI",
            bullets=(
                "identyfikator kandydata: CAN ID, kanał, STD/EXT, Byte i Bit",
                "deterministyczny candidate_score, klasa i numeryczne wsparcie Experiment Diff",
                "opcjonalna zagregowana walidacja Signal Discovery bez nazw sesji i artefaktów źródłowych",
                "ograniczona liczba exact evidence z source_row i payloadem tylko dla wybranego kandydata",
                "nazwy markerów, etykiety eksperymentu, notatki i nazwy sesji są redagowane przed requestem, aby nie kotwiczyć modelu na semantyce typu TEST_EGR",
                "opcjonalny krótki kontekst operatora wpisany w GUI jest jedynym świadomym kanałem przekazania semantycznej wskazówki",
                "RAW CAN ani pełna sesja nie są przekazywane do AI",
            ),
        ),
        HelpSection(
            "Konfiguracja lokalnego AI",
            paragraphs=(
                "Stage 1 korzysta z lokalnego endpointu zgodnego z OpenAI Chat Completions, np. Ollama /v1. W karcie Signal Hypothesis podaje się Local AI URL, model i timeout.",
                "Adapter Stage 1 akceptuje localhost, prywatne adresy LAN oraz lokalne hosty .local/.lan. Publiczne endpointy AI są odrzucane, aby przypadkowo nie wysłać danych poza lokalną infrastrukturę.",
                "Dla krótkiego audytowalnego structured output adapter domyślnie używa reasoning_effort=none, max_tokens=768, temperature=0 oraz response_format=json_object.",
                "Ustawienia URL/model/timeout są zapisywane lokalnie przez QSettings. Można też użyć CRT_AI_BASE_URL, CRT_AI_MODEL i CRT_AI_TIMEOUT_S jako wartości początkowych.",
            ),
        ),
        HelpSection(
            "Co AI może zaproponować",
            bullets=(
                "roboczą nazwę sygnału",
                "możliwe znaczenie fizyczne",
                "jednostkę, scale i offset tylko gdy dane to uzasadniają",
                "confidence AI od 0 do 1 — jest to pewność modelu, a nie deterministyczny score CRT",
                "krótkie uzasadnienie oparte o przekazane evidence",
                "następne eksperymenty potrzebne do potwierdzenia lub odrzucenia hipotezy",
                "ostrzeżenia i alternatywne interpretacje",
                "pola opisowe physical_meaning, rationale, next_experiments i warnings są wymagane po polsku (pl-PL); techniczny identyfikator name i symbol jednostki mogą pozostać językowo neutralne",
            ),
        ),
        HelpSection(
            "Walidacja odpowiedzi AI — kontrakt v2",
            paragraphs=(
                "Poprawny JSON nie wystarcza. CRT waliduje semantyczny kontrakt odpowiedzi przed zapisaniem artefaktu. Pusta nazwa, puste physical_meaning lub rationale, niepoprawny confidence, brak eksperymentu weryfikacyjnego albo brak ostrzeżenia powodują odrzucenie odpowiedzi.",
                "Jeżeli model pominie wyłącznie semantycznie opcjonalne unit, scale lub offset, CRT uzupełnia je jako null. Jeżeli treściwa hipoteza pominie tylko AI confidence, CRT nie wymyśla pewności: zapisuje 0.0 i dopisuje jawne ostrzeżenie o tym fallbacku. Pusty lub semantycznie niekompletny JSON nadal jest odrzucany.",
                "Jeżeli model nie potrafi ustalić znaczenia fizycznego, ma zwrócić neutralną hipotezę, np. unknown_bit_state_candidate, jasno po polsku opisać niepewność i zaproponować test rozstrzygający. Nie powinien zwracać pustego obiektu {}.",
                "Przy odrzuceniu CRT nie zapisuje nowego signal_hypothesis. Komunikat błędu zawiera bounded pole diagnostyczne response_excerpt — krótki, ograniczony fragment odpowiedzi modelu. Dla poprawnego wyniku artefakt zapisuje response_sha256, response_contract_version=2 i response_language=pl-PL, ale nie pełną surową odpowiedź modelu.",
            ),
            note=(
                "Aktualny artefakt Signal Hypothesis ma schema_version=2. Starsze wyniki schema v1 z wcześniejszego, zbyt łagodnego kontraktu pozostają w projekcie jako historia, ale nie są pokazywane jako aktualne hipotezy."
            ),
        ),
        HelpSection(
            "Awaria lub wyłączenie AI",
            paragraphs=(
                "Niedostępny serwer, timeout albo niepoprawna odpowiedź modelu kończą tylko bieżącą operację Signal Hypothesis komunikatem AI unavailable/error.",
                "Signal Discovery, Experiment Diff, Signal Candidate Engine, exact evidence, projekty i pozostałe funkcje CRT pozostają dostępne. AI nie jest zależnością startową ani source-of-truth.",
                "Anulowanie żądania jest bezpieczne; przy aktywnym połączeniu HTTP operacja kończy się najpóźniej po skonfigurowanym timeout. Wynik po anulowaniu nie jest promowany do źródła prawdy.",
            ),
        ),
        HelpSection(
            "Weryfikacja i Draft DBC",
            paragraphs=(
                "Stage 1 nie ma automatycznego potwierdzania hipotezy. Operator powinien wrócić do Signal Candidates/Experiment Diff, sprawdzić exact evidence i wykonać sugerowane eksperymenty.",
                "Promocja zweryfikowanej hipotezy do Draft DBC jest osobnym kolejnym etapem. Sam fakt, że AI podało nazwę, jednostkę lub skalę, nie wystarcza do utworzenia potwierdzonego sygnału DBC.",
            ),
        ),
    ),
    related=(
        "signal-candidate-engine",
        "experiment-diff-marker-correlation",
        "signal-discovery",
        "source-of-truth",
        "artifacts",
    ),
)


if not any(topic.id == SIGNAL_HYPOTHESIS_HELP_TOPIC.id for topic in _help_catalog.HELP_TOPICS):
    _help_catalog.HELP_TOPICS = (*_help_catalog.HELP_TOPICS, SIGNAL_HYPOTHESIS_HELP_TOPIC)
    _help_catalog._TOPIC_BY_ID[SIGNAL_HYPOTHESIS_HELP_TOPIC.id] = SIGNAL_HYPOTHESIS_HELP_TOPIC


__all__ = ["SIGNAL_HYPOTHESIS_HELP_TOPIC"]
