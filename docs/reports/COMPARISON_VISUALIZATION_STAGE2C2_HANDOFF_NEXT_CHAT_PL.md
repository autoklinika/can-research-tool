# Comparison Visualization Stage 2C2 — handoff do kolejnej rozmowy

## Repozytorium i gałąź

- repozytorium: `autoklinika/can-research-tool`,
- gałąź: `agent/comparison-visualization-stage2c2-uds-latency`,
- baza stacked: `agent/comparison-visualization-stage2c1-interframe-jitter`,
  draft PR #52,
- PR Stage 2C2: draft PR #53.

Nie wykonywać merge ani nie oznaczać PR jako ready bez wyraźnego polecenia
właściciela.

## Funkcjonalny checkpoint

`eef6dc8872838447707aaad808df843a87e52667`

Późniejsze commity dokumentacyjne nie zmieniają kodu produkcyjnego.

## Dostarczony zakres

W produkcyjnym oknie `Porównanie logów` znajduje się karta `Latencja UDS`,
która obsługuje:

- jawne klucze request i response,
- rekonstrukcję ISO-TP przez istniejący `IsoTpReassembler`,
- deterministyczne parowanie FIFO według SID,
- odpowiedzi pozytywne i negatywne,
- `0x78 ResponsePending`,
- osobny czas do pierwszej i końcowej odpowiedzi,
- timeout od żądania albo ostatniego `0x78`,
- suppress-positive-response,
- odpowiedzi nieparowane i niekompletne ISO-TP,
- percentyle latencji,
- porównanie z sesją bazową,
- trwały artefakt,
- nawigację do żądania, pierwszej i końcowej odpowiedzi.

## Najważniejsze pliki

- `app/comparison_uds_latency.py`,
- `gui/comparison_uds_latency_view.py`,
- `gui/comparison_visualization_stage2c2.py`,
- `gui/comparison_sets_analysis_view.py`,
- `tests/test_comparison_uds_latency.py`,
- `tests_gui/comparison_uds_latency_smoke.py`,
- `.github/workflows/comparison-uds-latency-stage2c2.yml`,
- `docs/reports/COMPARISON_VISUALIZATION_STAGE2C2_UDS_LATENCY_PL.md`.

## Reguły, których nie wolno zgubić

1. Analiza jest wyłącznie pasywna.
2. Request i response są wskazywane dokładnymi kluczami CAN.
3. Komunikat wieloramkowy jest dowodem logicznym, ale nawigacja zachowuje
   pierwszy i ostatni dokładny `source_row`.
4. Latencja jest liczona od końca kompletnego żądania do początku odpowiedzi.
5. `0x78` ustawia first-response latency, nie zamyka transakcji i odnawia
   timeout.
6. Odpowiedź końcowa może być pozytywna albo negatywna.
7. Timeout jest oceniany względem rzeczywistego końca surowej sesji, pobranego
   przez istniejący indeks stronicowany.
8. Suppress-positive-response bez odpowiedzi nie jest timeoutem.
9. Nieparowana odpowiedź nie może zostać sztucznie przypisana do innego SID.
10. Nie zmieniać formatu sesji ani schematu projektu.

## Test ręczny na Windows

Test wymaga zestawu porównawczego, którego sesje zawierają ruch UDS między tą
samą parą identyfikatorów.

### Przykład 29-bit normal-fixed

- request: `0:EXT:18DA30F9:data`,
- response: `0:EXT:18DAF930:data`.

### Przykład 11-bit

- request: `0:STD:7E0:data`,
- response: `0:STD:7E8:data`.

Należy użyć identyfikatorów rzeczywiście obecnych w badanych sesjach.

Procedura:

1. Uruchom CRT z gałęzi Stage 2C2.
2. Otwórz projekt i zestaw porównawczy zawierający minimum dwie sesje UDS.
3. Kliknij `Analizuj wybrany zestaw…`.
4. Otwórz kartę `Latencja UDS`.
5. Wpisz dokładny klucz żądania i odpowiedzi.
6. Ustaw timeout; dla zwykłej diagnostyki można zacząć od 5000 ms.
7. Kliknij `Analizuj transakcje UDS`.
8. Sprawdź tabelę statystyk:
   - liczba żądań,
   - odpowiedzi pozytywne i negatywne,
   - liczba `0x78`,
   - timeouty,
   - p50/p95/p99.
