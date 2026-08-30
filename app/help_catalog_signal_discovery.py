from __future__ import annotations

from .help_catalog import HelpSection, HelpTopic


SIGNAL_DISCOVERY_HELP_TOPIC = HelpTopic(
    id="signal-discovery",
    category="Dekodowanie i protokoły",
    title="Signal Discovery — aktywność bitów i ręczny bitfield",
    summary=(
        "Jak znaleźć zmienne bity i bajty jednego CAN ID, ręcznie interpretować dowolny "
        "bitfield i przechodzić z wyniku do dokładnej ramki źródłowej."
    ),
    keywords=(
        "signal discovery",
        "byte activity",
        "bit activity",
        "bitfield",
        "start bit",
        "intel",
        "motorola",
        "little endian",
        "big endian",
        "signed",
        "scale",
        "offset",
        "source_row",
        "reverse engineering",
        "CAN ID",
    ),
    sections=(
        HelpSection(
            "Do czego służy Stage 1",
            paragraphs=(
                "Signal Discovery Stage 1 jest pasywnym warsztatem do ręcznego odkrywania znaczenia pól w nieznanej wiadomości CAN. Pracuje na zapisanej sesji i nie generuje transmisji CAN.",
                "Analiza dotyczy jednego dokładnego klucza wiadomości: kanału, CAN ID, formatu STD/EXT oraz rodzaju ramki data/RTR/error.",
            ),
            bullets=(
                "Byte / Bit Activity Map pokazuje, które pozycje są stałe, zmienne lub nieobecne przy zmiennym DLC.",
                "Dla każdego bajtu zapisywane są minimum, maksimum, liczba wartości, częstotliwość zmian i dokładne source_row dowodów MIN/MAX.",
                "Dla każdego bitu liczone są stany 0/1 oraz przejścia tylko między ciągłymi obserwacjami tego bajtu.",
            ),
        ),
        HelpSection(
            "Jak uruchomić analizę",
            steps=(
                "Otwórz zapisaną sesję w projekcie CRT.",
                "Przejdź do zakładki `Signal Discovery`.",
                "Wybierz kanał, wpisz CAN ID w zapisie szesnastkowym i wybierz STD 11-bit albo EXT 29-bit.",
                "Wybierz typ ramki i użyj `Analizuj aktywność`.",
                "Przejrzyj mapę bajtów i bitów. Przy wybranym bajcie możesz otworzyć dokładną ramkę MIN lub MAX.",
            ),
            note=(
                "Statystyki aktywności są liczone na wszystkich pasujących ramkach w całej sesji. "
                "Nie są liczone wyłącznie z punktów widocznych na wykresie."
            ),
        ),
        HelpSection(
            "Arbitrary Bitfield Inspector / Plotter",
            paragraphs=(
                "Inspektor pozwala wybrać dowolny start bit i długość 1–64 bitów bez wcześniejszego tworzenia DBC. Możesz przełączać Intel/little endian oraz Motorola/big endian zgodne z numeracją CANdb++/DBC, a także signed/unsigned, scale i offset.",
                "Wykres jest warstwą interpretacji. Zmiana start bit, endian, signed, scale lub offset nie modyfikuje surowych ramek ani zapisanego artefaktu aktywności.",
            ),
            bullets=(
                "Intel: start bit jest najmłodszym bitem pola, a kolejne pozycje rosną liniowo.",
                "Motorola: start bit jest najstarszym bitem pola i używa reguły saw-tooth CANdb++/DBC.",
                "Kliknięcie punktu wykresu wybiera dowód z zachowanym dokładnym source_row.",
            ),
        ),
        HelpSection(
            "Pełna statystyka a próbka wykresu",
            paragraphs=(
                "Aby GUI pozostawało responsywne również przy bardzo dużych logach, artefakt przechowuje deterministyczną, równomierną próbkę do 5000 pasujących ramek dla wykresu. Pierwszy i ostatni obszar sesji pozostają reprezentowane przez dobór według indeksu wystąpienia.",
                "Ograniczenie próbki dotyczy tylko wykresu. Liczniki aktywności bajtów i bitów, minimum, maksimum i liczba pasujących ramek powstają z pełnego przebiegu sesji.",
            ),
            warning=(
                "Na podstawie samego wykresu nie zakładaj znaczenia fizycznego sygnału. Stage 1 pomaga "
                "zobaczyć kandydatów i ręcznie testować interpretacje; automatyczny Signal Candidate Engine "
                "i korelacja eksperymentów należą do kolejnych etapów."
            ),
        ),
        HelpSection(
            "Dowody i źródło prawdy",
            paragraphs=(
                "Przyciski MIN/MAX i punkty wykresu prowadzą przez istniejący bounded navigator CRT do dokładnego source_row w surowej zapisanej sesji. Nie jest wykonywane ponowne wyszukiwanie CAN ID w celu zgadnięcia ramki.",
                "Wynik analizy jest zapisywany jako wersjonowany artefakt `signal_discovery_activity` z fingerprintem źródłowej sesji i parametrami dokładnego klucza wiadomości.",
            ),
            note="Surowa sesja pozostaje niezmiennym źródłem prawdy. Signal Discovery tylko ją odczytuje i zapisuje osobny artefakt analizy.",
        ),
        HelpSection(
            "Czego Stage 1 jeszcze nie robi",
            bullets=(
                "nie nadaje automatycznie nazw ani jednostek znalezionym polom",
                "nie tworzy jeszcze Signal Hypothesis ani Draft DBC",
                "nie wykonuje automatycznej korelacji z markerami lub eksperymentami A/B",
                "nie klasyfikuje jeszcze pól jako counter/checksum/CRC candidate",
                "nie uruchamia aktywnego skanowania UDS, J1939 ani żadnego TX",
            ),
        ),
    ),
    related=("stored-sessions", "dbc", "source-of-truth", "artifacts"),
)


__all__ = ["SIGNAL_DISCOVERY_HELP_TOPIC"]
