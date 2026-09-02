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
        "semantic guardrail",
        "operator context",
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
            "Brak kontekstu operatora — twardy guardrail semantyczny",
            paragraphs=(
                "Jeżeli pole Kontekst operatora jest puste, CRT uznaje, że ma wyłącznie dowód strukturalny i korelacyjny, ale nie ma świadomego źródła semantyki fizycznej. Model nie może wtedy wiarygodnie przypisać funkcji typu EGR, wentylator, przekaźnik, temperatura czy ciśnienie.",
                "Jeżeli model mimo to zwróci domenową interpretację, CRT przed zapisaniem artefaktu zastępuje ją neutralną hipotezą unknown_bit_state_candidate. physical_meaning opisuje wtedy tylko nieznany stan binarny skorelowany z target/control, confidence jest 0.0, a rationale jest budowane wyłącznie z deterministycznych liczb kandydata, np. Target/Control, kierunku i timingu.",
                "W trybie bez kontekstu operatora następne eksperymenty są neutralne i służą wyłącznie rozstrzyganiu korelacji, np. sprawdzeniu przejścia odwrotnego i niezależnej kontroli. CRT nie zachowuje domenowych sugestii modelu, których evidence nie wspiera.",
            ),
        ),
        HelpSection(
            "Kontekst operatora — domena, nie semantyka bitu",
            paragraphs=(
                "Niepusty Kontekst operatora może wskazać obszar eksperymentu, np. EGR, ale nadal nie jest dowodem funkcji bitu. CRT przed artifact.write deterministycznie zastępuje zbyt szczegółowe twierdzenia modelu bezpiecznym opisem: kandydat może być związany z obszarem wskazanym przez operatora, lecz dane nie określają funkcji bitu ani znaczenia stanów 0 i 1.",
                "CRT nie zapisuje na podstawie samego kontekstu operatora twierdzeń typu 1=otwarcie, 0=zamknięcie, command/feedback, nazwy konkretnego aktuatora, progu, stanu domyślnego ani jednostki/scale/offset. AI confidence jest w tym trybie ograniczone do maksymalnie 0.35.",
                "Także następne eksperymenty są budowane przez CRT deterministycznie dla dokładnego CAN ID / Byte / Bit i obserwowanego kierunku. Dzięki temu model nie może pomylić np. B0.2 z innym bitem ani dopisać nieuzasadnionych manipulacji fizycznych. Eksperymenty dotyczą powtórzenia bodźca operatora, przejścia odwrotnego i niezależnej kontroli.",
            ),
        ),
        HelpSection(
            "Konfiguracja lokalnego AI",
            paragraphs=(
                "Stage 1 korzysta z lokalnego endpointu zgodnego z OpenAI Chat Completions, np. Ollama /v1. W karcie Signal Hypothesis podaje się Local AI URL, model i timeout.",
                "Adapter Stage 1 akceptuje localhost, prywatne adresy LAN oraz lokalne hosty .local/.lan. Publiczne endpointy AI są odrzucane, aby przypadkowo nie wysłać danych poza lokalną infrastrukturę.",
                "Dla krótkiego audytowalnego structured output adapter domyślnie używa reasoning_effort=none, max_tokens=1536, temperature=0 oraz response_format=json_object.",
                "Ustawienia URL/model/timeout są zapisywane lokalnie przez QSettings. Można też użyć CRT_AI_BASE_URL, CRT_AI_MODEL i CRT_AI_TIMEOUT_S jako wartości początkowych.",
            ),
        ),
        HelpSection(
            "Co AI może zaproponować",
            bullets=(
                "roboczą interpretację przed zastosowaniem deterministycznych guardraili CRT",
                "możliwy obszar znaczenia fizycznego wyłącznie na podstawie jawnego kontekstu operatora; końcowy zapis nie może wykraczać poza poziom wspierany przez evidence",
                "jednostkę, scale i offset tylko gdy dane to uzasadniają; przy operator_context Stage 1 guardrail zeruje te pola do null, dopóki nie ma osobnego evidence",
                "confidence AI od 0 do 1 jako surową ocenę modelu; zapisany wynik może zostać deterministycznie obniżony przez CRT",
                "krótkie uzasadnienie oparte o przekazane evidence; zapisane rationale może zostać zastąpione deterministycznym rationale CRT",
                "pomysły na weryfikację; zapisane next_experiments są jednak generowane przez CRT dla dokładnego kandydata, aby nie dopuścić błędnego bitu ani nieuzasadnionych działań",
                "pola opisowe physical_meaning, rationale, next_experiments i warnings są wymagane po polsku (pl-PL); techniczny identyfikator name i symbol jednostki mogą pozostać językowo neutralne",
            ),
        ),
        HelpSection(
            "Walidacja odpowiedzi AI — kontrakt v2",
            paragraphs=(
                "Poprawny JSON nie wystarcza. CRT waliduje semantyczny kontrakt odpowiedzi przed zapisaniem artefaktu. Pusta nazwa, puste physical_meaning lub rationale, niepoprawny confidence, brak eksperymentu weryfikacyjnego albo brak ostrzeżenia powodują odrzucenie odpowiedzi.",
                "Jeżeli model pominie wyłącznie semantycznie opcjonalne unit, scale lub offset, CRT uzupełnia je jako null. Jeżeli treściwa hipoteza pominie tylko AI confidence, CRT nie wymyśla pewności: zapisuje 0.0 i dopisuje jawne ostrzeżenie o tym fallbacku. Pusty lub semantycznie niekompletny JSON nadal jest odrzucany.",
                "Jeżeli model zwróci element next_experiments lub warnings jako prosty obiekt tekstowy, np. name + description, CRT może bezpiecznie spłaszczyć istniejące pola tekstowe do jednego stringa przed zastosowaniem guardraili. Nie są przy tym dopisywane nowe fakty ani znaczenie fizyczne.",
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
