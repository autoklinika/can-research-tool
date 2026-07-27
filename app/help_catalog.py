from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from html import escape


@dataclass(frozen=True, slots=True)
class HelpSection:
    title: str
    paragraphs: tuple[str, ...] = ()
    bullets: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    note: str = ""
    warning: str = ""


@dataclass(frozen=True, slots=True)
class HelpTopic:
    id: str
    category: str
    title: str
    summary: str
    keywords: tuple[str, ...]
    sections: tuple[HelpSection, ...]
    related: tuple[str, ...] = ()


HELP_CATEGORY_ORDER = (
    "Pierwsze kroki",
    "Projekt i organizacja badań",
    "Rejestracja i ramki CAN",
    "Zapisane sesje i wyszukiwanie",
    "Dekodowanie i protokoły",
    "Porównywanie logów",
    "Artefakty i dowody",
    "Bezpieczeństwo i wydajność",
    "Rozwiązywanie problemów",
    "Słownik i skróty",
)


def S(
    title: str,
    *,
    paragraphs: tuple[str, ...] = (),
    bullets: tuple[str, ...] = (),
    steps: tuple[str, ...] = (),
    note: str = "",
    warning: str = "",
) -> HelpSection:
    return HelpSection(
        title=title,
        paragraphs=paragraphs,
        bullets=bullets,
        steps=steps,
        note=note,
        warning=warning,
    )


def T(
    topic_id: str,
    category: str,
    title: str,
    summary: str,
    keywords: tuple[str, ...],
    sections: tuple[HelpSection, ...],
    related: tuple[str, ...] = (),
) -> HelpTopic:
    return HelpTopic(
        id=topic_id,
        category=category,
        title=title,
        summary=summary,
        keywords=keywords,
        sections=sections,
        related=related,
    )


