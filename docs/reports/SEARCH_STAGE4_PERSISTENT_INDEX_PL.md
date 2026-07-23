# Wyszukiwanie — Etap 4: trwałe indeksy projektu

## Status

Etap 4 jest funkcjonalnie zakończony i zaakceptowany w testach ręcznych na Windowsie.

Gałąź robocza:

```text
agent/log-search-stage1
```

Surowe logi i format sesji nie zostały zmienione. Wszystkie indeksy są odtwarzalnymi danymi pochodnymi.

## Cel

Etap 4 usuwa konieczność ponownego przygotowywania danych wyszukiwarki po każdym uruchomieniu CAN Research Tool. Rozwiązanie rozróżnia trzy rodzaje źródeł:

1. trwały indeks surowych ramek projektu,
2. istniejący trwały cache wiadomości logicznych,
3. indeks pamięciowy dla widoków tymczasowych i Live Capture.

## Źródła wyszukiwania

### Surowe ramki zapisanej sesji

Indeks jest przechowywany per projekt:

```text
<projekt>/.crt/indexes/search-v1.sqlite
```

Surowa sesja `*.crt.jsonl` pozostaje źródłem prawdy.

### Wiadomości logiczne

Wyszukiwarka korzysta bezpośrednio z istniejącego cache:

```text
<nazwa-sesji>.logical.sqlite
```

Nie jest tworzony drugi indeks wiadomości logicznych w RAM. Dzięki temu ponowne otwarcie aplikacji nie uruchamia kolejnego przygotowania tabeli logicznej.

### Widoki nietrwałe

Indeks pamięciowy pozostaje używany dla:

- Live Capture,
- ograniczonego bufora podglądu,
- modeli proxy i wybranych widoków filtrowanych,
- tabel, które nie mają własnego trwałego źródła SQLite.

Indeks pamięciowy jest tworzony leniwie dopiero po użyciu wyszukiwarki dla danego modelu.

## Cykl życia

### Start aplikacji i otwarcie projektu

- brak globalnego skanowania `QTableView`,
- brak automatycznego indeksowania wszystkich tabel,
- gotowe indeksy SQLite są tylko rozpoznawane i ponownie używane,
- otwarcie zapisanej sesji ładuje maksymalnie stronę 20 000 ramek, a nie cały log.

### Import logu lub zapis logu Live

Po finalizacji nowej sesji może rozpocząć się przygotowanie indeksu surowych ramek wyłącznie dla tej sesji. Postęp jest prezentowany w dolnym pasku aplikacji.

### Pierwsze wyszukiwanie w starej sesji bez indeksu

Indeks jest budowany poza wątkiem GUI. Po zakończeniu oczekujące wyszukiwanie może zostać wykonane na gotowym źródle.

### Kolejne uruchomienie projektu

Gotowy i zgodny indeks jest używany bez przebudowy. Adapter GUI ponownie sprawdza stan SQLite bezpośrednio przed ewentualnym uruchomieniem workera, co zabezpiecza przed nieaktualnym stanem obiektu UI.

## Fingerprint źródła

Stan indeksu surowych ramek zależy od:

- stabilnego identyfikatora sesji z `project.sqlite`,
- ścieżki względnej sesji,
- SHA-256 zapisanej w rekordzie sesji,
- rozmiaru pliku,
- liczby ramek,
- wersji schematu indeksu.

Zmiana samego `mtime` nie powoduje automatycznej przebudowy. CRT weryfikuje wtedy rzeczywistą zawartość pliku względem SHA-256. Jeśli dane są identyczne, aktualizuje wyłącznie metadane czasu.

## Stabilna identyfikacja rekordów

Źródło surowej sesji ma identyfikator:

```text
session:<session_id>:raw:v1
```

Rekord ramki jest identyfikowany stabilną sekwencją. Numer źródłowego wiersza jest przechowywany osobno i służy do nawigacji.

## Budowanie i wznawianie

- odczyt sesji odbywa się poza wątkiem GUI,
- dane są zatwierdzane transakcyjnie partiami po 1000 ramek,
- `indexed_rows` jest zapisywane po każdej partii,
- przerwana budowa ma stan `pending`,
- następna próba wznawia pracę od ostatniej zatwierdzonej ramki,
- niespójna liczba dokumentów powoduje bezpieczną odbudowę danego źródła,
- błąd ma stan `failed` i jest raportowany w UI.

