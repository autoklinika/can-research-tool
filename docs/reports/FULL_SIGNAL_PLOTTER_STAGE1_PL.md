# Full Signal Plotter Stage 1 — raport

## Cel

Dodać do CRT pełny, pasywny wykres jednego arbitralnego bitfield z zapisanej sesji, z dwoma dokładnymi kursorami A/B oraz nawigacją do źródłowych ramek RAW.

## Kontrakt evidence-first

- RAW zapisanej sesji pozostaje niezmienny.
- Analiza dotyczy jednego dokładnego klucza CAN: channel + arbitration ID + STD/EXT + frame kind.
- Pole ma start bit, długość 1–64, Intel/Motorola, signed, scale i offset.
- Artefakt `signal_plot_series` zawiera każdy poprawnie odczytany punkt aż do jawnego limitu bezpieczeństwa.
- `series_contract.complete=true`.
- `series_contract.sampling=none`.
- Każdy punkt zachowuje exact `source_row`, sequence i timestamp.
- Przekroczenie limitu bezpieczeństwa przerywa analizę bez zapisu częściowego artefaktu.

## Rendering

Pełna seria jest source-of-truth dla kursora. GUI może deterministycznie zredukować wyłącznie polilinię używaną przez QPainter, zachowując endpointy i lokalne extrema koszyków.

Redukcja renderingu:

- nie modyfikuje artefaktu,
- nie zmienia listy pełnych punktów,
- nie jest używana do wyboru kursora,
- nie wpływa na `source_row`.

## Kursory A/B

Kliknięcie wykresu:

1. mapuje pozycję X na timestamp,
2. wyszukuje najbliższy rzeczywisty punkt w pełnej serii,
3. zapisuje indeks tego punktu jako A albo B,
4. pokazuje timestamp, value, raw i exact source_row.

Dla dwóch kursorów CRT pokazuje:

- `Δt(B-A)` w ns i s,
- `Δvalue(B-A)`.

Przyciski `Otwórz A w RAW` i `Otwórz B w RAW` używają istniejącego StoredSearchNavigator i exact source_row.

## GUI

Nowa karta `Signal Plotter` jest dodawana do produkcyjnego widoku zapisanej sesji przez cienką warstwę `MinimalAnalysisChromeSessionViewWidget`.

Stage 1 nie zmienia istniejącego Signal Discovery. Ma osobny provider, service, artefakt i widok.

## Architektura

- `app/extensions/builtin/signal_plot_series.py` — deterministyczny provider pełnej serii,
- `app/signal_plot_service.py` — dedykowany passive registry, odczyt artefaktu, cursor helpers i render decimation,
- `gui/signal_plotter_view.py` — konfiguracja pola, background task, plot i kursory A/B,
- `gui/minimal_analysis_chrome.py` — cienka integracja produkcyjnej zakładki,
- `app/help_catalog_signal_plotter.py` — Help Center,
- `tests/test_signal_plotter.py` — core contract,
- `tests_gui/signal_plotter_smoke.py` — produkcyjny GUI smoke,
- `.github/workflows/full-signal-plotter-stage1.yml` — Windows-only validation.

## Granice Stage 1

Nie obejmuje jeszcze:

- zoom/pan,
- wielu sygnałów/tracks jednocześnie,
- nakładania markerów na wykres,
- porównania dwóch sesji na jednym wykresie,
- exportu obrazu/CSV z zaznaczonego zakresu,
- automatycznego tworzenia DBC,
- AI,
- CAN TX.

## Walidacja

Dedykowany Windows workflow sprawdza:

- pełną serię bez sampling,
- exact source_row,
- scale/offset,
- brak częściowego artefaktu po przekroczeniu limitu,
- brak wymyślania wartości przy niepełnym DLC,
- nearest exact cursor point,
- Δt/Δvalue,
- render-only decimation,
- produkcyjną kartę Signal Plotter,
- exact evidence navigation do RAW,
- SHA źródłowej sesji bez zmian,
- regresję Signal Discovery,
- regresję minimal analysis chrome.

Normalna walidacja tego etapu jest wykonywana na Windows. Legacy Ubuntu nie jest wymagane.