HELP_TOPICS: tuple[HelpTopic, ...] = (
    T(
        "start",
        "Pierwsze kroki",
        "Wprowadzenie do CAN Research Tool",
        "Czym jest CRT, jak zorganizowany jest projekt i od czego rozpocząć pracę.",
        ("start", "wprowadzenie", "CRT", "projekt", "ECU", "workflow"),
        (
            S(
                "Do czego służy CRT",
                paragraphs=(
                    "CAN Research Tool jest projektowym środowiskiem do pasywnego badania komunikacji CAN, organizowania sesji i budowania trwałej wiedzy o jednym badanym ECU.",
                    "Program łączy rejestrację, import logów, filtrowanie, dekodowanie DBC i UDS, wyszukiwanie, porównywanie sesji oraz nawigację od wyniku analizy do dokładnej ramki źródłowej.",
                ),
                bullets=(
                    "jeden projekt CRT opisuje jeden badany ECU lub jeden ściśle określony obiekt badań",
                    "surowe sesje są niezmiennym źródłem prawdy",
                    "analizy tworzą trwałe, wersjonowane artefakty",
                    "wynik analizy powinien prowadzić do konkretnego dowodu w logu",
                ),
            ),
            S(
                "Najkrótsza ścieżka pracy",
                steps=(
                    "Utwórz lub otwórz projekt.",
                    "Zarejestruj sesję Live Capture albo zaimportuj istniejący log.",
                    "Dodaj znaczniki opisujące momenty testu i przypisz sesję do obszaru badań.",
                    "Otwórz zapisaną sesję, użyj wyszukiwania, filtrów i dekoderów.",
                    "Utwórz zestaw porównawczy i uruchom pasywne analizy.",
                    "Z wyniku przejdź do dokładnej ramki lub transakcji źródłowej.",
                ),
            ),
            S(
                "Najważniejsza zasada",
                note="Filtry, widoki i analizy nie powinny zastępować surowego logu. Zmieniają sposób prezentacji lub tworzą nowe artefakty, ale nie usuwają ramek ze źródłowej sesji.",
            ),
        ),
        ("quick-start", "project-model", "source-of-truth"),
    ),
    T(
        "quick-start",
        "Pierwsze kroki",
        "Szybki start — od pustego projektu do pierwszego porównania",
        "Praktyczna procedura uruchomienia pierwszego kompletnego badania.",
        ("quick start", "pierwszy projekt", "pierwsza sesja", "porównanie"),
        (
            S(
                "Przygotowanie projektu",
                steps=(
                    "Wybierz `Plik → Nowy projekt…`.",
                    "Nadaj projektowi nazwę identyfikującą ECU i wariant badania.",
                    "Ustaw domyślną prędkość CAN oraz tryb odbioru zgodny ze stanowiskiem.",
                    "Uzupełnij właściwości projektu i profil ECU, gdy dane są znane.",
                ),
            ),
            S(
                "Pierwsze dwie sesje",
                steps=(
                    "Zarejestruj sesję bazową w kontrolowanych warunkach.",
                    "Dodaj znaczniki przed każdą zmianą stanu, poleceniem diagnostycznym lub ruchem elementu wykonawczego.",
                    "Zapisz sesję z jednoznaczną nazwą i opisem.",
                    "Powtórz test po zmianie badanego warunku i zapisz drugą sesję.",
                ),
            ),
            S(
                "Pierwsze porównanie",
                steps=(
                    "Otwórz `Porównaj` i utwórz trwały zestaw porównawczy.",
                    "Wybierz sesję bazową oraz sesję po zmianie.",
                    "Uruchom komplet analiz.",
                    "Sprawdź dashboard, oś czasu, timing i jitter oraz — dla ruchu diagnostycznego — latencję i transakcje UDS.",
                ),
                warning="Nie interpretuj automatycznie każdej różnicy jako usterki. Najpierw potwierdź warunki testu, znaczniki, czas trwania sesji i kompletność danych.",
            ),
        ),
        ("projects", "live-capture", "comparison-sets"),
    ),
    T(
        "project-model",
        "Pierwsze kroki",
        "Model danych CRT",
        "Relacje między projektem, sesją, obszarem badań, analizą, artefaktem i dowodem.",
        ("model danych", "sesja", "obszar badań", "artefakt", "dowód"),
        (
            S(
                "Hierarchia",
                bullets=(
                    "Projekt — kompletna teczka badawcza jednego ECU.",
                    "Sesja — niezmienny zapis ramek, markerów i metadanych jednego przebiegu.",
                    "Obszar badań — tematyczna grupa sesji, np. EGR, VGT, SCR lub rozruch.",
                    "Zestaw porównawczy — trwały wybór sesji z określoną sesją bazową.",
                    "Analysis run — wersjonowane wykonanie konkretnego algorytmu.",
                    "Artefakt — zapisany wynik analizy wraz ze źródłami i fingerprintami.",
                    "Dowód — odwołanie do sesji, klucza wiadomości i dokładnego `source_row`.",
                ),
            ),
            S(
                "Dlaczego to ważne",
                paragraphs=(
                    "Rozdzielenie surowych danych od wniosków pozwala powtarzać analizę innym algorytmem, porównywać wersje wyników i wracać do pierwotnej ramki bez utraty kontekstu.",
                ),
            ),
        ),
        ("source-of-truth", "artifacts", "evidence-navigation"),
    ),
    T(
        "source-of-truth",
        "Pierwsze kroki",
        "Źródło prawdy i niezmienność danych",
        "Jak CRT chroni surowe sesje i dlaczego widok nie jest tym samym co zapis.",
        ("source of truth", "raw", "surowe ramki", "niezmienność", "bezpieczeństwo"),
        (
            S(
                "Surowa sesja",
                paragraphs=(
                    "Pełny zapis ramek pozostaje na dysku w kolejności przechwycenia. GUI używa ograniczonych stron i próbek, aby zachować responsywność, ale nie oznacza to ograniczenia źródłowego logu.",
                ),
            ),
            S(
                "Co nie zmienia źródła",
                bullets=(
                    "filtry widoku",
                    "grupowanie ramek",
                    "dekodowanie DBC i UDS",
                    "wyszukiwanie",
                    "analizy porównawcze",
                    "eksport wyników analiz",
                ),
            ),
            S(
                "Kontrola wyników",
                note="Każdy istotny wynik powinien dać się zweryfikować przez otwarcie właściwej sesji i dokładnego wiersza źródłowego.",
            ),
        ),
        ("bounded-model", "artifacts", "evidence-navigation"),
    ),
    T(
        "projects",
        "Projekt i organizacja badań",
        "Tworzenie i otwieranie projektów",
        "Folder projektu, manifest, ustawienia domyślne i bezpieczna zmiana aktywnego projektu.",
        ("nowy projekt", "otwórz projekt", "manifest", "folder"),
        (
            S(
                "Nowy projekt",
                steps=(
                    "Wybierz lokalizację folderu projektu.",
                    "Podaj nazwę i opis badanego ECU.",
                    "Ustaw domyślny bitrate i tryb odbioru.",
                    "Po utworzeniu sprawdź kartę `Przegląd` i właściwości projektu.",
                ),
            ),
            S(
                "Otwieranie",
                paragraphs=(
                    "CRT zapamiętuje ostatnio używany projekt. Przy starcie może otworzyć go automatycznie, jeśli manifest nadal istnieje.",
                    "Zmiana projektu jest blokowana podczas aktywnej rejestracji. Najpierw zatrzymaj Live Capture, aby nie rozdzielić jednej sesji pomiędzy dwa projekty.",
                ),
            ),
            S(
                "Przenoszenie",
                note="Projekt jest projektowany jako samodzielny folder. Przenoś cały folder, a nie pojedynczy plik bazy lub sam log.",
            ),
        ),
        ("project-properties", "sessions", "backup"),
    ),
    T(
        "project-properties",
        "Projekt i organizacja badań",
        "Właściwości projektu i profil ECU",
        "Metadane identyfikacyjne, hipotezy, źródła informacji i stopień weryfikacji.",
        ("właściwości", "profil ECU", "VIN", "hardware", "software", "hipoteza"),
        (
            S(
                "Dane identyfikacyjne",
                bullets=(
                    "producent, rodzina i model",
                    "part number i serial number",
                    "VIN",
                    "hardware version i software version",
                    "procesor i stan badanego ECU",
                ),
            ),
            S(
                "Fakty i hipotezy",
                paragraphs=(
                    "Dane mogą pochodzić z etykiety, diagnostyki, pliku, dokumentacji lub analizy CAN. Warto zapisywać źródło oraz status weryfikacji zamiast nadpisywać niepewną informację jako fakt.",
                ),
            ),
        ),
        ("projects", "study-areas", "evidence-navigation"),
    ),
    T(
        "study-areas",
        "Projekt i organizacja badań",
        "Obszary badań i organizacja sesji",
        "Tematyczne grupowanie logów oraz utrzymywanie kontekstu eksperymentu.",
        ("obszar badań", "EGR", "VGT", "SCR", "organizacja"),
        (
            S(
                "Zastosowanie",
                paragraphs=(
                    "Obszar badań grupuje sesje dotyczące jednego problemu lub funkcji ECU. Dzięki temu projekt może zawierać wiele etapów badań bez mieszania logów rozruchu, EGR, SCR i diagnostyki.",
                ),
            ),
            S(
                "Dobre nazewnictwo",
                bullets=(
                    "krótka nazwa funkcji lub hipotezy",
                    "spójne nazwy sesji z datą lub wariantem testu",
                    "opis warunków stanowiska i zmian pomiędzy przebiegami",
                ),
            ),
        ),
        ("sessions", "markers", "comparison-sets"),
    ),
    T(
        "sessions",
        "Projekt i organizacja badań",
        "Sesje, import i metadane przebiegu",
        "Rejestracja nowych sesji oraz import istniejących logów CRT i CSV.",
        ("sesja", "import", "CSV", "log", "metadata"),
        (
            S(
                "Sesja rejestrowana",
                paragraphs=(
                    "Sesja powstaje podczas Live Capture. Zawiera surowe ramki, timestampy, kanał, flagi, markery i metadane zapisu.",
                ),
            ),
            S(
                "Import",
                steps=(
                    "Otwórz projekt.",
                    "Wybierz `Plik → Importuj log…`.",
                    "Wskaż plik CRT JSONL lub obsługiwany CSV.",
                    "Poczekaj na zakończenie zadania i sprawdź komunikaty w panelu wyjściowym.",
                    "Uzupełnij nazwę, opis i przypisanie do obszaru badań.",
                ),
            ),
            S(
                "Walidacja importu",
                warning="Po imporcie sprawdź bitrate, kanał, typ identyfikatora, jednostkę czasu i kompletność danych. CSV pochodzące z różnych narzędzi mogą różnić się semantyką kolumn.",
            ),
        ),
        ("live-capture", "stored-sessions", "backup"),
    ),
    T(
        "live-capture",
        "Rejestracja i ramki CAN",
        "Live Capture — uruchamianie i zatrzymywanie rejestracji",
        "Bezpieczny przebieg aktywnego przechwytywania ramek CAN.",
        ("live capture", "start", "stop", "Kvaser", "CANlib", "bitrate"),
        (
            S(
                "Przed uruchomieniem",
                bullets=(
                    "sprawdź interfejs CAN i bitrate",
                    "potwierdź masę, zasilanie ECU i terminację magistrali",
                    "upewnij się, że aktywny projekt odpowiada badanemu ECU",
                    "przygotuj plan markerów i warunków testu",
                ),
            ),
            S(
                "Podczas rejestracji",
                paragraphs=(
                    "Widok Live Capture prezentuje ograniczony bufor roboczy. Pełny zapis źródłowy jest prowadzony niezależnie od liczby ramek widocznych w tabeli.",
                ),
                bullets=(
                    "dodawaj markery przed zmianą stanu",
                    "obserwuj status połączenia i liczniki",
                    "nie zmieniaj projektu w trakcie aktywnego capture",
                    "zatrzymaj rejestrację przed zamknięciem programu",
                ),
            ),
            S(
                "Po zatrzymaniu",
                steps=(
                    "Nadaj sesji jednoznaczną nazwę.",
                    "Dodaj opis warunków i celu testu.",
                    "Przypisz sesję do obszaru badań.",
                    "Otwórz zapisaną sesję i sprawdź początek, koniec oraz markery.",
                ),
            ),
        ),
        ("raw-frames", "markers", "live-filters"),
    ),
    T(
        "raw-frames",
        "Rejestracja i ramki CAN",
        "Surowe ramki CAN i klucz wiadomości",
        "Znaczenie pól ramki oraz jednoznacznego klucza używanego przez analizy.",
        ("CAN ID", "STD", "EXT", "DLC", "payload", "message key", "source_row"),
        (
            S(
                "Podstawowe pola",
                bullets=(
                    "timestamp — czas odebrania ramki",
                    "kanał — fizyczny lub logiczny kanał interfejsu",
                    "CAN ID — identyfikator 11- lub 29-bitowy",
                    "STD/EXT — rodzaj identyfikatora",
                    "DLC i długość danych",
                    "payload — bajty danych",
                    "flagi remote/error",
                    "sequence i `source_row` — pozycja w źródłowej sesji",
                ),
            ),
            S(
                "Dokładny klucz wiadomości",
                paragraphs=(
                    "Analizy czasowe używają formatu `kanał:STD/EXT:CAN_ID:typ`, na przykład `0:EXT:18DA30F9:data`. Klucz rozróżnia ten sam CAN ID występujący na innym kanale, w innym formacie lub jako remote/error frame.",
                ),
            ),
        ),
        ("stored-sessions", "timeline", "evidence-navigation"),
    ),
    T(
        "live-filters",
        "Rejestracja i ramki CAN",
        "Filtry Live Capture i filtry globalne",
        "Ograniczanie widoku bez utraty pełnego surowego zapisu.",
        ("filtry", "global filter", "include", "exclude", "live"),
        (
            S(
                "Cel filtrów",
                paragraphs=(
                    "Filtr pomaga obserwować interesujące ID, kanały, payloady lub reguły podczas intensywnego ruchu. Nie powinien zmieniać kompletności zapisywanej sesji źródłowej.",
                ),
            ),
            S(
                "Dobra praktyka",
                steps=(
                    "Zacznij od szerokiego widoku i potwierdź ruch.",
                    "Dodawaj reguły etapami.",
                    "Sprawdź liczbę ukrytych i widocznych ramek.",
                    "Zapisz nazwany zestaw filtrów, gdy ma być używany ponownie.",
                    "Przy interpretacji wróć do surowej sesji lub jawnie wyczyść filtry.",
                ),
            ),
            S(
                "Ryzyko interpretacyjne",
                warning="Pusty widok po zastosowaniu filtra nie oznacza pustej sesji. Najpierw wyczyść filtry i sprawdź klucz wiadomości, kanał oraz STD/EXT.",
            ),
        ),
        ("source-of-truth", "raw-frames", "troubleshooting-empty"),
    ),
    T(
        "markers",
        "Rejestracja i ramki CAN",
        "Markery operatora",
        "Zapisywanie kontekstu eksperymentu bez modyfikowania ramek CAN.",
        ("marker", "znacznik", "operator", "event", "anchor"),
        (
            S(
                "Do czego służą",
                paragraphs=(
                    "Marker opisuje moment eksperymentu, np. `otwarcie EGR`, `zapłon ON`, `start procedury`, `odłączenie czujnika`. Jest przechowywany obok sesji i może pełnić rolę kotwicy osi czasu.",
                ),
            ),
            S(
                "Dobre markery",
                bullets=(
                    "krótkie i jednoznaczne nazwy",
                    "dodanie tuż przed lub tuż po obserwowanym zdarzeniu",
                    "stałe nazewnictwo w sesji bazowej i porównywanej",
                    "opis wariantu w notatce sesji, nie w przypadkowej nazwie markera",
                ),
            ),
        ),
        ("timeline", "study-areas", "sessions"),
    ),
    T(
        "stored-sessions",
        "Zapisane sesje i wyszukiwanie",
        "Przeglądanie zapisanej sesji",
        "Stronicowany widok ramek, wiadomości logiczne i przechodzenie do źródła.",
        ("stored session", "zapisana sesja", "strona", "paging", "ramka"),
        (
            S(
                "Model stronicowany",
                paragraphs=(
                    "CRT nie ładuje całej wielomilionowej sesji do tabeli. Otwiera ograniczoną stronę, a pełny log pozostaje dostępny przez indeks i nawigację do konkretnego `source_row`.",
                ),
            ),
            S(
                "Co można sprawdzać",
                bullets=(
                    "surowe ramki i payloady",
                    "wiadomości pogrupowane według ID",
                    "markery i czas względny",
                    "dekodowanie DBC",
                    "komunikaty ISO-TP i UDS",
                    "wyniki wyszukiwania w całym logu",
                ),
            ),
        ),
        ("bounded-model", "search", "dbc"),
    ),
    T(
        "search",
        "Zapisane sesje i wyszukiwanie",
        "Wyszukiwanie w sesjach i projekcie",
        "Znajdowanie CAN ID, payloadów, tekstu i wyników poza aktualnie widoczną stroną.",
        ("search", "wyszukiwanie", "indeks", "payload", "CAN ID"),
        (
            S(
                "Indeks trwały",
                paragraphs=(
                    "Wyszukiwanie korzysta z trwałych indeksów projektu. Dzięki temu wynik może wskazywać ramkę znajdującą się daleko poza aktualną stroną bez ładowania całej sesji do pamięci.",
                ),
            ),
            S(
                "Typowy przepływ",
                steps=(
                    "Wpisz CAN ID, fragment payloadu lub tekst ASCII.",
                    "Zawęź wynik kanałem, typem ID lub zakresem sesji.",
                    "Otwórz wynik.",
                    "CRT przełączy stronę i zaznaczy właściwy `source_row`.",
                ),
            ),
            S(
                "Aktualność indeksu",
                note="Po imporcie lub zapisie nowej sesji indeks może być budowany w tle. Do czasu zakończenia niektóre wyniki mogą być niedostępne albo wymagać pasywnego skanowania fallbackowego.",
            ),
        ),
        ("stored-sessions", "evidence-navigation", "performance"),
    ),
    T(
        "dbc",
        "Dekodowanie i protokoły",
        "Dekodery DBC",
        "Dodawanie plików DBC, aktywacja i wpływ dekodera na widoki.",
        ("DBC", "decoder", "signal", "sygnał", "database"),
        (
            S(
                "Zastosowanie",
                paragraphs=(
                    "DBC mapuje ramki CAN na wiadomości i sygnały fizyczne. Dekodowanie jest warstwą interpretacji; surowy payload pozostaje dostępny niezależnie od aktywnego DBC.",
                ),
            ),
            S(
                "Przepływ",
                steps=(
                    "Otwórz `Dekodery`.",
                    "Dodaj plik DBC do projektu.",
                    "Aktywuj właściwy wariant.",
                    "Otwórz sesję lub rozpocznij nowy capture.",
                    "Porównaj wartość sygnału z surowym payloadem i definicją endian/scaling.",
                ),
            ),
            S(
                "Zmiana podczas capture",
                warning="Zmiana aktywnych DBC podczas trwającej rejestracji nie powinna zmieniać zestawu przypisanego do już rozpoczętej sesji. Nowa konfiguracja jest używana przy następnym uruchomieniu capture.",
            ),
        ),
        ("raw-frames", "uds-basics", "troubleshooting-decode"),
    ),
    T(
        "isotp-uds",
        "Dekodowanie i protokoły",
        "ISO-TP i wiadomości logiczne UDS",
        "Składanie wielu ramek CAN w jeden komunikat diagnostyczny.",
        ("ISO-TP", "UDS", "single frame", "first frame", "consecutive frame", "flow control"),
        (
            S(
                "Warstwa transportowa",
                paragraphs=(
                    "ISO-TP pozwala przesyłać komunikaty dłuższe niż pojedyncza ramka CAN. CRT może prezentować Single Frame oraz rekonstruować sekwencje First Frame, Consecutive Frame i Flow Control.",
                ),
            ),
            S(
                "Kompletność",
                bullets=(
                    "komunikat kompletny — wszystkie wymagane fragmenty zostały odebrane",
                    "komunikat niekompletny — brakuje ramki, kolejność jest błędna lub capture zakończył się wcześniej",
                    "błąd transportu — wynik powinien być traktowany jako ostrzeżenie, nie pełna odpowiedź UDS",
                ),
            ),
        ),
        ("uds-basics", "uds-latency", "uds-transactions"),
    ),
    T(
        "uds-basics",
        "Dekodowanie i protokoły",
        "Podstawy UDS w CRT",
        "SID, odpowiedzi pozytywne i negatywne, DID, subfunkcja, Routine ID i NRC.",
        ("SID", "DID", "Routine ID", "NRC", "0x78", "UDS"),
        (
            S(
                "Usługa i odpowiedź",
                bullets=(
                    "żądanie zaczyna się od SID, np. `0x22 ReadDataByIdentifier`",
                    "odpowiedź pozytywna zwykle używa SID + `0x40`, np. `0x62`",
                    "odpowiedź negatywna ma format `0x7F requestSID NRC`",
                    "`0x78 ResponsePending` oznacza odpowiedź pośrednią, a nie końcowy wynik",
                ),
            ),
            S(
                "Identyfikatory",
                bullets=(
                    "DID — identyfikator danych, np. `F190` dla VIN w typowym UDS",
                    "subfunkcja — drugi bajt wielu usług, z wyzerowanym bitem suppress-positive-response",
                    "Routine ID — dwubajtowy identyfikator procedury usługi `0x31`",
                    "NRC — kod przyczyny odpowiedzi negatywnej",
                ),
            ),
            S(
                "Adresowanie",
                warning="Analizy Stage 2C2 wymagają jawnego podania dokładnego klucza CAN request i response. CRT nie powinien zgadywać par adresów, gdy w logu występuje wiele testerów lub ECU.",
            ),
        ),
        ("isotp-uds", "uds-latency", "uds-transactions"),
    ),
    T(
        "comparison-sets",
        "Porównywanie logów",
        "Zestawy porównawcze",
        "Trwałe wybieranie sesji bazowej i sesji porównywanych.",
        ("comparison set", "zestaw porównawczy", "baseline", "baza"),
        (
            S(
                "Cel zestawu",
                paragraphs=(
                    "Zestaw porównawczy zapisuje, które sesje mają być analizowane razem i która z nich jest bazą. Dzięki temu te same analizy można powtarzać bez ponownego ręcznego wyboru logów.",
                ),
            ),
            S(
                "Dobór sesji",
                bullets=(
                    "podobne warunki stanowiska i czas trwania",
                    "jednoznaczna różnica badanego warunku",
                    "spójne markery lub wspólne kotwice",
                    "ta sama prędkość i kanał CAN",
                    "właściwa sesja bazowa reprezentująca stan odniesienia",
                ),
            ),
        ),
        ("comparison-dashboard", "timeline", "artifacts"),
    ),
    T(
        "comparison-dashboard",
        "Porównywanie logów",
        "Przegląd graficzny porównania",
        "KPI, heatmapa obecności, częstotliwości, payloady i kolejność wiadomości.",
        ("dashboard", "KPI", "heatmap", "częstotliwość", "payload", "sequence"),
        (
            S(
                "Główne elementy",
                bullets=(
                    "KPI nowych i brakujących kluczy wiadomości",
                    "liczba zmian payloadu i sekwencji",
                    "heatmapa obecności wiadomości w sesjach",
                    "ranking zmian częstotliwości",
                    "pełna tabela różnic z filtrowaniem i sortowaniem",
                    "inspektor klucza wiadomości i podgląd payloadu",
                ),
            ),
            S(
                "Interpretacja",
                paragraphs=(
                    "Nowy lub brakujący ID może wynikać z rzeczywistej zmiany stanu, ale również z różnej długości sesji, opóźnionego startu capture albo niespójnych filtrów wejściowych. Zawsze otwórz dowód źródłowy.",
                ),
            ),
        ),
        ("comparison-sets", "timing-jitter", "evidence-navigation"),
    ),
    T(
        "timeline",
        "Porównywanie logów",
        "Oś czasu i trwałe wyrównanie sesji",
        "Wspólna skala czasu, kotwice oraz odtwarzanie zapisanej osi bez skanowania.",
        ("timeline", "oś czasu", "alignment", "kotwica", "marker", "source_row"),
        (
            S(
                "Tryby synchronizacji",
                bullets=(
                    "początek każdej sesji",
                    "N-te wystąpienie dokładnego klucza wiadomości",
                    "N-ty marker operatora o określonej nazwie",
                    "osobna dokładna ramka-kotwica wskazana dla każdej sesji",
                ),
            ),
            S(
                "Bounded model osi",
                paragraphs=(
                    "Oś przechowuje ograniczoną, deterministyczną próbkę punktów dla każdej sesji, zachowując początek, koniec i dokładną kotwicę. Każdy punkt posiada rzeczywisty `source_row`.",
                ),
            ),
            S(
                "Trwałe wyrównanie",
                paragraphs=(
                    "Po zapisaniu wyrównania CRT może ponownie otworzyć oś bez skanowania sesji. Zgodność jest kontrolowana przez kolejność sesji, liczbę ramek i SHA-256.",
                ),
            ),
        ),
        ("markers", "timing-jitter", "artifacts"),
    ),
    T(
        "timing-jitter",
        "Porównywanie logów",
        "Timing i jitter wiadomości CAN",
        "Analiza odstępów pomiędzy kolejnymi wystąpieniami jednego klucza wiadomości.",
        ("timing", "jitter", "inter-frame", "p95", "p05", "frequency", "gap"),
        (
            S(
                "Metryki",
                bullets=(
                    "średnia, mediana, minimum i maksimum odstępu",
                    "percentyle p05, p25, p75, p95 i p99",
                    "jitter `p95 − p05`",
                    "RMS odchylenia od mediany",
                    "współczynnik zmienności",
                    "częstotliwość wynikająca z mediany",
                    "liczba długich przerw",
                ),
            ),
            S(
                "Przerwy",
                paragraphs=(
                    "Próg przerwy jest wyrażony jako mnożnik mediany. CRT dokładnie zlicza wszystkie przerwy, a jako dowody zachowuje ograniczoną liczbę najdłuższych par ramek.",
                ),
            ),
            S(
                "Jak czytać wynik",
                bullets=(
                    "stabilna mediana i rosnące p95 — pojedyncze opóźnienia lub nieregularny ogon",
                    "rosnący jitter — mniej stabilny cykl transmisji",
                    "spadek częstotliwości — dłuższy typowy okres",
                    "pojedyncza długa przerwa — otwórz obie ramki tworzące odstęp",
                ),
            ),
        ),
        ("timeline", "percentiles", "evidence-navigation"),
    ),
    T(
        "uds-latency",
        "Porównywanie logów",
        "Latencja UDS i parowanie request/response",
        "Pasywne mierzenie czasu do pierwszej i końcowej odpowiedzi diagnostycznej.",
        ("latencja UDS", "request response", "0x78", "timeout", "p50", "p95"),
        (
            S(
                "Konfiguracja",
                steps=(
                    "Podaj dokładny klucz wiadomości żądania.",
                    "Podaj dokładny klucz odpowiedzi.",
                    "Ustaw timeout odpowiedni do badanego ECU i usługi.",
                    "Uruchom analizę dla zestawu porównawczego.",
                ),
            ),
            S(
                "Parowanie",
                paragraphs=(
                    "CRT rekonstruuje ISO-TP i paruje transakcje deterministycznie według bazowego SID. `0x78 ResponsePending` jest odpowiedzią pośrednią, zapisuje czas pierwszej reakcji i odnawia oczekiwanie na odpowiedź końcową.",
                ),
            ),
            S(
                "Statusy",
                bullets=(
                    "positive-response",
                    "negative-response",
                    "timeout",
                    "capture-ended",
                    "suppressed-no-response",
                ),
            ),
            S(
                "Granice",
                warning="Analiza nie wykrywa automatycznie właściwej pary CAN ID i nie obsługuje wszystkich niestandardowych wariantów adresowania ISO-TP. Błędne klucze mogą dać zero transakcji mimo obecności ruchu diagnostycznego.",
            ),
        ),
        ("uds-basics", "uds-transactions", "percentiles"),
    ),
    T(
        "uds-transactions",
        "Porównywanie logów",
        "Eksplorator transakcji UDS",
        "Filtrowanie, korelacja protokołowa, grupowanie i eksport trwałych dowodów Stage 2C2.",
        ("Transakcje UDS", "DID", "Routine ID", "NRC", "CSV", "artifact"),
        (
            S(
                "Źródło danych",
                paragraphs=(
                    "Karta pracuje na trwałym artefakcie `comparison_uds_latency`. Nie skanuje ponownie surowych sesji i nie zmienia reguł parowania.",
                    "Gdy istnieje kilka zgodnych wyników, preferowany jest najnowszy artefakt zawierający transakcje. Nowsze puste artefakty są pomijane, aby nie zasłaniały wcześniejszego poprawnego wyniku.",
                ),
            ),
            S(
                "Filtry i grupowanie",
                bullets=(
                    "sesja, SID, status, NRC, payload, czas i final latency",
                    "grupowanie automatyczne",
                    "grupowanie według SID, DID, subfunkcji lub Routine ID",
                    "porównanie grup z sesją bazową",
                ),
            ),
            S(
                "Dowody i eksport",
                bullets=(
                    "pełne payloady request, first response, final response i zachowanych `0x78`",
                    "nawigacja do dokładnego `source_row`",
                    "eksport transakcji i grup do UTF-8 BOM CSV z separatorem `;`",
                ),
            ),
            S(
                "Bounded evidence",
                warning="Jeżeli widzisz `evidence_truncated`, tabela i CSV opisują zachowane pary dowodowe, a nie wszystkie transakcje sesji. Dokładne globalne liczniki pozostają w karcie `Latencja UDS`.",
            ),
        ),
        ("uds-latency", "artifacts", "evidence-navigation"),
    ),
    T(
        "artifacts",
        "Artefakty i dowody",
        "Trwałe artefakty analiz",
        "Wersjonowane wyniki, fingerprinty źródeł i bezpieczne ponowne otwieranie.",
        ("artefakt", "analysis run", "fingerprint", "SHA-256", "schema"),
        (
            S(
                "Co zawiera artefakt",
                bullets=(
                    "typ i wersję schematu",
                    "provider, wersję algorytmu i parametry",
                    "odwołania do sesji źródłowych",
                    "fingerprinty, m.in. `frame_count` i SHA-256",
                    "wynik analizy i metadane ostrzeżeń",
                ),
            ),
            S(
                "Zgodność",
                paragraphs=(
                    "Przy ponownym otwieraniu CRT odrzuca artefakt, gdy zmieniła się kolejność sesji, liczba ramek, identyfikator źródła lub SHA-256. Chroni to przed prezentowaniem starego wyniku jako aktualnego.",
                ),
            ),
            S(
                "Wiele wersji",
                note="Nowszy artefakt nie zawsze jest lepszy. Może mieć inne parametry albo być pusty. Widok powinien jawnie pokazać wybrany artefakt i zastosowane parametry.",
            ),
        ),
        ("project-model", "source-of-truth", "uds-transactions"),
    ),
    T(
        "evidence-navigation",
        "Artefakty i dowody",
        "Nawigacja do dowodu źródłowego",
        "Jak wynik analizy otwiera właściwą sesję i dokładną ramkę.",
        ("dowód", "source_row", "open evidence", "ramka źródłowa", "navigator"),
        (
            S(
                "Przekazywane dane",
                bullets=(
                    "identyfikator sesji",
                    "dokładny `source_row`",
                    "pełny klucz wiadomości",
                    "opcjonalny kontekst analizy lub transakcji",
                ),
            ),
            S(
                "Przepływ",
                steps=(
                    "Wybierz wiersz, punkt osi lub transakcję.",
                    "Kliknij przycisk otwarcia dowodu.",
                    "CRT otworzy właściwą sesję.",
                    "Widok przejdzie do strony zawierającej ramkę.",
                    "Dokładny wiersz zostanie zaznaczony.",
                ),
            ),
            S(
                "Weryfikacja",
                warning="Nie opieraj wniosku wyłącznie na tabeli agregującej. Sprawdź sąsiednie ramki, znaczniki, czas i pełny payload w źródłowej sesji.",
            ),
        ),
        ("stored-sessions", "comparison-dashboard", "uds-transactions"),
    ),
    T(
        "bounded-model",
        "Bezpieczeństwo i wydajność",
        "Bounded model GUI",
        "Dlaczego program pokazuje ograniczone strony i próbki mimo pełnego logu na dysku.",
        ("bounded", "page size", "sample", "memory", "performance", "truncated"),
        (
            S(
                "Cel",
                paragraphs=(
                    "Wielomilionowa sesja nie powinna być materializowana w pojedynczym modelu Qt. CRT używa stron, ograniczonych list dowodów i deterministycznych próbek, aby zachować responsywność.",
                ),
            ),
            S(
                "Co może być ograniczone",
                bullets=(
                    "liczba ramek aktualnie widocznych w tabeli",
                    "liczba punktów na osi czasu",
                    "próbka użyta do percentyli",
                    "lista najdłuższych przerw",
                    "lista transakcji dowodowych w artefakcie",
                ),
            ),
            S(
                "Co powinno pozostać dokładne",
                bullets=(
                    "pełny zapis surowych ramek",
                    "kolejność źródłowa",
                    "globalne liczniki, gdy algorytm tak deklaruje",
                    "nawigacja zachowanego dowodu do dokładnego `source_row`",
                ),
            ),
        ),
        ("source-of-truth", "percentiles", "performance"),
    ),
    T(
        "percentiles",
        "Bezpieczeństwo i wydajność",
        "Percentyle, mediana i jitter",
        "Praktyczna interpretacja metryk czasowych bez mylenia średniej z typowym zachowaniem.",
        ("percentyl", "p50", "p95", "p99", "mediana", "średnia", "jitter"),
        (
            S(
                "Znaczenie",
                bullets=(
                    "p50 — mediana; połowa próbek jest mniejsza lub równa tej wartości",
                    "p95 — poziom, którego nie przekracza około 95% próbek",
                    "p99 — zachowanie bardzo wolnego ogona",
                    "średnia — wrażliwa na pojedyncze duże opóźnienia",
                    "jitter p95−p05 — szerokość typowego rozrzutu",
                ),
            ),
            S(
                "Przykład interpretacji",
                paragraphs=(
                    "Jeżeli p50 pozostaje stabilne, ale p95 rośnie, typowa odpowiedź nadal jest podobna, lecz częściej pojawiają się wolne przypadki. Jeżeli jednocześnie rośnie p50, pogorszenie jest bardziej systematyczne.",
                ),
            ),
            S(
                "Próbkowanie",
                note="W dużych analizach percentyle mogą być wyznaczane z deterministycznej bounded próbki. Raport powinien odróżniać dokładne liczniki od statystyk próbkowanych.",
            ),
        ),
        ("timing-jitter", "uds-latency", "bounded-model"),
    ),
    T(
        "backup",
        "Bezpieczeństwo i wydajność",
        "Kopie zapasowe i przenoszenie projektu",
        "Jak zabezpieczyć pełną teczkę badawczą bez rozdzielania danych i indeksów.",
        ("backup", "kopia zapasowa", "przenoszenie", "folder projektu"),
        (
            S(
                "Zakres kopii",
                paragraphs=(
                    "Kopiuj cały folder projektu, gdy capture i zadania zapisu są zatrzymane. Sam plik `project.sqlite` nie zawiera wszystkich sesji i artefaktów.",
                ),
            ),
            S(
                "Przed kopią",
                steps=(
                    "Zatrzymaj Live Capture.",
                    "Poczekaj na zakończenie importu, indeksowania i analiz.",
                    "Zamknij CRT albo upewnij się, że nie trwa zapis.",
                    "Skopiuj cały katalog projektu.",
                    "Otwórz kopię w CRT i sprawdź listę sesji oraz artefakty.",
                ),
            ),
        ),
        ("projects", "artifacts", "troubleshooting-recovery"),
    ),
    T(
        "performance",
        "Bezpieczeństwo i wydajność",
        "Wydajność, indeksowanie i zadania w tle",
        "Jak rozpoznać normalną pracę tła i rzeczywiste zawieszenie aplikacji.",
        ("performance", "wydajność", "indeksowanie", "QThreadPool", "background"),
        (
            S(
                "Zadania w tle",
                bullets=(
                    "import logów",
                    "budowanie indeksów",
                    "skanowanie sesji przez analizę",
                    "zapis i odczyt dużych artefaktów",
                    "nawigacja wymagająca odnalezienia wiersza poza bieżącą stroną",
                ),
            ),
            S(
                "Oczekiwane zachowanie",
                paragraphs=(
                    "Długie operacje powinny działać poza wątkiem GUI, pokazywać postęp i umożliwiać anulowanie. Anulowanie unieważnia wynik spóźnionego zadania, aby stary callback nie nadpisał nowszego widoku.",
                ),
            ),
            S(
                "Gdy jest wolno",
                steps=(
                    "Sprawdź panel zadań i komunikaty.",
                    "Potwierdź rozmiar sesji i stan indeksu.",
                    "Nie uruchamiaj wielokrotnie tej samej analizy.",
                    "Poczekaj na zakończenie lub użyj `Anuluj`.",
                    "Jeśli GUI nie odpowiada, zapisz log diagnostyczny i zanotuj ostatnią akcję.",
                ),
            ),
        ),
        ("bounded-model", "search", "troubleshooting-recovery"),
    ),
    T(
        "troubleshooting-empty",
        "Rozwiązywanie problemów",
        "Pusty widok lub zero wyników",
        "Najczęstsze przyczyny braku ramek, transakcji albo punktów analizy.",
        ("zero wyników", "pusty", "no data", "filtr", "artefakt"),
        (
            S(
                "Sprawdź kolejno",
                steps=(
                    "Wyczyść filtry widoku.",
                    "Potwierdź aktywną sesję i zestaw porównawczy.",
                    "Sprawdź kanał, STD/EXT i dokładny CAN ID.",
                    "Dla UDS sprawdź osobno request i response message key.",
                    "Otwórz kartę źródłową, np. `Latencja UDS`, i potwierdź liczbę żądań.",
                    "Sprawdź, który artefakt został wczytany i z jakimi parametrami.",
                    "Potwierdź, że indeks lub analiza zakończyły się sukcesem.",
                ),
            ),
            S(
                "Pusty artefakt",
                paragraphs=(
                    "Pusty wynik może być poprawnym rezultatem analizy uruchomionej z błędnymi kluczami albo na sesji bez danego ruchu. W eksploratorze UDS nowszy pusty artefakt nie powinien zasłaniać wcześniejszego niepustego.",
                ),
            ),
        ),
        ("live-filters", "uds-latency", "artifacts"),
    ),
    T(
        "troubleshooting-decode",
        "Rozwiązywanie problemów",
        "Błędne dekodowanie DBC lub UDS",
        "Diagnoza nieprawidłowych wartości sygnałów i komunikatów logicznych.",
        ("błędne dekodowanie", "DBC", "UDS", "endian", "scaling", "ISO-TP"),
        (
            S(
                "DBC",
                bullets=(
                    "sprawdź aktywny plik i wariant wiadomości",
                    "potwierdź STD/EXT i CAN ID",
                    "sprawdź endian, start bit, długość, signed i scaling",
                    "porównaj wartość z surowym payloadem",
                ),
            ),
            S(
                "ISO-TP i UDS",
                bullets=(
                    "sprawdź, czy wybrano właściwe ID request i response",
                    "potwierdź kompletność First/Consecutive Frames",
                    "sprawdź kolejność sekwencji i brakujące ramki",
                    "odróżnij `0x78` od odpowiedzi końcowej",
                ),
            ),
        ),
        ("dbc", "isotp-uds", "raw-frames"),
    ),
    T(
        "troubleshooting-kvaser",
        "Rozwiązywanie problemów",
        "Kvaser, CANlib i brak komunikacji",
        "Podstawowa diagnostyka interfejsu bez zmieniania warstwy zapisu CRT.",
        ("Kvaser", "CANlib", "channel", "driver", "bus off", "bitrate"),
        (
            S(
                "Podstawowe kontrole",
                steps=(
                    "Sprawdź, czy urządzenie jest widoczne w systemie i narzędziach Kvaser.",
                    "Potwierdź wybrany kanał i bitrate.",
                    "Sprawdź terminację, masę i stan zasilania ECU.",
                    "Upewnij się, że inny program nie blokuje kanału.",
                    "Zamknij i ponownie otwórz kanał zamiast wielokrotnie uruchamiać capture.",
                ),
            ),
            S(
                "Bezpieczeństwo",
                warning="Nie przechodź do aktywnego TX jako pierwszego testu. Najpierw potwierdź pasywny odbiór, poprawny bitrate i stabilny stan magistrali.",
            ),
        ),
        ("live-capture", "troubleshooting-empty", "source-of-truth"),
    ),
    T(
        "troubleshooting-recovery",
        "Rozwiązywanie problemów",
        "Bezpieczne odzyskiwanie po błędzie",
        "Co zrobić po przerwanym imporcie, analizie, zamknięciu okna lub awarii procesu.",
        ("recovery", "odzyskiwanie", "crash", "cancel", "failed"),
        (
            S(
                "Najpierw zabezpiecz projekt",
                steps=(
                    "Nie usuwaj ręcznie plików sesji ani bazy.",
                    "Zamknij proces CRT, jeśli nadal działa w tle.",
                    "Wykonaj kopię całego folderu projektu.",
                    "Uruchom CRT i otwórz projekt z kopii lub oryginału.",
                    "Sprawdź listę sesji, stan analysis runs i komunikaty błędów.",
                ),
            ),
            S(
                "Ponowne uruchomienie analizy",
                paragraphs=(
                    "Niekompletny lub failed analysis run nie powinien nadpisywać poprzedniego poprawnego artefaktu. Uruchom analizę ponownie dopiero po ustaleniu parametrów i źródeł.",
                ),
            ),
        ),
        ("backup", "artifacts", "performance"),
    ),
    T(
        "glossary",
        "Słownik i skróty",
        "Słownik pojęć",
        "Najważniejsze terminy używane w interfejsie i raportach CRT.",
        ("słownik", "glossary", "CAN", "UDS", "artefakt", "source_row"),
        (
            S(
                "CAN i transport",
                bullets=(
                    "CAN ID — identyfikator ramki.",
                    "STD/EXT — 11- lub 29-bitowy identyfikator.",
                    "DLC — kod długości danych.",
                    "Payload — bajty danych ramki lub komunikatu.",
                    "ISO-TP — transport wieloramkowy nad CAN.",
                    "UDS — Unified Diagnostic Services.",
                ),
            ),
            S(
                "Analizy",
                bullets=(
                    "Baseline — sesja bazowa.",
                    "Jitter — zmienność odstępu czasowego.",
                    "Percentyl — wartość graniczna dla określonej części próbek.",
                    "Artefakt — trwały, wersjonowany wynik analizy.",
                    "Fingerprint — dane pozwalające sprawdzić zgodność źródła.",
                    "Evidence — zachowany dowód prowadzący do logu.",
                    "`source_row` — dokładny numer wiersza w źródłowej sesji.",
                    "Bounded — jawnie ograniczona liczba elementów w modelu lub artefakcie.",
                ),
            ),
            S(
                "UDS",
                bullets=(
                    "SID — identyfikator usługi.",
                    "DID — identyfikator danych.",
                    "NRC — Negative Response Code.",
                    "Routine ID — identyfikator procedury `0x31`.",
                    "`0x78` — ResponsePending.",
                ),
            ),
        ),
        ("uds-basics", "project-model", "shortcuts"),
    ),
    T(
        "shortcuts",
        "Słownik i skróty",
        "Skróty klawiaturowe i nawigacja",
        "Najważniejsze skróty dostępne w głównym oknie oraz w zakładce Pomoc.",
        ("shortcut", "skrót", "F1", "Ctrl+F", "keyboard"),
        (
            S(
                "Główne skróty",
                bullets=(
                    "`F1` — otwórz Pomoc CRT.",
                    "`Ctrl+F` w Pomocy — ustaw fokus w wyszukiwarce tematów.",
                    "`Alt+Left` / `Alt+Right` w Pomocy — poprzedni lub następny temat w historii.",
                    "`Ctrl+Shift+N` — nowy projekt.",
                    "`Ctrl+Shift+O` — otwórz projekt.",
                    "`Ctrl+I` — importuj log.",
                ),
            ),
            S(
                "Nawigacja w Pomocy",
                paragraphs=(
                    "Wpisz kilka słów w polu wyszukiwania. Wyniki są dopasowywane do tytułu, opisu, słów kluczowych i treści. Dwuklik w drzewie lub kliknięcie tematu otwiera artykuł.",
                ),
            ),
        ),
        ("start", "glossary"),
    ),
)


