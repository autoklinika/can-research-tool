# Comparison Visualization Stage 2D1 — handoff do kolejnej rozmowy

## Repozytorium i gałąź

- repozytorium: `autoklinika/can-research-tool`,
- gałąź: `agent/comparison-visualization-stage2d1-uds-transaction-explorer`,
- baza stacked: `agent/comparison-visualization-stage2c2-uds-latency`,
  draft PR #53,
- PR Stage 2D1: draft PR #54.

Nie wykonywać merge ani nie oznaczać PR jako ready bez wyraźnego polecenia
właściciela.

## Funkcjonalny checkpoint

`74dceb37ddc4b9d0dba355b69df35ca264de1e97`

Późniejsze commity raportowe nie zmieniają kodu produkcyjnego.

## Dostarczony zakres

W produkcyjnym oknie `Porównanie logów` znajduje się karta `Transakcje UDS`,
która:

- wczytuje najnowszy zgodny artefakt Stage 2C2 bez skanowania surowych sesji,
- filtruje transakcje po sesji, SID, statusie, NRC, payloadzie, czasie i final
  latency,
- grupuje automatycznie albo według SID, DID, subfunkcji i Routine ID,
- pokazuje p50–p95 first/final latency,
- porównuje grupy pomiędzy sesją bazową i pozostałymi,
- pokazuje pełne szczegóły request/first/final response,
- eksportuje transakcje i grupy do CSV,
- przechodzi do dokładnych ramek źródłowych.

## Najważniejsze pliki

- `app/comparison_uds_transaction_explorer.py`,
- `gui/comparison_uds_transaction_explorer_view.py`,
- `gui/comparison_visualization_stage2d1.py`,
- `gui/comparison_sets_analysis_view.py`,
- `tests/test_comparison_uds_transaction_explorer.py`,
- `tests_gui/comparison_uds_transaction_explorer_smoke.py`,
- `.github/workflows/comparison-uds-transaction-explorer-stage2d1.yml`,
- `docs/reports/COMPARISON_VISUALIZATION_STAGE2D1_UDS_TRANSACTION_EXPLORER_PL.md`.

## Reguły, których nie wolno zgubić

1. Eksplorator nie skanuje ponownie surowych sesji.
2. Źródłem prawdy dla Stage 2D1 jest zgodny artefakt Stage 2C2.
3. Stage 2D1 nie zmienia parowania request/response.
4. Grupowanie zachowuje SID również dla DID, subfunkcji i Routine ID.
5. Filtrowanie i grupowanie pracują na bounded parach dowodowych.
6. Gdy Stage 2C2 oznacza `evidence_truncated`, GUI musi wyświetlić ostrzeżenie.
7. Dokładne globalne liczniki pozostają w karcie `Latencja UDS`.
8. Nawigacja używa dokładnego pierwszego `source_row` komunikatu logicznego.
9. Przebudowa filtrów musi czyścić selekcję przed wymianą modelu tabeli.
10. Eksport CSV ma używać UTF-8 BOM i separatora `;`.
11. Nie zmieniać formatu sesji, indeksów ani schematu projektu.

## Test ręczny na Windows

Test wymaga zestawu porównawczego z wcześniej utworzonym artefaktem Stage 2C2.
Najpierw należy potwierdzić, że karta `Latencja UDS` pokazuje transakcje dla
właściwych kluczy request/response.

Procedura:

1. Uruchom CRT z gałęzi Stage 2D1.
2. Otwórz projekt i zestaw porównawczy zawierający minimum dwie sesje UDS.
3. Kliknij `Analizuj wybrany zestaw…`.
4. W karcie `Latencja UDS` uruchom albo wczytaj analizę Stage 2C2.
5. Otwórz kartę `Transakcje UDS`.
6. Jeżeli artefakt został utworzony już po otwarciu dialogu, kliknij
   `Wczytaj najnowszy artefakt UDS`.
7. Potwierdź komunikat o wczytaniu bez ponownego skanowania surowych sesji.
8. Sprawdź tabelę transakcji i panel szczegółów.
9. Zmień `Grupowanie` kolejno na:
   - `SID usługi`,
   - `DID`,
   - `Subfunkcja`,
   - `Routine ID`.
