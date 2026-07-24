# Comparison Visualization Stage 1 — handoff do kolejnej rozmowy

## Repozytorium

`autoklinika/can-research-tool`

## Gałąź

`agent/comparison-visualization-stage1`

## Pull request

`#49 Add graphical comparison dashboard`

PR pozostaje draftem. Nie oznaczać jako ready i nie wykonywać merge bez wyraźnego polecenia właściciela projektu.

## Dokument nadrzędny etapu

Najpierw przeczytaj:

- `docs/reports/COMPARISON_VISUALIZATION_STAGE1_FINAL_REPORT_PL.md`,
- `docs/CRT_RESEARCH_PLATFORM_MASTER_PLAN_PL.md`,
- odpowiednie wcześniejsze raporty analiz porównawczych i trwałych indeksów wyszukiwania.

## Aktualny stan funkcjonalny

Dostarczono graficzny dashboard porównań z:

- kartami KPI,
- heatmapą obecności wiadomości,
- rankingiem zmian częstotliwości,
- pełną tabelą różnic ze stronicowaniem,
- wyszukiwaniem, filtrami i sortowaniem całego wyniku,
- inspektorem wiadomości,
- podglądem różnic payloadu,
- akcją `Uruchom komplet analiz`,
- nawigacją `Otwórz dowody` do ramki źródłowej.

Końcowy przepływ został ręcznie potwierdzony przez właściciela projektu:

`dashboard → dowód → właściwa sesja → właściwa ramka`.

Okno porównania jest niezależne i niemodalne. Po sukcesie minimalizuje się, a główne CRT przejmuje fokus.

## Checkpointy

Ostatni funkcjonalny checkpoint przed raportami:

`6564446915d1a27ffe73ac4d2c23a5cf9969a995`

Commit raportu końcowego:

`45e0dbaf2e43edb5ec06408bfbf4fc2c03fd701a`

Commit pierwszej wersji handoffu:

`29e4e2e3bdb9ab6be28ada70dc44d86f30040f83`

Na początku kolejnej rozmowy zawsze sprawdź rzeczywisty HEAD PR #49, ponieważ niniejsza aktualizacja handoffu tworzy kolejny commit.

## Pierwsze zadania w kolejnej rozmowie

1. Sprawdź aktualny HEAD gałęzi i PR #49.
2. Sprawdź wszystkie workflowy dla najnowszego HEAD.
3. Jeżeli którykolwiek workflow nie jest zielony, przeanalizuj joby i popraw regresję.
4. Sprawdź review Copilota i nierozwiązane wątki.
5. Zweryfikuj, czy opis PR odpowiada końcowemu zachowaniu okna:
   - okno jest niemodalne,
   - nie zamyka się po otwarciu dowodu,
   - minimalizuje się i odsłania główne CRT.
6. Wykonaj końcowy checkpoint commit/push po ewentualnych poprawkach.

Nie oznaczaj PR jako ready i nie wykonuj merge bez wyraźnego polecenia właściciela.

## Test ręczny do powtórzenia po zmianach

Na Windows:

1. Otwórz projekt zawierający co najmniej dwie zapisane sesje.
2. Otwórz zestawy porównawcze.
3. Uruchom dashboard wybranego zestawu.
4. Wykonaj komplet analiz.
5. Sprawdź wyszukiwanie i filtry tabeli.
6. Kliknij `Otwórz dowody` dla rekordu.
7. Potwierdź:
   - minimalizację okna porównania,
   - przejęcie fokusu przez główne CRT,
   - otwarcie właściwej sesji,
   - przejście do właściwej strony,
   - zaznaczenie właściwej ramki.
8. Przywróć okno porównania i otwórz kolejny dowód.

W miarę dostępności danych powtórz dla statusów:

- nowe ID,
- brakujące ID,
- zmienione ID.

## Testy automatyczne szczególnie istotne

- `tests/test_comparison_evidence.py`
- `tests_gui/comparison_visualization_smoke.py`
- `tests_gui/comparison_visualization_navigation_smoke.py`

Pełna walidacja automatyczna powinna być wykonywana na GitHub Actions. Self-hosted Windows pozostaje istotny tylko tam, gdzie workflow tego wymaga.

## Stałe ograniczenia

Nie zmieniaj bez osobnej decyzji architektonicznej:

- `CaptureService`,
- Kvasera i backendu sprzętowego,
- lifecycle CANlib,
- kodu CAN TX/RX,
- formatu sesji,
- kolejności ani kompletności pełnego zapisu surowych ramek,
- schematu trwałych indeksów,
- bounded/stronicowanego modelu GUI,
- schematu `.crt/project.sqlite`.

## Rekomendowany następny etap

Po pełnym domknięciu PR #49 rozpocząć na osobnej gałęzi:

`Comparison Visualization Stage 2 — analiza czasowa`

Zakres proponowany:

- wspólna oś czasu sesji,
- synchronizacja względem znacznika lub zdarzenia,
- porównanie kolejności komunikatów,
- różnice opóźnień i czasu odpowiedzi,
- przejście z punktu osi czasu do ramki źródłowej.

Nie rozpoczynaj Stage 2 na gałęzi Stage 1, jeśli PR #49 nie został wcześniej formalnie domknięty zgodnie z decyzją właściciela.