_TOPIC_BY_ID = {topic.id: topic for topic in HELP_TOPICS}


def help_topic(topic_id: str) -> HelpTopic:
    try:
        return _TOPIC_BY_ID[str(topic_id)]
    except KeyError as exc:
        raise KeyError(f"unknown help topic: {topic_id}") from exc


def help_topics_by_category() -> tuple[tuple[str, tuple[HelpTopic, ...]], ...]:
    return tuple(
        (
            category,
            tuple(topic for topic in HELP_TOPICS if topic.category == category),
        )
        for category in HELP_CATEGORY_ORDER
        if any(topic.category == category for topic in HELP_TOPICS)
    )


def search_help_topics(query: str) -> tuple[HelpTopic, ...]:
    normalized = _normalize(query)
    if not normalized:
        return HELP_TOPICS
    tokens = tuple(token for token in normalized.split() if token)
    ranked: list[tuple[int, int, HelpTopic]] = []
    for order, topic in enumerate(HELP_TOPICS):
        title = _normalize(topic.title)
        summary = _normalize(topic.summary)
        keywords = _normalize(" ".join(topic.keywords))
        body = _normalize(_topic_plain_text(topic))
        haystack = " ".join((title, summary, keywords, body))
        if not all(token in haystack for token in tokens):
            continue
        score = 0
        for token in tokens:
            if token in title:
                score += 40
            if token in keywords:
                score += 20
            if token in summary:
                score += 10
            if token in body:
                score += 2
        ranked.append((-score, order, topic))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in ranked)


