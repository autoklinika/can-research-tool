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
                "deterministyczny candidate_score, klasa i najlepsze wsparcie Experiment Diff",
                "opcjonalna walidacja Signal Discovery",
                "ograniczona liczba exact evidence z source_row i payloadem tylko dla wybranego kandydata",
                "opcjonalny krótki kontekst operatora wpisany w GUI",
                "RAW CAN ani pełna sesja nie są przekazywane do AI",
            ),
        ),
        HelpSection(
            "Konfiguracja lokalnego AI",
            paragraphs=(
                "Stage 1 korzysta z lokalnego endpointu zgodnego z OpenAI Chat Completions, np. Ollama /v1. W karcie Signal Hypothesis podaje się Local AI URL, model i timeout.",
                "Adapter Stage 1 akceptuje localhost, prywatne adresy LAN oraz lokalne hosty .local/.lan. Publiczne endpointy AI są odrzucane, aby przypadkowo nie wysłać danych poza lokalną infrastrukturę.",
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
