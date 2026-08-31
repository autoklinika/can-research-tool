from __future__ import annotations

from . import help_catalog as _help_catalog
from .help_catalog import HelpSection, HelpTopic


EXPERIMENT_DIFF_HELP_TOPIC = HelpTopic(
    id="experiment-diff-marker-correlation",
    category="Analiza i porównania",
    title="Experiment Diff — korelacja zmian z markerami",
    summary=(
        "Jak porównywać powtarzane eksperymenty, znaleźć bity zmieniające się po markerze "
        "i przejść z rankingu do dokładnych ramek przed i po zdarzeniu."
    ),
    keywords=(
        "experiment diff",
        "marker correlation",
        "marker",
        "korelacja",
        "target",
        "control",
        "bit",
        "source_row",
        "evidence",
        "delay",
        "EGR",
        "powtarzalność",
    ),
    sections=(
        HelpSection(
            "Do czego służy Experiment Diff",
            paragraphs=(
                "Experiment Diff Stage 1 jest pasywną analizą zestawu co najmniej dwóch zapisanych sesji. Używa markerów operatora jako kotwic czasu i szuka bitów, których stan zmienia się powtarzalnie po wybranym zdarzeniu.",
                "Analiza nie zgaduje jeszcze fizycznego znaczenia sygnału. Tworzy deterministyczny ranking kandydatów oraz zachowuje dokładne dowody źródłowe.",
            ),
        ),
        HelpSection(
            "Marker testowy i kontrolny",
            paragraphs=(
                "Marker testowy określa zdarzenie, z którym szukamy korelacji. Opcjonalny marker kontrolny pozwala sprawdzić, czy ten sam bit zmienia się również w sytuacji kontrolnej.",
                "Tożsamość markera jest oparta przede wszystkim o snapshot preset_id zapisany w chwili eksperymentu. Zmiana późniejszej nazwy presetu nie rozdziela historycznych zdarzeń tego samego typu.",
            ),
            bullets=(
                "Target 7/7 oznacza zmianę w siedmiu z siedmiu eksperymentów, w których bit był obserwowalny przed i po markerze.",
                "Control 0/5 oznacza brak zmiany w pięciu kwalifikujących się zdarzeniach kontrolnych.",
                "Brak ramki lub brak danego bajtu w oknie nie jest liczony jako sztuczny brak korelacji.",
            ),
        ),
        HelpSection(
            "Okno przed i po markerze",
            paragraphs=(
                "Dla każdego zdarzenia CRT zapamiętuje ostatni obserwowany stan danego klucza CAN przed markerem w zadanym oknie pre. Następnie w oknie post szuka pierwszej ramki, w której dany bit różni się od tego stanu.",
                "Delay jest różnicą czasu między timestampem markera a pierwszą zaobserwowaną zmianą bitu. Artefakt przechowuje minimum, maksimum, średnią i medianę opóźnienia dla powtórzeń target.",
            ),
        ),
        HelpSection(
            "Jak czytać ranking",
            paragraphs=(
                "Score jest jawny i deterministyczny. Stage 1 łączy coverage, support, zgodność kierunku 0→1/1→0 oraz specificity względem markerów kontrolnych.",
                "AI nie uczestniczy w wyliczeniu score. W przyszłości może interpretować gotowy artefakt i proponować hipotezy, ale wynik dowodowy pozostaje niezależny od AI.",
            ),
            bullets=(
                "Coverage — w ilu targetach kandydat był faktycznie obserwowalny.",
                "Support — w ilu kwalifikujących targetach bit się zmienił.",
                "Direction consistency — jak często zmiana miała ten sam kierunek.",
                "Control specificity — kara za analogiczne zmiany w kontrolach.",
            ),
        ),
        HelpSection(
            "Exact evidence",
            paragraphs=(
                "Dla każdego zachowanego powtórzenia można otworzyć ramkę stanu PRZED markerem oraz ramkę PO markerze. Dla zmiany target jest to pierwsza ramka, która zmieniła analizowany bit.",
                "Nawigacja używa session_id i dokładnego source_row. CRT nie wyszukuje podobnej ramki ponownie i nie modyfikuje sesji źródłowej.",
            ),
            note=(
                "Brak zmiany w kontroli również jest wynikiem dowodowym: kwalifikujące zdarzenie ma stan przed markerem i obserwację po markerze, na której bit pozostał taki sam."
            ),
        ),
        HelpSection(
            "Czego Stage 1 jeszcze nie robi",
            bullets=(
                "nie testuje automatycznie wszystkich wielobitowych interpretacji Intel/Motorola",
                "nie tworzy jeszcze Signal Hypothesis ani Draft DBC",
                "nie nadaje znaczenia fizycznego kandydatom",
                "nie korzysta jeszcze z lokalnego AI do interpretacji rankingu",
                "nie wykonuje żadnego CAN TX ani aktywnego UDS/J1939 discovery",
            ),
        ),
    ),
    related=("signal-discovery", "source-of-truth", "artifacts"),
)


# Help Center Stage 1 still uses one shared catalog. Register the feature-owned
# topic on import, without changing the base catalog or requiring Experiment Diff
# to be available for normal CRT operation.
if not any(topic.id == EXPERIMENT_DIFF_HELP_TOPIC.id for topic in _help_catalog.HELP_TOPICS):
    _help_catalog.HELP_TOPICS = (*_help_catalog.HELP_TOPICS, EXPERIMENT_DIFF_HELP_TOPIC)
    _help_catalog._TOPIC_BY_ID[EXPERIMENT_DIFF_HELP_TOPIC.id] = EXPERIMENT_DIFF_HELP_TOPIC


__all__ = ["EXPERIMENT_DIFF_HELP_TOPIC"]
