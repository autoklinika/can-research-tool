from __future__ import annotations

from . import help_catalog as _help_catalog
from .help_catalog import HelpSection, HelpTopic


SIGNAL_CANDIDATES_HELP_TOPIC = HelpTopic(
    id="signal-candidate-engine",
    category="Analiza i porównania",
    title="Signal Candidate Engine — ranking kandydatów sygnałów",
    summary=(
        "Jak CRT scala deterministyczne wyniki Experiment Diff z opcjonalną walidacją "
        "Signal Discovery i buduje audytowalny ranking strong/medium/weak."
    ),
    keywords=(
        "signal candidate",
        "candidate engine",
        "kandydat sygnału",
        "strong",
        "medium",
        "weak",
        "experiment diff",
        "signal discovery",
        "artifact",
        "source_row",
        "evidence",
        "ranking",
        "AI",
    ),
    sections=(
        HelpSection(
            "Do czego służy Candidate Engine",
            paragraphs=(
                "Signal Candidate Engine Stage 1 jest kolejnym etapem po Signal Discovery i Experiment Diff. Nie szuka zmian bezpośrednio w surowym logu. Scala już zapisane, wersjonowane artefakty dowodowe i deduplikuje ten sam candidate_key między eksperymentami.",
                "Wynikiem jest trwały artefakt signal_candidates zawierający ranking, klasę siły, źródła rankingu, walidację aktywności i exact evidence prowadzące do ramek źródłowych.",
            ),
        ),
        HelpSection(
            "Jakie dane są wejściem",
            bullets=(
                "Experiment Diff jest wymagany. CRT wybiera najnowszy artefakt dla każdej unikalnej konfiguracji target/control i okna czasu, aby ponowne uruchomienie tego samego eksperymentu nie zawyżało rankingu.",
                "Signal Discovery jest opcjonalnym enrichment. CRT wybiera najnowszy pasujący artefakt dla sesji i klucza CAN występującego w kandydatach Experiment Diff.",
                "Candidate Engine korzysta z read-only artifact.read z kontrolą integralności SHA-256 i nie skanuje ponownie RAW CAN.",
            ),
        ),
        HelpSection(
            "Score i klasy strong / medium / weak",
            paragraphs=(
                "candidate_score w Stage 1 jest najlepszym jawnym, deterministycznym score pochodzącym z Experiment Diff. Signal Discovery nie jest ukrytą wagą i brak jego artefaktu nie obniża score.",
                "Klasa strong wymaga score co najmniej 0.75, co najmniej trzech zmian target, zgodności kierunku co najmniej 80%, control change ratio nie większego niż 25% oraz braku sprzecznego dowodu aktywności. Medium wymaga score co najmniej 0.40 i co najmniej dwóch zmian target. Pozostałe wyniki są weak.",
            ),
        ),
        HelpSection(
            "Walidacja Signal Discovery",
            paragraphs=(
                "Jeżeli istnieje pasujący artefakt Signal Discovery, Candidate Engine sprawdza czy wskazany bit był rzeczywiście zmienny w pełnej sesji oraz pokazuje pokrycie sesji, liczbę przejść i transition rate.",
                "Status unavailable oznacza tylko brak pasującego artefaktu Signal Discovery. Nie jest to negatywny dowód i nie zmniejsza candidate_score.",
            ),
        ),
        HelpSection(
            "Exact evidence",
            paragraphs=(
                "Candidate Engine zachowuje evidence odziedziczone z Experiment Diff wraz z identyfikatorem artefaktu eksperymentu. Każdy dowód nadal wskazuje session_id oraz dokładny source_row stanu przed i po markerze.",
                "Przyciski Otwórz stan PRZED i Otwórz stan PO nie wyszukują podobnej ramki. Nawigują do dokładnie wskazanego source_row w niezmienionej sesji źródłowej.",
            ),
        ),
        HelpSection(
            "AI i Signal Hypothesis",
            paragraphs=(
                "AI nie uczestniczy w Candidate Engine Stage 1 i pole ai_used w kontrakcie rankingu ma wartość false.",
                "Pierwszy planowany punkt integracji lokalnego AI to Signal Hypothesis Stage 1. AI otrzyma gotowy artefakt signal_candidates, statystyki i wybrane exact evidence i będzie mogło proponować nazwę sygnału, jednostkę, skalę oraz następny eksperyment. Niedostępność AI nie może blokować Candidate Engine ani normalnej pracy CRT.",
            ),
        ),
        HelpSection(
            "Czego Stage 1 jeszcze nie robi",
            bullets=(
                "nie nadaje kandydatowi znaczenia fizycznego",
                "nie tworzy jeszcze Signal Hypothesis",
                "nie tworzy jeszcze Draft DBC",
                "nie wykonuje korelacji pól wielobitowych jako osobnych kandydatów",
                "nie używa AI do rankingu",
                "nie generuje żadnej transmisji CAN ani aktywnego UDS/J1939",
            ),
        ),
    ),
    related=(
        "signal-discovery",
        "experiment-diff-marker-correlation",
        "source-of-truth",
        "artifacts",
    ),
)


if not any(topic.id == SIGNAL_CANDIDATES_HELP_TOPIC.id for topic in _help_catalog.HELP_TOPICS):
    _help_catalog.HELP_TOPICS = (*_help_catalog.HELP_TOPICS, SIGNAL_CANDIDATES_HELP_TOPIC)
    _help_catalog._TOPIC_BY_ID[SIGNAL_CANDIDATES_HELP_TOPIC.id] = SIGNAL_CANDIDATES_HELP_TOPIC


__all__ = ["SIGNAL_CANDIDATES_HELP_TOPIC"]