def render_help_home_html() -> str:
    categories: list[str] = []
    for category, topics in help_topics_by_category():
        links = "".join(
            f'<li><a href="help://topic/{escape(topic.id)}">{escape(topic.title)}</a>'
            f'<div class="summary">{escape(topic.summary)}</div></li>'
            for topic in topics
        )
        categories.append(f"<h2>{escape(category)}</h2><ul>{links}</ul>")
    return _page(
        "Pomoc CAN Research Tool",
        "<p class=\"lead\">Przeszukiwalny opis funkcji programu, przepływów pracy, ograniczeń i pojęć technicznych.</p>"
        "<div class=\"callout\"><b>Zasada nadrzędna:</b> surowe sesje są źródłem prawdy, a filtry i analizy są warstwą prezentacji lub trwałymi artefaktami.</div>"
        "<h2>Szybkie przejścia</h2>"
        "<div class=\"quick\">"
        '<a href="help://topic/quick-start">Pierwsze badanie</a>'
        '<a href="help://topic/live-capture">Live Capture</a>'
        '<a href="help://topic/comparison-dashboard">Porównanie logów</a>'
        '<a href="help://topic/uds-transactions">Transakcje UDS</a>'
        '<a href="help://topic/troubleshooting-empty">Brak wyników</a>'
        '<a href="help://topic/glossary">Słownik</a>'
        "</div>"
        + "".join(categories),
    )


