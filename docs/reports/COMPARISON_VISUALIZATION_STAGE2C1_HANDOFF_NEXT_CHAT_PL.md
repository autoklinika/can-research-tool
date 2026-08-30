# Comparison Visualization Stage 2C1 — handoff do kolejnej rozmowy

## Repozytorium i gałąź

- repozytorium: `autoklinika/can-research-tool`,
- gałąź: `agent/comparison-visualization-stage2c1-interframe-jitter`,
- baza stacked: `agent/comparison-visualization-stage2b-persistent-alignment`,
  draft PR #51,
- PR Stage 2C1: draft PR #52.

Nie wykonywać merge ani nie oznaczać PR jako ready bez wyraźnego polecenia
właściciela.

## Funkcjonalny checkpoint

`497c5a352837ea4fe5ab42624e5b6bb408707256`

Późniejsze commity raportowe nie zmieniają kodu produkcyjnego.

## Dostarczony zakres

W produkcyjnym oknie `Porównanie logów` znajduje się karta `Timing i jitter`,
która obsługuje:

- analizę jednego dokładnego klucza wiadomości,
- średnią, medianę, percentyle, odchylenie standardowe i częstotliwość,
- jitter `p95-p05`, RMS względem mediany i współczynnik zmienności,
- wykrywanie przerw względem konfigurowalnego progu,
- porównanie metryk z sesją bazową,
- bounded listę najdłuższych przerw,
- nawigację do obu dokładnych ramek tworzących odstęp,
- zapis i automatyczne odtworzenie wersjonowanego artefaktu bez skanowania sesji.

## Najważniejsze pliki

- `app/comparison_interframe_timing.py`,
- `gui/comparison_interframe_timing_view.py`,
- `gui/comparison_visualization_stage2c1.py`,
- `gui/comparison_sets_analysis_view.py`,
- `tests/test_comparison_interframe_timing.py`,
- `tests_gui/comparison_interframe_timing_smoke.py`,
- `.github/workflows/comparison-interframe-timing-stage2c1.yml`,
- `docs/reports/COMPARISON_VISUALIZATION_STAGE2C1_INTERFRAME_TIMING_PL.md`.

## Test ręczny na Windows

1. Uruchom CRT z gałęzi Stage 2C1.
2. Otwórz projekt zawierający minimum dwie zapisane sesje.
3. Otwórz `Porównaj`, wybierz zestaw i kliknij
   `Analizuj wybrany zestaw…`.
4. Wejdź do karty `Timing i jitter`.
5. Wpisz dokładny klucz występujący w obu sesjach, na przykład
   `0:EXT:1AFFB680:data`.
6. Pozostaw próg przerwy `3,0` i kliknij `Analizuj timing`.
7. Sprawdź wykres, tabelę sesji i różnice względem bazy.
8. Gdy tabela przerw zawiera pozycję, zaznacz ją i sprawdź kolejno:
   `Otwórz początek odstępu` oraz `Otwórz koniec odstępu`.
9. Potwierdź otwarcie właściwej sesji i dokładnych ramek.
10. Zamknij okno porównania i otwórz je ponownie.
11. Potwierdź automatyczne wczytanie wyniku z komunikatem o odtworzeniu bez
    ponownego skanowania sesji.
12. Opcjonalnie zmień mnożnik progu i uruchom analizę ponownie, aby sprawdzić
    wpływ progu na liczbę przerw.

## Potwierdzenie ręczne

Dnia 2026-07-27 właściciel projektu wykonał test na Windows i potwierdził działanie
pełnego przepływu:

`analiza klucza → statystyki i jitter → wykryte przerwy → nawigacja do obu ramek → zapis artefaktu → ponowne otwarcie bez skanowania`

Stage 2C1 jest zatem potwierdzony zarówno automatycznie, jak i ręcznie. Dokładne
wiersze źródłowe obu ramek przerwy są zachowywane i poprawnie otwierane.

## Interpretacja wyników

- wzrost mediany oznacza spadek typowej częstotliwości wiadomości,
- duże `p95-p05` oznacza niestabilny okres transmisji,
- duży RMS względem mediany wskazuje rozrzut także poza skrajnymi percentylami,
- wysoki współczynnik zmienności ułatwia porównywanie kluczy o różnych okresach,
- przerwa wskazuje odstęp co najmniej równy `mediana × próg`,
- brak pozycji w tabeli przerw nie oznacza braku jitteru — oznacza tylko brak
  odstępu przekraczającego ustawiony próg.

## Walidacja automatyczna

Funkcjonalny checkpoint przeszedł:

- Stage 2C1 Validation na Ubuntu i Windows,
- pełny pytest,
- Windows GitHub-hosted CI,
- GUI Regressions,
- dashboard porównań,
- Stage 2A timeline,
- Stage 2B persistent alignment,
- Live Preview Capacity.

Self-hosted Windows pozostaje niewymagany, ponieważ etap nie używa Kvasera,
CANlib ani sprzętu CAN.

## Następny rekomendowany etap

`Comparison Visualization Stage 2C2 — request/response latency i transakcje UDS`

Proponowany zakres:

- jawna konfiguracja klucza żądania i odpowiedzi,
- deterministyczne parowanie transakcji,
- identyfikacja SID i positive response SID,
- odpowiedzi negatywne `0x7F`,
- obsługa `0x78 ResponsePending`,
- czas do pierwszej odpowiedzi,
- czas do odpowiedzi końcowej,
- timeouty i nieparowane żądania lub odpowiedzi,
- percentyle latencji i porównanie między sesjami,
- trwały artefakt z parami dowodowymi,
- nawigacja do żądania, pierwszej odpowiedzi i odpowiedzi końcowej.

Stage 2C2 powinien pozostać pasywny i korzystać wyłącznie z zapisanych sesji.
Nie należy jeszcze automatycznie wysyłać żądań UDS ani zmieniać transportu CAN.

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
