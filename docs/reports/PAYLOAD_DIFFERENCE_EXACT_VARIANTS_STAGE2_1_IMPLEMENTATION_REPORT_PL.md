# Payload Difference Provider — Stage 2.1

## Cel

Usunąć domyślne ograniczenie do 1000 unikalnych wariantów payloadu na klucz wiadomości bez wprowadzania nieograniczonego słownika w pamięci RAM.

Stage 2.1 pozostaje osobnym, wąskim rozszerzeniem Stage 2. Nie zmienia formatu sesji, surowych ramek ani kontraktów warstwy CAN.

## Wersje

- provider: `crt.comparison.payload_differences`
- wersja providera: `1.1.0`
- wersja algorytmu: `2`
- schemat artefaktu: `crt.payload_differences` v1
- artefakt: `payload-differences.json`

## Nowy mechanizm przechowywania wariantów

Analiza nadal czyta wszystkie niezmienne sesje strumieniowo.

Dla każdego klucza wiadomości provider:

1. przechowuje początkowe warianty w RAM,
2. po przekroczeniu progu przenosi kompletny licznik tego klucza do tymczasowej bazy SQLite,
3. wszystkie kolejne wystąpienia aktualizuje dokładnie w SQLite,
4. zachowuje count, pierwszy timestamp i ostatni timestamp każdego wariantu,
5. nie pomija żadnego wariantu.

Domyślny próg wynosi 1000 wariantów. Parametr `max_variants_per_message` zachowano dla zgodności wejścia, ale od algorytmu 2 oznacza on próg przejścia RAM → SQLite, a nie limit analizy.

## Izolacja danych tymczasowych

Baza robocza:

- jest tworzona przez `tempfile.TemporaryDirectory`,
- znajduje się poza katalogiem projektu,
- nie korzysta z `.crt/project.sqlite`,
- nie zmienia schematu projektu,
- jest zamykana przed zapisem artefaktu,
- jest usuwana przy sukcesie, anulowaniu i wyjątku.

## Semantyka artefaktu

Dla dokładnego trybu Stage 2.1:

- `selection_rule = all_variants_exact`,
- `variant_tracking_complete = true`,
- `messages_with_truncated_variants = 0`,
- `untracked_variant_frame_count = 0`,
- `configured_limit = null`,
- `memory_threshold` opisuje wyłącznie próg spill,
- `storage_mode` ma wartość `memory` lub `sqlite` dla konkretnego profilu.

Dodano sekcję `variant_storage` z informacją o trybie, progu pamięciowym i liczbie kluczy przeniesionych do SQLite.

Provider nie emituje już `variant_comparison_truncated` w algorytmie 2. Różnice `new_payload_variant` i `missing_payload_variant` są wyliczane dla pełnego zbioru wariantów.

## Przywrócenie edycji i usuwania zestawów porównawczych

Ręczna walidacja ujawniła, że po pierwszym uruchomieniu analizy GUI wyłączało przyciski `Edytuj…` i `Usuń zestaw`. Nie była to przypadkowa regresja Stage 2.1, lecz pierwotna blokada wprowadzona w Comparison Sets Stage 1 dla zachowania powtarzalności wyników.

Blokadę zastąpiono wersjonowaniem i bezpiecznym usuwaniem:

- zestaw bez analiz jest nadal edytowany w miejscu,
- zestaw bez analiz jest nadal fizycznie usuwany,
- edycja zestawu z analizami tworzy nowy aktywny zestaw z nowym ID,
- stara definicja pozostaje niezmiennym źródłem historycznych analiz,
- stara definicja jest ukrywana z aktywnego widoku przez znacznik w istniejącym `parameters_json`,
- usunięcie zestawu z analizami ukrywa definicję, lecz zachowuje analizę, artefakty i powiązania z sesjami,
- nie dodano migracji ani nowej kolumny w `.crt/project.sqlite`.

Stan w tabeli zmieniono z mylącego `Zablokowany` na `Z analizami`. Przyciski pozostają aktywne, a opis wyjaśnia semantykę tworzenia nowej wersji i zachowania historii.

## Walidacja dodana do repozytorium

- test deterministyczności i identycznego SHA-256,
- test jawnego progu spill ustawionego na 1,
- test ponad 1000 unikalnych wariantów na klucz i sesję,
- test dokładnego wykrycia nowego oraz brakującego wariantu po spill,
- test kompletnej macierzy wariantów,
- test usunięcia tymczasowej bazy po anulowaniu,
- zachowanie testu błędnego parametru,
- test edycji analizowanego zestawu przez utworzenie nowej wersji,
- test bezpiecznego usunięcia analizowanego zestawu bez usuwania historii,
- smoke GUI obejmujący aktywne przyciski po analizie, wersjonowaną edycję i usunięcie,
- nowy test został dodany do workflow GUI Regressions; pełny Windows CI uruchamia cały pytest.

Izolowany test magazynu SQLite wykonany poza repozytorium potwierdził poprawne zliczanie, timestampy, przejście do SQLite i usunięcie katalogu tymczasowego.

## Nienaruszone kontrakty

Bez zmian pozostają:

- `CaptureService`,
- Kvaser i lifecycle CANlib,
- CAN TX/RX,
- format sesji,
- kolejność i kompletność zapisu surowych ramek,
- trwałe indeksy wyszukiwania,
- schemat `.crt/project.sqlite`,
- Project Properties i Project Catalog,
- provider statystyk Stage 1,
- ID oraz schemat artefaktu Stage 2.

## Znane ograniczenie techniczne

Faza zliczania wariantów jest adaptacyjna i ogranicza wzrost słownika RAM. Końcowy artefakt JSON oraz kompletna macierz wariantów są nadal materializowane przez istniejący kontrakt `ArtifactWriter.write_json`.

Przy ekstremalnej liczbie unikalnych payloadów sam wynik może więc być bardzo duży. To nie powoduje utraty danych, ale może zwiększyć czas i szczytowe zużycie pamięci podczas budowania oraz serializacji artefaktu. Ewentualny strumieniowy writer artefaktów albo osobny artefakt SQLite wymaga oddzielnego projektu kontraktu i nie powinien być dokładany do Stage 2.1 bez szerszej decyzji architektonicznej.

## Status

Implementacja i testy zostały zapisane na osobnej gałęzi stacked na Stage 2. Aktualny HEAD obejmuje także naprawę edycji i usuwania zestawów analizowanych. GitHub Actions dla tego HEAD zostały uruchomione; pełny pytest, Linux GUI CI i Windows GitHub-hosted CI pozostają do końcowego potwierdzenia.
