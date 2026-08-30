# Comparison Visualization Stage 2D2 — trwała oś transakcji UDS

Data: 2026-07-27

## 1. Status etapu

Stage 2D2 został zaimplementowany i zwalidowany automatycznie na funkcjonalnym commicie:

`3d27e845209a3f3276277cb5ad4e4628df409cea`

Etap oczekuje na końcowy test ręczny właściciela projektu na Windows.

Gałąź:

`agent/comparison-visualization-stage2d2-uds-timeline`

Draft PR:

`#56 Add synchronized UDS transaction timeline`

PR pozostaje draftem. Nie wykonano merge i nie oznaczono PR jako ready.

## 2. Cel

Celem Stage 2D2 było połączenie dwóch istniejących trwałych źródeł badawczych:

1. wyrównania sesji zapisanego przez Stage 2B,
2. transakcji UDS zapisanych przez Stage 2C2,

w jeden widok pokazujący przebieg request/response na wspólnej osi czasu.

Widok ma działać bez ponownego skanowania surowych sesji i zachowywać dokładną nawigację do ramek źródłowych.

## 3. Nowa karta `Oś UDS`

W oknie `Porównanie logów` dodano kartę `Oś UDS`.

Każda sesja otrzymuje osobny pas. Dla każdej zachowanej transakcji widok prezentuje:

- moment request,
- moment pierwszej odpowiedzi,
- moment odpowiedzi końcowej,
- wszystkie zachowane odpowiedzi `0x78 ResponsePending`,
- rzeczywistą długość transakcji,
- status końcowy,
- klasyfikację względem kolejności sesji bazowej.

## 4. Źródła danych

Stage 2D2 nie tworzy nowego skanera ramek i nie rekonstruuje ponownie ISO-TP.

Źródła są wczytywane wyłącznie z:

- najnowszego zgodnego artefaktu `comparison_timeline_alignment`,
- preferowanego niepustego artefaktu `comparison_uds_latency`.

Jeżeli nowszy artefakt UDS jest pusty, zostaje pominięty zgodnie z regułą wprowadzoną w Stage 2D1.

Zgodność wyrównania i transakcji nadal jest kontrolowana przez istniejące fingerprinty sesji.

## 5. Reprezentacja graficzna

Kolory transakcji:

- zielony — odpowiedź pozytywna,
- czerwony — odpowiedź negatywna,
- pomarańczowy odcinek przerywany — timeout,
- szary odcinek przerywany — koniec logu,
- niebieski — suppress-positive-response bez odpowiedzi.

Dodatkowe oznaczenia:

- fioletowy punkt nad odcinkiem — `0x78 ResponsePending`,
- pomarańczowa ramka — transakcja dodatkowa,
- żółta ramka — transakcja przesunięta w kolejności,
- pionowa linia `t = 0` — kotwica trwałego wyrównania Stage 2B.

Długość odcinka odpowiada czasowi od request do odpowiedzi końcowej. Gdy final response nie istnieje, używany jest moment pierwszej odpowiedzi albo krótki znacznik request.

## 6. Filtry

Widok obsługuje filtrowanie według:

- sesji,
- SID usługi,
- statusu transakcji,
- DID,
- NRC,
- tekstu występującego w nazwie korelacji, payloadzie lub statusie.

Filtry zmieniają wyłącznie prezentację. Nie zmieniają źródłowych artefaktów i nie uruchamiają ponownego skanowania sesji.

## 7. Porównanie kolejności protokołu

Stage 2D2 porównuje kolejność zachowanych transakcji każdej sesji z sesją bazową.

Klucz korelacji wykorzystuje istniejącą semantykę Stage 2D1:

- SID,
- DID,
- subfunkcję,
- Routine ID.

Transakcje są klasyfikowane jako:

- `baseline` — transakcja sesji bazowej,
- `matched` — zachowana w tej samej wspólnej kolejności,
- `shifted` — istnieje w obu sesjach, ale zmieniła pozycję,
- `additional` — nie ma odpowiadającej transakcji w bazie.

Dodatkowo tabela różnic pokazuje:

- liczbę transakcji brakujących,
- liczbę transakcji dodatkowych,
- liczbę transakcji przesuniętych,
- listę brakujących usług lub korelacji.

### Ważna reguła

Porównanie sekwencji jest liczone na pełnym zachowanym artefakcie Stage 2C2. Filtry widoku nie mogą zmieniać klasyfikacji protokołowej.

## 8. Nawigacja do dowodów

Dla zaznaczonej transakcji dostępne są:

- `Otwórz żądanie`,
- `Otwórz pierwszą odpowiedź`,
- `Otwórz odpowiedź końcową`.

Każde przejście korzysta z dokładnego `source_row` i istniejącego bezpiecznego lifecycle nawigacji okna porównania.

Podwójne kliknięcie transakcji otwiera request.

## 9. Bounded evidence

Stage 2D2 pracuje na zachowanych parach dowodowych Stage 2C2.

Jeżeli sesja ma `evidence_truncated`:

- wykres,
- klasyfikacja kolejności,
- tabela transakcji,
- tabela różnic

dotyczą zachowanych dowodów, a nie wszystkich transakcji sesji.

