from __future__ import annotations

from . import help_catalog as _help_catalog
from .help_catalog import HelpSection, HelpTopic


SIGNAL_HYPOTHESIS_REVIEW_HELP_TOPIC = HelpTopic(
    id="signal-hypothesis-review",
    category="Analiza i porównania",
    title="Signal Hypothesis Review — decyzja operatora",
    summary=(
        "Jak potwierdzić, odrzucić lub edytować hipotezę AI bez modyfikowania jej "
        "oryginalnego artefaktu i z pełną historią append-only."
    ),
    keywords=(
        "signal hypothesis review",
        "verify",
        "verified",
        "reject",
        "rejected",
        "edit",
        "edited",
        "operator",
        "append-only",
        "Draft DBC",
        "audyt",
    ),
    sections=(
        HelpSection(
            "Po co jest Review",
            paragraphs=(
                "Signal Hypothesis generuje sugestię AI ze statusem suggested / verified=false. Stage 2 nie zmienia tego artefaktu. Decyzja człowieka jest zapisywana osobno jako signal_hypothesis_review.",
                "Każda kolejna decyzja tworzy nowy artefakt. Najnowszy review jest aktualnym stanem operatorskim, a wcześniejsze decyzje pozostają historią audytową.",
            ),
        ),
        HelpSection(
            "Potwierdź",
            paragraphs=(
                "Potwierdź tworzy review ze statusem verified. Potwierdzana jest treść aktualnie widoczna w edytorze operatora, dlatego można najpierw zapisać edycję, a następnie potwierdzić poprawioną wersję.",
                "Potwierdzenie nie ustawia verified=true w źródłowym artefakcie AI. Autorytatywna decyzja znajduje się wyłącznie w review.",
            ),
        ),
        HelpSection(
            "Odrzuć",
            paragraphs=(
                "Odrzuć tworzy review ze statusem rejected i wymaga krótkiego powodu w polu Notatka decyzji.",
                "Odrzucenie nie kasuje wcześniejszych edycji ani potwierdzeń. Jest kolejnym wpisem append-only i staje się aktualną decyzją dlatego, że jest najnowsze.",
            ),
        ),
        HelpSection(
            "Zapisz edycję",
            paragraphs=(
                "Zapisz edycję tworzy review ze statusem edited / verified=false. Operacja wymaga faktycznej zmiany co najmniej jednego pola.",
                "Stage 2 pozwala zmienić name, physical_meaning, unit, scale, offset i rationale. next_experiments oraz warnings pozostają historycznym kontekstem źródłowej hipotezy.",
            ),
        ),
        HelpSection(
            "Niezmienność źródła",
            bullets=(
                "źródłowy signal_hypothesis pozostaje byte-for-byte niezmienny",
                "review zapisuje ID i SHA źródłowej hipotezy",
                "decyzja operatora nie uruchamia AI",
                "review nie ma session.read i nie czyta RAW CAN",
                "review nie ma can.tx i nie może generować transmisji CAN",
            ),
        ),
        HelpSection(
            "Relacja z Draft DBC",
            paragraphs=(
                "Przyszły Draft DBC powinien korzystać wyłącznie z najnowszego signal_hypothesis_review o statusie verified. Sama sugestia AI ani review edited nie są wystarczającym potwierdzeniem semantyki sygnału.",
            ),
        ),
    ),
    related=(
        "signal-hypothesis-ai",
        "signal-candidate-engine",
        "experiment-diff-marker-correlation",
        "source-of-truth",
        "artifacts",
    ),
)


if not any(topic.id == SIGNAL_HYPOTHESIS_REVIEW_HELP_TOPIC.id for topic in _help_catalog.HELP_TOPICS):
    _help_catalog.HELP_TOPICS = (*_help_catalog.HELP_TOPICS, SIGNAL_HYPOTHESIS_REVIEW_HELP_TOPIC)
    _help_catalog._TOPIC_BY_ID[SIGNAL_HYPOTHESIS_REVIEW_HELP_TOPIC.id] = SIGNAL_HYPOTHESIS_REVIEW_HELP_TOPIC


__all__ = ["SIGNAL_HYPOTHESIS_REVIEW_HELP_TOPIC"]
