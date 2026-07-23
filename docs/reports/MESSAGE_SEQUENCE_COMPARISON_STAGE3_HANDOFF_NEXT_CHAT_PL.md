# Handoff — Message Sequence Comparison Provider Stage 3

## Repozytorium

`autoklinika/can-research-tool`

## Gałąź

`agent/message-sequence-comparison-stage3`

Gałąź jest stackowana na:

- `agent/payload-difference-exact-variants-stage2-1`,
- draft PR #47,
- bazowym HEAD `30e12ed9ea707536d3a24e81834d7be3ef37b6f5`.

Przed zmianami sprawdź aktualny HEAD, diff, bazę PR, review threads i GitHub Actions. Nie oznaczaj PR jako ready i nie wykonuj merge bez wyraźnego polecenia użytkownika.

## Provider

- ID: `crt.comparison.message_sequences`
- wersja: `1.0.0`
- algorytm: `1`
- artefakt: `message-sequence-differences.json`
- typ: `message_sequence_differences`
- schemat: `crt.message_sequence_differences` v1

## Semantyka

Element sekwencji to pełny klucz wiadomości:

- kanał,
- CAN ID,
- STD/EXT,
- data/remote/error.

Analizowane są dokładnie:

- pary i trójki,
- tryb `raw`,
- tryb `collapsed`, który zwija kolejne identyczne klucze,
- samoprzejścia `A → A`,
- cykle `A → B → A`.

Domyślnie ramki remote i error są pomijane. Parametr `include_non_data_frames=true` włącza je do strumienia.

## Dokładność i pamięć

Provider używa ograniczonego bufora RAM oraz run-scoped SQLite.

- `memory_sequence_threshold` jest progiem opróżnienia bufora,
- nie jest limitem analizy,
- pełna macierz jest kompletna,
- `untracked_sequence_count = 0`,
- baza robocza jest poza projektem i jest usuwana po sukcesie, błędzie i anulowaniu.

`message_sequence_exact.py` jest providerem rejestrowanym w CRT. Zachowuje first/last timestamp według source order, również przy niemonotonicznym czasie.

## Porównanie

Względem efektywnej sesji bazowej wykrywane są:

- nowe sekwencje,
- brakujące sekwencje,
- zmiany liczby wystąpień,
- zmiany udziału,
- zmiany średniego czasu sekwencji.

Ranking może być ograniczony parametrem, lecz macierz pozostaje pełna.

## GUI

Rzeczywista aplikacja otwiera `MessageSequenceComparisonAnalysisDialog`, który zachowuje renderery Stage 1 i Stage 2.1 oraz dodaje renderer Stage 3.

W oknie analizy wybierz:

```text
CAN message sequence comparison
```

Widok obsługuje maksymalizację i `F11` przez wspólny kontroler okien.

## Pliki kluczowe

- `app/extensions/builtin/message_sequence.py`
- `app/extensions/builtin/message_sequence_exact.py`
- `app/extensions/builtin/__init__.py`
- `app/extensions/__init__.py`
- `gui/message_sequence_analysis_dialog.py`
- `gui/comparison_sets_analysis_view.py`
- `tests/test_message_sequence_provider.py`
- `tests/test_message_sequence_source_order.py`
- `tests_gui/message_sequence_comparison_smoke.py`
- `.github/workflows/gui-regression.yml`
- `docs/reports/MESSAGE_SEQUENCE_COMPARISON_STAGE3_PLAN_PL.md`
- `docs/reports/MESSAGE_SEQUENCE_COMPARISON_STAGE3_IMPLEMENTATION_REPORT_PL.md`

## Walidacja wymagana

1. Sprawdź diff względem HEAD Stage 2.1.
2. Potwierdź, że PR jest stackowany dokładnie na gałęzi Stage 2.1.
3. Sprawdź review threads i submitted reviews.
4. Sprawdź `Tests`.
5. Sprawdź `GUI Regressions`.
6. Sprawdź `Windows GitHub-Hosted CI`.
7. Sprawdź `Live Preview Capacity`.
8. Windows Self-Hosted CI raportuj osobno; Stage 3 jest pasywny i nie wymaga Kvasera.
9. W razie błędu odczytaj dokładny log przed zmianą kodu.
10. Potwierdź identyczny JSON i SHA-256 dwóch uruchomień.
11. Potwierdź dokładność przy `memory_sequence_threshold = 1`.
12. Potwierdź cleanup SQLite po anulowaniu.
13. Potwierdź source-order timestampy przy niemonotonicznym czasie.
14. Uruchom `tests_gui/message_sequence_comparison_smoke.py`.
15. Wykonaj ręczny test GUI na rzeczywistym projekcie.

## Ręczny test

```powershell
git fetch origin
git switch agent/message-sequence-comparison-stage3
git pull --ff-only

python -m pytest tests/test_message_sequence_provider.py tests/test_message_sequence_source_order.py -q
python tests_gui/message_sequence_comparison_smoke.py
python -m gui.main
```

W aplikacji:

1. otwórz projekt z co najmniej dwiema sesjami,
2. otwórz `Zestawy porównawcze`,
3. wybierz zestaw,
4. kliknij `Analizuj wybrany zestaw…`,
5. wybierz `CAN message sequence comparison`,
6. uruchom analizę,
7. sprawdź sesje, ranking, oznaczenia `[CYKL]` i `[POWTÓRZENIE]`.

## Granice

Stage 3 obsługuje tylko `synchronization_mode = none`.

Nie dodawaj do tego PR:

- synchronizacji markerami,
- J1939/UDS/ISO-TP sequence semantics,
- request/response pairing,
- sekwencji dłuższych niż trzy elementy,
- findings,
- automatycznego werdyktu naprawy ECU.

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

## Następny kierunek

Po zielonym CI i ręcznej akceptacji Stage 3 można zaprojektować osobny etap protokołowego porównania J1939/UDS albo synchronizacji markerowej. Nie łączyć obu kierunków w jeden PR.
