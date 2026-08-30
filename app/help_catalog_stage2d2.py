from __future__ import annotations

from .help_catalog import HelpSection, HelpTopic


STAGE2D2_HELP_TOPICS = (
    HelpTopic(
        id="uds-timeline",
        category="Porównywanie logów",
        title="Trwała oś transakcji UDS",
        summary=(
            "Nakładanie request, 0x78 i odpowiedzi końcowej na wspólną, "
            "zapisaną oś czasu sesji."
        ),
        keywords=(
            "oś UDS",
            "UDS timeline",
            "request",
            "response",
            "0x78",
            "timeout",
            "NRC",
            "DID",
            "Routine ID",
            "brakujące transakcje",
            "przesunięte transakcje",
        ),
        sections=(
            HelpSection(
                title="Gdzie znajduje się funkcja",
                steps=(
                    "Otwórz projekt i przejdź do Porównaj.",
                    "Wybierz zestaw porównawczy i kliknij Analizuj wybrany zestaw…",
                    "Otwórz kartę Oś UDS.",
                    "Kliknij Wczytaj trwałą oś UDS, jeżeli karta nie załadowała się automatycznie.",
                ),
            ),
            HelpSection(
                title="Wymagane źródła",
                paragraphs=(
                    "Widok nie skanuje surowych sesji. Łączy ostatnie zgodne zapisane wyrównanie Stage 2B z preferowanym niepustym artefaktem Latencja UDS ze Stage 2C2.",
                ),
                bullets=(
                    "w karcie Oś czasu musi istnieć zapisane wyrównanie",
                    "w karcie Latencja UDS musi istnieć wynik dla właściwych kluczy request/response",
                    "fingerprinty sesji i kolejność zestawu muszą być nadal zgodne",
                ),
                warning=(
                    "Brak jednego z artefaktów nie oznacza braku ruchu UDS w logu. "
                    "Najpierw utwórz i zapisz wymagane wyniki źródłowe."
                ),
            ),
            HelpSection(
                title="Jak czytać wykres",
                bullets=(
                    "początek odcinka oznacza request",
                    "koniec odcinka oznacza pierwszą lub końcową odpowiedź",
                    "fioletowe punkty nad odcinkiem oznaczają 0x78 ResponsePending",
                    "kolor zielony oznacza odpowiedź pozytywną",
                    "kolor czerwony oznacza odpowiedź negatywną",
                    "odcinek przerywany oznacza timeout albo koniec logu",
                    "pomarańczowa ramka oznacza transakcję dodatkową",
                    "żółta ramka oznacza transakcję przesuniętą w kolejności",
                ),
            ),
            HelpSection(
                title="Filtry",
                paragraphs=(
                    "Można ograniczyć widok do sesji, SID, statusu, DID, NRC albo fragmentu payloadu i nazwy korelacji. Filtry nie zmieniają artefaktów źródłowych.",
                ),
            ),
            HelpSection(
                title="Porównanie sekwencji",
                paragraphs=(
                    "CRT porównuje kolejność zachowanych transakcji z sesją bazową. Tabela pokazuje liczbę transakcji brakujących, dodatkowych i przesuniętych. Porównanie jest deterministyczne i działa na bounded dowodach Stage 2C2.",
                ),
                warning=(
                    "Jeżeli źródłowy artefakt ma evidence_truncated, klasyfikacja sekwencji dotyczy zachowanych par dowodowych, a nie wszystkich transakcji sesji."
                ),
            ),
            HelpSection(
                title="Nawigacja do dowodu",
                bullets=(
                    "Otwórz żądanie prowadzi do pierwszej ramki request",
                    "Otwórz pierwszą odpowiedź prowadzi do pierwszego 0x78 albo pierwszej odpowiedzi końcowej",
                    "Otwórz odpowiedź końcową prowadzi do final response",
                    "każde przejście używa dokładnego source_row zapisanego w artefakcie",
                ),
            ),
        ),
        related=(
            "timeline",
            "uds-latency",
            "uds-transactions",
            "evidence-navigation",
            "artifacts",
        ),
    ),
)


__all__ = ["STAGE2D2_HELP_TOPICS"]