def render_help_topic_html(topic: HelpTopic) -> str:
    chunks = [f'<p class="lead">{escape(topic.summary)}</p>']
    for section in topic.sections:
        chunks.append(f"<h2>{escape(section.title)}</h2>")
        chunks.extend(f"<p>{_inline(value)}</p>" for value in section.paragraphs)
        if section.bullets:
            chunks.append("<ul>" + "".join(f"<li>{_inline(value)}</li>" for value in section.bullets) + "</ul>")
        if section.steps:
            chunks.append("<ol>" + "".join(f"<li>{_inline(value)}</li>" for value in section.steps) + "</ol>")
        if section.note:
            chunks.append(f'<div class="note"><b>Uwaga:</b> {_inline(section.note)}</div>')
        if section.warning:
            chunks.append(f'<div class="warning"><b>Ważne:</b> {_inline(section.warning)}</div>')
    if topic.related:
        links = []
        for related_id in topic.related:
            related = _TOPIC_BY_ID.get(related_id)
            if related is not None:
                links.append(
                    f'<li><a href="help://topic/{escape(related.id)}">{escape(related.title)}</a></li>'
                )
        if links:
            chunks.append("<h2>Powiązane tematy</h2><ul>" + "".join(links) + "</ul>")
    return _page(topic.title, "".join(chunks))