9. Sprawdź różnice względem sesji bazowej.
10. Zaznacz transakcję zawierającą odpowiedź końcową i otwórz kolejno:
    - `Otwórz żądanie`,
    - `Otwórz pierwszą odpowiedź`,
    - `Otwórz odpowiedź końcową`.
11. Potwierdź właściwą sesję i dokładne ramki.
12. Dla transakcji z `0x78` pierwsza i końcowa odpowiedź powinny prowadzić do
    różnych ramek.
13. Zamknij okno porównania i otwórz je ponownie.
14. Potwierdź automatyczne odtworzenie wyniku z komunikatem o wczytaniu bez
    ponownego skanowania sesji.

Jeżeli sesje nie zawierają wskazanych kluczy albo nie zawierają kompletnego UDS,
wynik może prawidłowo pokazać zero żądań i ostrzeżenie. Nie jest to awaria GUI.

## Interpretacja wyników

- `first response` pokazuje czas do pierwszej reakcji ECU; dla transakcji z
  `0x78` jest to czas do pierwszego ResponsePending,
- `final response` pokazuje pełny czas zakończenia operacji,
- duża różnica first/final wskazuje długie przetwarzanie po pierwszym `0x78`,
- wzrost p95 przy podobnym p50 wskazuje pogorszenie najwolniejszych transakcji,
- `capture-ended` oznacza, że log skończył się przed timeoutem i nie wolno
  automatycznie traktować go jako brak odpowiedzi ECU,
- `unmatched response` może oznaczać rozpoczęcie logowania w połowie transakcji,
  zły klucz request/response albo ruch kilku testerów,
- `incomplete ISO-TP` wskazuje utratę albo brak fragmentu komunikatu.

## Walidacja automatyczna

Funkcjonalny checkpoint przeszedł:

- Stage 2C2 Validation na Ubuntu i Windows,
- pełny pytest,
- Windows GitHub-hosted CI,
- GUI Regressions,
- dashboard porównań,
- Stage 2A timeline,
- Stage 2B persistent alignment,
- Stage 2C1 timing i jitter,
- Live Preview Capacity.

Self-hosted Windows pozostaje niewymagany, ponieważ etap nie używa Kvasera,
CANlib ani sprzętu CAN.

Copilot Code Review nie wykonał analizy z powodu wyczerpanego limitu konta.
Nie zgłoszono wątków review; wykonano własną kontrolę reguł parowania, timeoutów,
bounded evidence, artefaktu i lifecycle GUI.

## Potwierdzenie ręczne

Dnia 2026-07-27 właściciel projektu potwierdził działanie Stage 2C2 na Windows.
Zaakceptowany przepływ obejmuje:

`analiza transakcji UDS → parowanie request/response → statystyki first/final latency → nawigacja do żądania i odpowiedzi → zapis artefaktu → ponowne otwarcie bez skanowania`

Stage 2C2 jest ręcznie zamkniętym checkpointem funkcjonalnym. PR #53 ma nadal
pozostać draftem i bez merge.

## Następny rekomendowany etap

`Comparison Visualization Stage 2D — korelacja protokołowa i widok transakcji`

Ze względu na rozmiar zakresu etap należy podzielić:

### Stage 2D1 — eksplorator transakcji UDS

- filtrowanie po sesji, SID, NRC, statusie, payloadzie i zakresie czasu,
- szczegóły request/first/final response,
- grupowanie według SID, DID, subfunkcji i Routine ID,
- wykres rozkładu first/final latency,
- porównanie usług pomiędzy sesjami,
- eksport widocznej tabeli oraz dowodów do CSV,
- nawigacja do dokładnych ramek źródłowych,
- praca na trwałym artefakcie Stage 2C2 bez skanowania surowych sesji.

### Stage 2D2 — powiązanie z osią czasu

- wizualne naniesienie transakcji na trwałą oś czasu,
- przejście pomiędzy transakcją a punktem osi,
- warstwy statusów i latencji,
- trwała konfiguracja widoku korelacyjnego.

Automatyczne wykrywanie par request/response, functional addressing z wieloma ECU
i niestandardowe adresowanie ISO-TP pozostają osobnymi decyzjami
architektonicznymi.

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
