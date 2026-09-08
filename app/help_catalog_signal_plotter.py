from __future__ import annotations

from . import help_catalog as _help_catalog
from .help_catalog import HelpSection, HelpTopic


SIGNAL_PLOTTER_HELP_TOPIC = HelpTopic(
    id="full-signal-plotter",
    category="Dekodowanie i protokoły",
    title="Full Signal Plotter — pełna seria i kursory A/B",
    summary=(
        "Jak zbudować pełną, niepróbkowaną serię wybranego bitfield z zapisanej sesji, "
        "ustawić dokładne kursory A/B i przejść do odpowiadających ramek RAW."
    ),
    keywords=(
        "signal plotter",
        "full signal plotter",
        "wykres",
        "cursor",
        "kursor A",
        "kursor B",
        "delta time",
        "delta value",
        "bitfield",
        "start bit",
        "intel",
        "motorola",
        "source_row",
        "pełna seria",
        "sampling none",
    ),
    sections=(
        HelpSection(
            "Do czego służy Full Signal Plotter Stage 1",
            paragraphs=(
                "Full Signal Plotter jest pasywnym narzędziem do oglądania jednego arbitralnego pola CAN na osi czasu całej zapisanej sesji. Nie wysyła ramek i nie modyfikuje pliku sesji.",
                "W przeciwieństwie do małego plottera w Signal Discovery, artefakt Full Signal Plotter zapisuje każdy poprawnie odczytany punkt wybranego pola aż do jawnego limitu bezpieczeństwa Stage 1. Nie stosuje cichego próbkowania danych źródłowych.",
            ),
        ),
        HelpSection(
            "Jak zbudować serię",
            steps=(
                "Otwórz zapisaną sesję w projekcie CRT i przejdź do zakładki `Signal Plotter`.",
                "Wybierz kanał, CAN ID, format STD/EXT i rodzaj ramki.",
                "Ustaw start bit, długość 1–64, Intel/Motorola, signed/unsigned, scale i offset.",
                "Pozostaw lub świadomie zmień limit bezpieczeństwa liczby punktów.",
                "Kliknij `Zbuduj pełną serię`.",
            ),
            note=(
                "Jeżeli liczba punktów przekroczy limit bezpieczeństwa, Stage 1 przerywa analizę i nie zapisuje częściowego artefaktu. Zwiększenie limitu jest świadomą decyzją operatora."
            ),
        ),
        HelpSection(
            "Pełne dane a redukcja renderingu",
            paragraphs=(
                "Artefakt `signal_plot_series` ma kontrakt `complete=true` i `sampling=none`. Każdy punkt zawiera dokładny timestamp, raw value, wartość po scale/offset oraz source_row.",
                "Dla wydajności QPainter może rysować deterministycznie zredukowaną polilinię z zachowaniem skrajnych wartości koszyków. Ta redukcja nie zmienia artefaktu i nie jest używana do wyboru kursora.",
            ),
            warning=(
                "Kursor zawsze jest ustawiany na najbliższym rzeczywistym punkcie pełnej serii, nie na punkcie powstałym wyłącznie do renderingu."
            ),
        ),
        HelpSection(
            "Kursory A/B",
            steps=(
                "Wybierz aktywny kursor A albo B.",
                "Kliknij na wykresie; CRT znajdzie najbliższy rzeczywisty timestamp w pełnej serii.",
                "Odczytaj timestamp, value, raw i dokładny source_row kursora.",
                "Gdy oba kursory są ustawione, CRT pokazuje Δt(B-A) oraz Δvalue(B-A).",
                "Użyj `Otwórz A w RAW` lub `Otwórz B w RAW`, aby przejść do dokładnej ramki źródłowej.",
            ),
        ),
        HelpSection(
            "Granice Stage 1",
            bullets=(
                "jeden dokładny klucz CAN i jeden bitfield na pojedynczym wykresie",
                "brak zoom/pan i wielokanałowych tracków w Stage 1",
                "brak automatycznej interpretacji znaczenia fizycznego pola",
                "brak AI i brak zależności od lokalnego AI",
                "brak CAN TX i aktywnych procedur diagnostycznych",
            ),
            note=(
                "Kolejne etapy mogą dodać zoom/pan, wiele tracków, nakładanie markerów i porównanie sygnałów bez zmiany kontraktu source_row."
            ),
        ),
    ),
    related=("signal-discovery", "stored-sessions", "source-of-truth", "artifacts"),
)


if not any(topic.id == SIGNAL_PLOTTER_HELP_TOPIC.id for topic in _help_catalog.HELP_TOPICS):
    _help_catalog.HELP_TOPICS = (*_help_catalog.HELP_TOPICS, SIGNAL_PLOTTER_HELP_TOPIC)
    _help_catalog._TOPIC_BY_ID[SIGNAL_PLOTTER_HELP_TOPIC.id] = SIGNAL_PLOTTER_HELP_TOPIC


__all__ = ["SIGNAL_PLOTTER_HELP_TOPIC"]