def _page(title: str, body: str) -> str:
    return f"""
<!doctype html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: sans-serif; line-height: 1.48; margin: 24px 32px 48px; }}
h1 {{ font-size: 26px; margin: 0 0 10px; }}
h2 {{ font-size: 18px; margin-top: 26px; padding-bottom: 5px; border-bottom: 1px solid palette(mid); }}
p, li {{ font-size: 14px; }}
.lead {{ font-size: 16px; }}
.summary {{ opacity: 0.78; margin: 2px 0 8px; }}
.callout, .note, .warning {{ border: 1px solid palette(mid); border-radius: 5px; padding: 10px 12px; margin: 14px 0; }}
.warning {{ border-left: 5px solid #c57b00; }}
.note {{ border-left: 5px solid #3b82c4; }}
.quick {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 20px; }}
.quick a {{ border: 1px solid palette(mid); border-radius: 4px; padding: 7px 10px; text-decoration: none; }}
code {{ font-family: monospace; background: palette(alternate-base); padding: 1px 4px; border-radius: 3px; }}
a {{ text-decoration: none; }}
</style></head><body><h1>{escape(title)}</h1>{body}</body></html>
"""


def _inline(value: str) -> str:
    parts = re.split(r"(`[^`]+`)", str(value))
    rendered: list[str] = []
    for part in parts:
        if len(part) >= 2 and part.startswith("`") and part.endswith("`"):
            rendered.append(f"<code>{escape(part[1:-1])}</code>")
        else:
            rendered.append(escape(part))
    return "".join(rendered)


def _topic_plain_text(topic: HelpTopic) -> str:
    values = [topic.title, topic.summary, " ".join(topic.keywords)]
    for section in topic.sections:
        values.extend((section.title, *section.paragraphs, *section.bullets, *section.steps))
        values.extend((section.note, section.warning))
    return " ".join(value for value in values if value)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value).casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9x]+", without_marks))


__all__ = [
    "HELP_CATEGORY_ORDER",
    "HELP_TOPICS",
    "HelpSection",
    "HelpTopic",
    "help_topic",
    "help_topics_by_category",
    "render_help_home_html",
    "render_help_topic_html",
    "search_help_topics",
]
