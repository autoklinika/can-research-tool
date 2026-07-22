# Handoff — Payload Difference Exact Variants Stage 2.1

## Repozytorium

`autoklinika/can-research-tool`

## Gałąź robocza

`agent/payload-difference-exact-variants-stage2-1`

Gałąź jest stacked na:

- `agent/payload-difference-provider-stage2`,
- draft PR #46,
- bazowym HEAD `5d76aa74d2d7500f66e2a2c3bad383b3ba6228fb`.

Przed kolejnymi zmianami sprawdź aktualny HEAD, draft PR Stage 2.1, stacked PR #45 i #46, diff, review threads oraz GitHub Actions.

Nie oznaczaj PR jako ready i nie wykonuj merge bez wyraźnego polecenia użytkownika.

## Co wykonano

Stage 2.1 usuwa domyślne ograniczenie liczby porównywanych wariantów payloadu.

Provider:

- ID `crt.comparison.payload_differences`,
- wersja `1.1.0`,
- algorytm `2`,
- schemat `crt.payload_differences` v1.

Domyślnie każdy wariant jest zliczany dokładnie. Próg 1000 oznacza teraz wyłącznie przejście z RAM do tymczasowej bazy SQLite.

## Mechanizm

- początkowe warianty klucza są trzymane w RAM,
- po przekroczeniu progu cały klucz jest przenoszony do run-scoped SQLite,
- późniejsze wystąpienia są aktualizowane przez UPSERT,
- zachowane są count oraz pierwszy i ostatni timestamp,
- wszystkie warianty trafiają do porównania i macierzy obecności,
- nie powstaje `variant_comparison_truncated`,
- `new_payload_variant` i `missing_payload_variant` są dokładne.

## Dane tymczasowe

Tymczasowa baza:

- jest poza projektem,
- nie zmienia `.crt/project.sqlite`,
- jest zamykana przed zapisem artefaktu,
- jest usuwana po sukcesie, anulowaniu i wyjątku.

## Pliki kluczowe

- `app/extensions/builtin/payload_difference_exact.py`
- `app/extensions/builtin/__init__.py`
- `tests/test_payload_difference_provider.py`
- `tests/test_payload_difference_exact_storage.py`
- `.github/workflows/gui-regression.yml`
- `docs/reports/PAYLOAD_DIFFERENCE_EXACT_VARIANTS_STAGE2_1_IMPLEMENTATION_REPORT_PL.md`

## Walidacja do wykonania

1. Sprawdź HEAD i bazę draft PR Stage 2.1.
2. Sprawdź, czy diff względem Stage 2 zawiera tylko pliki Stage 2.1.
3. Sprawdź review threads i submitted reviews.
4. Sprawdź Linux `GUI Regressions`.
5. Sprawdź pełny `Tests`.
6. Sprawdź Windows GitHub-hosted CI.
7. Windows Self-Hosted CI nie jest wymagany dla tego pasywnego etapu bez sprzętu.
8. W przypadku błędu odczytaj dokładny log przed zmianą kodu.
9. Potwierdź deterministyczność i identyczne SHA-256 dwóch artefaktów.
10. Potwierdź test ponad 1000 wariantów.
11. Potwierdź cleanup SQLite po anulowaniu na Windows.
12. Uruchom ręcznie `tests_gui/payload_difference_smoke.py`.

## Szczególnie ważne przypadki

- parametr `max_variants_per_message` oznacza próg spill, nie limit,
- `configured_limit` ma pozostać `null`,
- `memory_threshold` ma być jawny,
- wszystkie dokładne profile mają `complete=true`,
- `untracked_variant_frame_count` ma wynosić zero,
- różne długości payloadu nie mogą być dopełniane zerami,
- sesje i ich SHA-256 muszą pozostać niezmienione,
- baza tymczasowa nie może pozostać po anulowaniu,
- provider nie tworzy automatycznych findings.

## Znane ograniczenie

Zliczanie jest hybrydowe RAM/SQLite, lecz końcowy JSON i pełna macierz wariantów są materializowane przez istniejący `ArtifactWriter.write_json`. Ekstremalnie duży wynik może więc zużywać dużo pamięci podczas końcowej serializacji, mimo że żaden wariant nie jest pomijany.

Nie rozszerzaj Stage 2.1 o nowy streaming writer albo trwały artefakt SQLite bez osobnej decyzji architektonicznej.

## Nienaruszalne kontrakty

Nie zmieniaj:

- `CaptureService`,
- Kvasera i lifecycle CANlib,
- CAN TX/RX,
- formatu sesji,
- kolejności i kompletności pełnego zapisu surowych ramek,
- trwałych indeksów wyszukiwania,
- schematu `.crt/project.sqlite`,
- Project Properties i Project Catalog.

## Następny etap

Po zielonym CI i ręcznej akceptacji Stage 2.1 można rozpocząć osobny Message Sequence Comparison Provider Stage 3.
