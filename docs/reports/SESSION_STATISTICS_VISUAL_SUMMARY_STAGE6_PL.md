# Stage 6 — lekkie graficzne podsumowanie statystyk

## Cel

Rozbudować zaakceptowany ręcznie widok statystyk zapisanej sesji o lekką warstwę graficzną, która przyspiesza ocenę logu bez zamiany zakładki `Analizy` w przeładowany dashboard.

Stage 6 jest zbudowany na checkpointcie Stage 5:

- gałąź bazowa: `agent/session-statistics-table-stage5`,
- bazowy HEAD: `ee062e5531c3cd7d7c9d3f86ad869d16cb224bf1`,
- ręczna walidacja Stage 5: potwierdzona,
- techniczny model tabeli i artefakt pozostają bez zmian.

## Założenia wizualne

Zachowany zostaje zaakceptowany podział ekranu:

- lista artefaktów po lewej,
- interpretacja wybranego artefaktu po prawej,
- karty `Podsumowanie` i `Statystyki CAN ID`.

Warstwa graficzna ma charakter pomocniczy. Twarde dane, sortowanie, filtry i techniczne podsumowanie pozostają podstawą widoku.

## Zakres Stage 6

### Kafle KPI

W górnej części karty `Podsumowanie` dodano pięć zwartych kafli:

- liczba ramek,
- liczba unikalnych CAN ID,
- czas sesji,
- średnia częstotliwość dodatnich interwałów,
- anomalie timestampów.

Kafel anomalii pokazuje dodatkowo liczbę zerowych i ujemnych różnic czasu.

### Najaktywniejsze CAN ID

Pod KPI znajduje się lista maksymalnie pięciu najaktywniejszych kluczy wiadomości, sortowana według liczby ramek.

Dla każdego wiersza prezentowane są:

- CAN ID,
- kanał,
- typ ramki,
- format STD/EXT,
- liczba ramek,
- udział procentowy,
- częstotliwość.

Udział jest przedstawiony przez niewielki pasek `QProgressBar`. Lista ma stałą, ograniczoną wysokość i nie wypiera szczegółów technicznych.

### Mini-paski udziału w tabeli

Kolumna `Udział [%]` w istniejącej tabeli korzysta z `ShareBarDelegate`.

Delegate:

- zachowuje liczbową wartość,
- rysuje subtelny pasek za tekstem,
- korzysta z kolorów aktywnego motywu Qt,
- nie definiuje osobnej agresywnej palety,
- zachowuje prawidłowy wygląd zaznaczenia.

### Szczegóły techniczne

Dotychczasowe tekstowe podsumowanie artefaktu pozostaje w karcie `Podsumowanie`, poniżej KPI i listy Top CAN ID.

Nie usunięto informacji o:

- ID artefaktu,
- providerze,
- wersji algorytmu i schematu,
- SHA-256,
- źródłowej sesji,
- sumach i timingach.

## Architektura

Nowa warstwa znajduje się w:

```text
gui/session_statistics_visual_summary.py
```

`VisualSessionStatisticsViewWidget` rozszerza widok Stage 5 i nie modyfikuje:

- `SessionStatisticsProvider`,
- `SessionStatisticsTableModel`,
- schematu `crt.session_statistics`,
- `ArtifactCatalog`,
- bazy projektu,
- pliku sesji.

Wszystkie wartości są odczytywane wyłącznie z istniejącego, zweryfikowanego artefaktu JSON.

## Bezpieczeństwo danych

Stage 6 nie otwiera źródłowego `*.crt.jsonl` do zapisu i nie uruchamia ponownej analizy w GUI.

Zachowane pozostają:

- niezmienność SHA-256 sesji,
- atomowy zapis artefaktu z wcześniejszych etapów,
- read-only `ArtifactCatalog`,
- brak bezpośredniego dostępu GUI do CaptureService i CANlib.

## Testy

Dodano:

```text
tests_gui/session_statistics_visual_summary_smoke.py
```

Smoke sprawdza:

- pełny przepływ zapisanej sesji i analizy,
- obecność pięciu kafli KPI,
- poprawne wartości ramek, CAN ID, czasu, częstotliwości i anomalii,
- kolejność Top CAN ID,
- pasek udziału 50%,
- delegate kolumny `Udział [%]`,
- zachowanie tekstowego podsumowania,
- ponowne otwarcie gotowego artefaktu,
- identyczny SHA-256 sesji przed i po całym przepływie.

Test został dodany do:

- `GUI Regressions`,
- pełnego `Windows GitHub-Hosted CI`.

## Poza zakresem

Stage 6 nie dodaje:

- wykresów czasowych,
- wykresów kołowych,
- heatmap,
- osobnej karty pełnego dashboardu,
- ponownego liczenia statystyk w GUI,
- zmiany zakresu analizy,
- porównań sesji,
- nawigacji do ramek,
- findings, CAN Intelligence ani AI,
- CAN TX ani funkcji aktywnych.

## Walidacja ręczna

Po zielonej walidacji GitHub-hosted należy otworzyć rzeczywistą sesję i ocenić:

- czy KPI są czytelne przy typowej szerokości prawego panelu,
- czy Top 5 nie wypiera szczegółów technicznych,
- czy pasek udziału pomaga, ale nie dominuje tabeli,
- czy wygląd pozostaje spójny w motywie jasnym i ciemnym.