Dokładne liczniki globalne pozostają w karcie `Latencja UDS`.

## 10. Poprawki wykryte podczas CI

### 10.1 Klasyfikacja zamiany kolejności

Pierwsza wersja testu zakładała, że przy zmianie `[22, 31] → [31, 22, 19]` obie wspólne usługi muszą być oznaczone jako przesunięte.

Kontrakt doprecyzowano:

- jedna usługa pozostaje wspólnym dopasowanym rdzeniem,
- druga jest oznaczona jako przesunięta,
- `19` jest transakcją dodatkową.

Algorytm używa deterministycznych bloków wspólnych oraz bezpiecznego dla duplikatów parowania pozostałych kluczy.

### 10.2 Filtry nie mogą zmieniać różnic sekwencji

CI wykrył, że filtrowanie np. wyłącznie odpowiedzi negatywnych mogło usunąć odpowiadającą transakcję bazową przed porównaniem i błędnie oznaczyć wynik jako dodatkowy.

Poprawka rozdziela:

- pełny model różnic protokołowych,
- przefiltrowany model prezentacji.

Klasyfikacja sekwencji pozostaje stabilna niezależnie od filtrów.

## 11. Aktualizacja Help Center

Zgodnie z polityką `docs/CRT_HELP_MAINTENANCE_POLICY_PL.md`, Stage 2D2 zawiera aktualizację Pomocy w tym samym etapie.

Dodano artykuł:

- identyfikator: `uds-timeline`,
- tytuł: `Trwała oś transakcji UDS`.

Artykuł opisuje:

- lokalizację funkcji,
- wymagane artefakty Stage 2B i Stage 2C2,
- znaczenie kolorów i symboli,
- filtry,
- klasyfikację sekwencji,
- bounded evidence,
- nawigację do dokładnych dowodów.

Dodano również:

- słowa kluczowe wyszukiwarki,
- szybkie przejście `Oś UDS` na stronie głównej Pomocy,
- test wymaganej obecności tematu,
- produkcyjny smoke GUI artykułu.

Help Center ma zostać sprawdzony ręcznie razem z funkcją przed końcowym zatwierdzeniem etapu.

## 12. Zmienione pliki produkcyjne

- `app/comparison_uds_timeline.py`,
- `gui/comparison_uds_timeline_view.py`,
- `gui/comparison_visualization_stage2d2.py`,
- `gui/comparison_sets_analysis_view.py`,
- `app/help_catalog_stage2d2.py`,
- `app/help_catalog_registry.py`,
- `gui/help_center_view_stage2d2.py`,
- `gui/help_center_shell.py`.

## 13. Testy i CI

Dodano lub zmieniono:

- `tests/test_comparison_uds_timeline.py`,
- `tests_gui/comparison_uds_timeline_smoke.py`,
- `tests/test_help_catalog.py`,
- `tests_gui/help_center_smoke.py`,
- `.github/workflows/comparison-uds-timeline-stage2d2.yml`.

Na funkcjonalnym commicie `3d27e845209a3f3276277cb5ad4e4628df409cea` zakończyły się sukcesem:

- `Comparison UDS Timeline Stage 2D2 Validation` — Ubuntu,
- `Comparison UDS Timeline Stage 2D2 Validation` — Windows,
- testy rdzenia Stage 2D2,
- produkcyjny smoke GUI Stage 2D2,
- testy i smoke Help Center,
- pełny job `pytest`,
- `Windows GitHub-Hosted CI`,
- `GUI Regressions`,
- `Live Preview Capacity`,
- `Comparison Dashboard Validation`,
- `Comparison Timeline Validation`,
- `Comparison Timeline Stage 2B Validation`,
- `Comparison Inter-Frame Timing Stage 2C1 Validation`,
- `Comparison UDS Latency Stage 2C2 Validation`,
- `Comparison UDS Transaction Explorer Stage 2D1 Validation`,
- `Help Center Validation`.

Ogólny job `Tests/gui-smoke` nadal wykonywał niezależny długi test tworzenia workspace podczas zapisu raportu.

Windows Self-Hosted CI nie jest wymagany dla pasywnego etapu bez sprzętu CAN.

## 14. Zachowane kontrakty

Bez zmian pozostają:

- `CaptureService`,
- Kvaser i lifecycle CANlib,
- CAN TX/RX,
- format sesji i markerów,
- kompletność i kolejność surowego zapisu,
- schemat indeksów,
- bounded model zapisanych sesji,
- schemat `.crt/project.sqlite`,
- formaty artefaktów Stage 2B i Stage 2C2.

## 15. Kryterium ręcznego odbioru

Etap można ręcznie zatwierdzić po potwierdzeniu:

1. karta `Oś UDS` wczytuje zapisane źródła bez skanowania,
2. request, `0x78` i final response są widoczne na właściwych pasach,
3. filtry działają bez zmiany klasyfikacji sekwencji,
4. tabela różnic pokazuje brakujące, dodatkowe i przesunięte transakcje,
5. trzy przyciski nawigacji otwierają właściwe ramki,
6. artykuł Pomocy `Trwała oś transakcji UDS` jest dostępny i zgodny z funkcją.
