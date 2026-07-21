# Wyszukiwanie — Etap 4: trwały indeks projektu

## Cel

Etap 4 usuwa konieczność ponownego przygotowywania indeksu surowych ramek po każdym uruchomieniu CAN Research Tool. Indeks jest odtwarzalnym cache projektu i nie zmienia formatu ani kolejności zapisu źródłowych ramek CAN.

## Lokalizacja

Indeks jest przechowywany w projekcie:

```text
<projekt>/.crt/indexes/search-v1.sqlite
```

Surowa sesja `*.crt.jsonl` pozostaje źródłem prawdy.

## Cykl życia

### Start aplikacji i otwarcie projektu

- brak automatycznego skanowania tabel,
- brak automatycznej przebudowy indeksów,
- brak obciążenia wynikającego z wyszukiwarki.

### Import logu lub zapis logu Live

Po bezpiecznym zapisaniu i finalizacji sesji uruchamiane jest przygotowanie indeksu tylko dla nowej sesji. Postęp jest wyświetlany w dolnym pasku aplikacji jako etap `1/4 Indeks wyszukiwania`.

### Pierwsze wyszukiwanie w starej sesji bez indeksu

Indeks jest budowany w workerze. Po zakończeniu oczekujące wyszukiwanie uruchamia się automatycznie.

### Kolejne uruchomienie projektu

Fingerprint sesji jest porównywany z metadanymi zapisanymi w SQLite. Aktualny indeks jest używany bez przebudowy.

## Fingerprint źródła

Stan indeksu zależy od:

- stabilnego identyfikatora sesji z `project.sqlite`,
- ścieżki względnej sesji,
- SHA-256 zapisanej w rekordzie sesji,
- rozmiaru pliku,
- czasu modyfikacji pliku,
- liczby ramek,
- wersji schematu indeksu.

Zmiana któregokolwiek elementu unieważnia tylko indeks danej sesji.

## Stabilna identyfikacja rekordów

Źródło indeksu ma identyfikator:

```text
session:<session_id>:raw:v1
```

Rekord ramki jest identyfikowany przez jej stabilną sekwencję wewnątrz źródła. Numer wiersza jest przechowywany oddzielnie i służy do nawigacji w pełnym, nieprzefiltrowanym widoku sesji.

## Budowanie i wznawianie

- odczyt sesji odbywa się poza wątkiem GUI,
- dane są zatwierdzane transakcyjnie partiami po 1000 ramek,
- stan `indexed_rows` jest zapisywany po każdej partii,
- przerwana budowa ma stan `pending`,
- następna próba wznawia pracę od ostatniej zatwierdzonej ramki,
- błąd ma stan `failed` i jest raportowany na pasku przygotowania projektu.

SQLite pracuje w trybie WAL.

## Wykonywanie zapytań

`QueryEngine` obsługuje dwa typy źródeł:

1. indeks pamięciowy dla Live, filtrów i pozostałych tabel,
2. trwałe źródło SQLite dla pełnych zapisanych sesji.

Dla podstawowych trybów (`contains`, `exact`, `prefix`, `suffix`) SQLite wykonuje wstępną selekcję kandydatów. Kandydaci są następnie weryfikowani przez ten sam `CompiledSearchQuery`, co zachowuje zgodność semantyczną z wyszukiwaniem pamięciowym.

Regex, wildcard i wyszukiwanie case-sensitive korzystają z pełnego strumieniowego skanu SQLite, ale dokumenty nie są ładowane jednocześnie do RAM.

## Bezpieczny fallback

Trwały indeks jest używany tylko wtedy, gdy:

- tabela przedstawia surowe ramki zapisanej sesji,
- sesja nie ma stanu `recording`,
- widok zawiera pełną liczbę ramek sesji.

Live Capture, widoki przefiltrowane, wiadomości logiczne i inne tabele nadal korzystają z indeksu pamięciowego. Zapobiega to błędnemu mapowaniu wyników do wierszy proxy lub ograniczonego bufora.

## Usuwanie

Usunięcie sesji usuwa również jej rekordy z trwałego indeksu. Awaria usuwania cache nie blokuje usunięcia właściwej sesji, ponieważ cache jest w pełni odtwarzalny.

## Ograniczenia Etapu 4

Etap 4 indeksuje surowe ramki CAN. Trwałe adnotacje protokołów, wiadomości logiczne, UDS/J1939/ISO-TP i wartości DBC należą do następnego etapu przygotowania sesji. Ich zmiany nie unieważniają surowego indeksu wyszukiwania.
