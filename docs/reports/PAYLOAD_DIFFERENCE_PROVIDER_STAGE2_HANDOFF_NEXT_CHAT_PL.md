# Handoff — Payload Difference Provider Stage 2

## Repozytorium

`autoklinika/can-research-tool`

## Gałąź robocza

`agent/payload-difference-provider-stage2`

Gałąź jest stacked na:

- `agent/comparison-statistics-provider-stage1`,
- draft PR #45,
- commit bazowy `12524adb8bbdd7286efaec3152584c5388b5a74c`.

Przed wykonaniem kolejnych zmian sprawdź aktualny HEAD gałęzi, draft PR Stage 2, status stacked PR #45, diff, review threads i GitHub Actions.

Nie oznaczaj żadnego PR jako ready i nie wykonuj merge bez wyraźnego polecenia użytkownika.

## Co zostało wykonane

Dodano drugi deterministyczny provider typu `COMPARISON`:

- ID `crt.comparison.payload_differences`,
- output `payload_differences`,
- artefakt `payload-differences.json`,
- schemat `crt.payload_differences` v1,
- wersja providera `1.0.0`,
- wersja algorytmu `1`.

Provider porównuje:

- pełne warianty payloadu,
- rzeczywiste długości danych,
- liczbę i udział wariantu,
- pierwszy i ostatni timestamp wariantu,
- klasyfikację pozycji bajtowej `absent/constant/variable`,
- minimum, maksimum i dominantę,
- histogram wartości bajtu,
- nowe i brakujące wartości,
- przejścia stały/zmienny,
- zmiany dominanty,
- zmianę DLC,
- obecność wariantów między wieloma sesjami.

## Macierz wariantów

Dla śledzonych payloadów tworzona jest macierz z rolą:

- `common`,
- `baseline_only`,
- `comparison_only`,
- `subset_only`,
- `incomplete`.

`incomplete` oznacza, że co najmniej jedna sesja przekroczyła limit wariantów i nie wolno interpretować braku śledzonego payloadu jako dowodu jego nieobecności.

## Kontrola pamięci

Analiza jest strumieniowa.

Domyślny limit:

`max_variants_per_message = 1000`

Po przekroczeniu limitu provider:

- liczy pominięte wystąpienia,
- zapisuje `complete=false`,
- zapisuje regułę `first_observed_in_session_order`,
- emituje `variant_comparison_truncated`,
- nie emituje nowych ani brakujących wariantów dla niepełnego porównania.

Nie zastępuj tej reguły nieograniczonym słownikiem payloadów. Ewentualny dokładny top-frequency wymaga osobnego projektu algorytmu lub drugiego przebiegu po źródle.

## GUI

Wspólny dialog analiz zestawu obsługuje teraz dwa schematy:

- `crt.comparison_statistics`,
- `crt.payload_differences`.

Dla payloadów pokazuje:

- podsumowanie sesji,
- liczbę kluczy i wariantów,
- liczbę bajtów stałych i zmiennych,
- ranking różnic,
- opis bajtu bazowego i bieżącego,
- payload, DLC i informację o truncation.

Worker, progres, anulowanie i blokada zamknięcia dialogu pozostają wspólne ze Stage 1.

## Pliki kluczowe

- `app/extensions/builtin/payload_difference.py`
- `app/extensions/builtin/__init__.py`
- `app/extensions/__init__.py`
- `gui/comparison_analysis_dialog.py`
- `tests/test_payload_difference_provider.py`
- `tests/test_comparison_statistics_provider.py`
- `tests_gui/payload_difference_smoke.py`
- `tests_gui/comparison_statistics_smoke.py`
- `.github/workflows/gui-regression.yml`
- `.github/workflows/windows-github-hosted-ci.yml`

Pełny opis:

`docs/reports/PAYLOAD_DIFFERENCE_PROVIDER_STAGE2_IMPLEMENTATION_REPORT_PL.md`

Plan wejściowy:

`docs/reports/PAYLOAD_DIFFERENCE_PROVIDER_STAGE2_PLAN_PL.md`

## Walidacja do wykonania

1. Sprawdź aktualny HEAD i bazę draft PR Stage 2.
2. Sprawdź, czy diff zawiera wyłącznie pliki Stage 2 i świadome regresje Stage 1.
3. Sprawdź wszystkie review threads i submitted reviews.
4. Sprawdź GitHub-hosted workflowy dla aktualnego HEAD.
5. Jeżeli CI nie jest zielone, odczytaj dokładny job i log przed zmianą kodu.
6. Zweryfikuj test deterministyczności i identyczne SHA-256 dwóch artefaktów.
7. Zweryfikuj Windows teardown dialogu oraz brak otwartego `project.sqlite`.
8. Wykonaj ręczną listę akceptacyjną z raportu implementacyjnego.
9. Nie traktuj Windows Self-Hosted CI jako wymaganego dla tego pasywnego etapu bez Kvasera i hardware.

## Szczególnie ważne przypadki

- różne długości payloadu nie mogą być dopełniane zerami,
- kanał oraz flagi STD/EXT/RTR/error pozostają częścią klucza,
- payloady RTR i error nie mogą otrzymać sztucznych danych,
- limit wariantów musi pozostać jawny,
- przy niepełnym śledzeniu nie wolno generować fałszywych `new/missing`,
- kolejność wyniku musi być deterministyczna,
- sesje i ich SHA-256 muszą pozostać niezmienione,
- provider nie tworzy automatycznych findings.

## Nienaruszalne kontrakty

Nie zmieniaj:

- `CaptureService`,
- Kvasera i lifecycle CANlib,
- CAN TX/RX,
- formatu sesji,
- kompletności i kolejności pełnego zapisu surowych ramek,
- trwałych indeksów wyszukiwania,
- schematu `.crt/project.sqlite`,
- kontraktów Project Properties i Project Catalog,
- artefaktów Stage 1.

Surowe ramki i pliki sesji pozostają niezmiennym źródłem prawdy.

## Następny proponowany etap

Po zielonym CI i ręcznej akceptacji Stage 2 wybierz osobny, wąski provider:

- porównanie sekwencji wiadomości,
- porównanie protokołów J1939/UDS,
- albo korelację ze znacznikami po zaprojektowaniu jawnego kontraktu synchronizacji.

Nie łącz tych obszarów z bieżącym providerem payloadów.
