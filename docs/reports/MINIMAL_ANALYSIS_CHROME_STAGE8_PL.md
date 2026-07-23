# Stage 8 — minimalny interfejs analiz zapisanej sesji

## Cel

Usunięcie stałych elementów interfejsu, które po zakończeniu analizy nie przekazują nowych informacji i zabierają pionową przestrzeń roboczą.

## Zmiana wizualna

Przy poprawnie skonfigurowanej zapisanej sesji i braku aktywnego zadania ukryte są:

- pasek postępu z tekstem `Oczekiwanie` lub `Gotowe`,
- stały komunikat `Gotowe. Analiza działa pasywnie...`,
- pasek wyboru wyniku, gdy istnieje zero lub jeden artefakt,
- powtórzony opis nazwy, daty i wersji wybranego artefaktu.

Dashboard `Podsumowanie` i tabela `Statystyki CAN ID` są wtedy prezentowane bezpośrednio pod kontrolkami uruchamiania analizy.

## Widoczność warunkowa

Pasek postępu i status pojawiają się wyłącznie:

- podczas uruchamiania i wykonywania analizy,
- podczas anulowania,
- po błędzie,
- gdy analiza jest niedostępna z powodu braku kontekstu projektu, sesji lub providera,
- gdy nie można odczytać katalogu artefaktów.

Po poprawnym zakończeniu analizy dashboard sam stanowi potwierdzenie wyniku, dlatego pasek i komunikat są ponownie ukrywane.

## Wiele wyników

Selektor `Wynik analizy` jest ukryty dla zero lub jednego artefaktu. Pojawia się automatycznie dopiero od dwóch wyników i nadal pozwala przełączać całe podsumowanie, tabelę CAN ID oraz informacje techniczne.

Stała linia powtarzająca nazwę, datę i wersję została ukryta również przy wielu wynikach — te informacje są już zawarte w pozycji dropdownu.

## Architektura

Dodano cienką warstwę prezentacyjną:

- `gui/minimal_analysis_chrome.py`
- `MinimalAnalysisChromeSessionViewWidget`

Warstwa dziedziczy po zaakceptowanym widoku Stage 7 i steruje wyłącznie widocznością istniejących kontrolek. Nie zmienia uruchamiania analiz, providerów, artefaktów ani modeli statystyk.

## Zachowane kontrakty

Bez zmian pozostają:

- `CaptureService`,
- Kvaser i lifecycle CANlib,
- format oraz kolejność zapisu surowych ramek,
- pliki i indeksy sesji,
- `SessionAnalysisService`,
- Extension API,
- provider `crt.analysis.session_statistics`,
- schemat `session-statistics.json`,
- integralność źródłowej sesji.

## Test regresyjny

`tests_gui/minimal_analysis_chrome_smoke.py` sprawdza:

1. ukryty progres i status w stanie spoczynku,
2. brak selektora bez wyników,
3. widoczny progres i status podczas analizy,
4. ponowne ukrycie po sukcesie,
5. bezpośredni dashboard przy jednym artefakcie,
6. automatyczne pojawienie się dropdownu przy drugim artefakcie,
7. brak powtórzonej linii opisu,
8. identyczny SHA-256 pliku źródłowej sesji.

Test został dodany do `GUI Regressions` oraz pełnego `Windows GitHub-Hosted CI`.