SQLite pracuje w trybie WAL.

## Wykonywanie zapytań

`QueryEngine` obsługuje zarówno dokumenty pamięciowe, jak i źródła wykonujące zapytanie bez materializowania pełnej zawartości w RAM.

### Surowy indeks projektu

Dla trybów `contains`, `exact`, `prefix` i `suffix` SQLite wykonuje wstępną selekcję kandydatów. Kandydaci są weryfikowani przez wspólny `CompiledSearchQuery`.

Regex, wildcard i wyszukiwanie case-sensitive wykonują strumieniowy skan SQLite bez ładowania całej sesji do pamięci.

### Cache wiadomości logicznych

Zapytanie odczytuje rekordy bezpośrednio z `.logical.sqlite`. Uwzględnia aktualny zestaw widocznych identyfikatorów, jeśli użytkownik zastosował filtr wiadomości logicznych.

## Stronicowanie zapisanych sesji

Widok surowych ramek zapisanej sesji używa strony o maksymalnym rozmiarze:

```text
20 000 ramek
```

Pełny log pozostaje na dysku, a wyszukiwanie obejmuje całą sesję przez SQLite. Otwarcie zakładki nie może ponownie wczytywać setek tysięcy ramek do modelu GUI.

## Lifecycle SQLite na Windowsie

Połączenia kontekstowe są tworzone przez jawny helper:

```text
app/sqlite_connection.py
```

Wyjście z `with` zatwierdza lub wycofuje transakcję oraz zamyka uchwyt pliku. Usunięto wcześniejszy import-time monkey patch i moduł `app/sqlite_lifecycle.py`.

Polityka fingerprintu znajduje się bezpośrednio w `ProjectSearchIndex`, a `app/__init__.py` nie wykonuje efektów ubocznych.

## Usuwanie

Usunięcie sesji usuwa jej rekordy z trwałego indeksu surowych ramek. Awaria cache nie może zablokować usunięcia źródłowej sesji, ponieważ cache jest odtwarzalny.

## Pasek przygotowania projektu

Dolny pasek:

- jest ukryty, gdy nie trwa żadne zadanie,
- pokazuje aktywny etap i postęp,
- obsługuje kilka rzeczywistych zadań,
- nie pojawia się dla gotowego indeksu surowych ramek ani gotowego `.logical.sqlite`.

## Walidacja

Testy jednostkowe i smoke obejmują:

- semantykę `QueryEngine`,
- trwałość indeksu po ponownym otwarciu projektu,
- wznowienie przerwanej budowy,
- zmianę `mtime` bez zmiany zawartości,
- unieważnienie indeksu po realnej zmianie danych,
- usuwanie indeksu razem z sesją,
- zwalnianie uchwytów SQLite na Windowsie,
- brak import-time monkey patcha,
- bezpośrednie wyszukiwanie w `.logical.sqlite`,
- brak tworzenia indeksu RAM dla tabeli wiadomości logicznych,
- wirtualny model wyników wyszukiwania.

Powiązane testy:

```text
tests/test_search_engine.py
tests/test_project_search_index.py
tests/test_sqlite_architecture.py
tests_gui/persistent_search_index_smoke.py
tests_gui/logical_search_cache_smoke.py
tests_gui/log_search_smoke.py
tests_gui/project_preparation_progress_smoke.py
```

Testy zostały dodane do workflow `.github/workflows/gui-regression.yml`. Końcowy pełny przebieg GitHub Actions powinien zostać potwierdzony przed scaleniem gałęzi.

## Zachowane kontrakty

Etap 4 nie zmienia:

- `CaptureService`,
- backendu Kvaser,
- lifecycle CANlib,
- formatu `*.crt.jsonl`,
- pełnego zapisu surowych ramek,
- kolejności zapisu ramek,
- formatu sesji projektu,
- semantyki istniejących filtrów.

## Pozostały temat

Wynik wyszukiwania surowych ramek może wskazywać rekord poza aktualnie załadowaną stroną. Następny etap powinien dodać nawigację:

```text
wynik wyszukiwania
→ obliczenie strony sesji
→ załadowanie strony przez kontroler
→ zaznaczenie źródłowej ramki
```

Nie należy ponownie zwiększać pojemności modelu do pełnej liczby ramek.