10. Klikaj `Zastosuj filtry` i potwierdź aktualizację tabel grup oraz wykresu.
11. Ustaw filtr sesji albo SID i sprawdź, że liczba widocznych transakcji maleje.
12. W polu wyszukiwania wpisz fragment payloadu, np. `F1 90`, numer DID `F190`,
    nazwę usługi albo status.
13. Zaznacz transakcję z odpowiedzią i sprawdź panel szczegółów.
14. Dla transakcji z `0x78` uruchom kolejno:
    - `Otwórz żądanie`,
    - `Otwórz pierwszą odpowiedź`,
    - `Otwórz odpowiedź końcową`.
15. Potwierdź właściwą sesję oraz trzy dokładne ramki; first i final powinny być
    różne przy `0x78`.
16. Zastosuj kolejny filtr po wcześniejszym zaznaczeniu wiersza. Panel szczegółów
    powinien się wyczyścić, a po zaznaczeniu nowego wiersza pokazać nowe dane.
17. Wyeksportuj `Transakcje CSV` i `Grupy CSV`.
18. Otwórz pliki i potwierdź nagłówki, separator `;`, payloady oraz wartości
    szesnastkowe.
19. Zamknij dialog porównania i otwórz go ponownie.
20. Potwierdź automatyczne odtworzenie eksploratora bez skanowania sesji.

## Interpretacja wyników

- `Automatycznie` wybiera najbardziej szczegółowy bezpieczny klucz korelacji,
- wiersz grupy z liczbą `0` oznacza, że dana usługa wystąpiła w innej sesji, ale
  nie w tej konkretnej,
- wzrost p95 przy stabilnym p50 wskazuje pogorszenie najwolniejszych odpowiedzi,
- duża różnica first/final oznacza długie przetwarzanie po pierwszej reakcji ECU,
- filtr NRC pozwala oddzielić problemy protokołowe od wzrostu samej latencji,
- ostrzeżenie `evidence_truncated` oznacza, że grupy i eksport nie obejmują
  wszystkich transakcji sesji; dokładne globalne liczby należy odczytać w
  `Latencja UDS`,
- brak zgodnego artefaktu oznacza konieczność uruchomienia Stage 2C2, a nie błąd
  formatu sesji.

## Walidacja automatyczna

Funkcjonalny checkpoint przeszedł:

- Stage 2D1 Validation na Ubuntu i Windows,
- pełny pytest,
- Windows GitHub-hosted CI,
- GUI Regressions,
- dashboard porównań,
- Stage 2A timeline,
- Stage 2B persistent alignment,
- Stage 2C1 timing i jitter,
- Stage 2C2 latencję UDS,
- Live Preview Capacity.

Ogólny `Tests/gui-smoke` pozostawał w trakcie podczas zapisu raportu. Dedykowany
produkcyjny smoke Stage 2D1 jest zielony na obu systemach. Self-hosted Windows
nie jest wymagany, ponieważ etap nie używa Kvasera, CANlib ani sprzętu CAN.

Copilot Code Review nie wykonał analizy z powodu wyczerpanego limitu konta. Nie
powstały wątki review.

## Następny rekomendowany etap

`Comparison Visualization Stage 2D2 — transakcje UDS na trwałej osi czasu`

Proponowany zakres:

- warstwa transakcji UDS na istniejącej osi czasu,
- wizualne odcinki request → first response → final response,
- statusy positive, negative, timeout, capture-ended i suppress,
- oznaczenie odpowiedzi `0x78`,
- wybór transakcji na osi i synchronizacja z eksploratorem Stage 2D1,
- przejście z wiersza eksploratora do odpowiedniego zakresu osi,
- filtry warstwy według SID, DID, Routine ID i statusu,
- trwała, wersjonowana konfiguracja widoku korelacyjnego,
- wykorzystanie artefaktów Stage 2B i Stage 2C2 bez ponownego skanowania sesji.

Stage 2D2 nie powinien zmieniać parowania transakcji ani formatu osi czasu.
Powinien budować odrębny, trwały artefakt prezentacyjny albo konfigurację
widoku, odwołującą się do istniejących `source_row` i fingerprintów.

## Stałe ograniczenia

Nie zmieniać bez osobnej decyzji architektonicznej:

- `CaptureService`,
- Kvasera i CANlib,
- CAN TX/RX,
- formatu sesji i markerów,
- kompletności i kolejności surowego zapisu,
- schematu indeksów,
- bounded modelu GUI,
- schematu `.crt/project.sqlite`.
