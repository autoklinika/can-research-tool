# Stage 7 — kompaktowy selektor artefaktów analizy

## Cel

Odzyskać przestrzeń roboczą zakładki `Analizy` przez zastąpienie dużej tabeli artefaktów kompaktowym selektorem, bez utraty obsługi wielu wyników i bez zmiany warstwy analiz.

## Punkt wyjścia

Stage 6 dostarczył zaakceptowane ręcznie:

- trwałe artefakty analizy,
- KPI sesji,
- Top CAN ID,
- tabelę statystyk per CAN ID,
- lekkie paski udziału.

Duża tabela techniczna artefaktów pozostawała jednak stale widoczna i zajmowała większość szerokości oraz wysokości ekranu, mimo że typowa sesja ma jeden aktualny wynik statystyk.

## Zmiana interfejsu

Tabela artefaktów została usunięta z przestrzeni roboczej.

W jej miejsce dodano u góry:

- etykietę `Wynik analizy`,
- kompaktowy `QComboBox` obsługujący jeden lub wiele artefaktów,
- jedną linię podsumowania: nazwa wyniku, czas utworzenia i wersja providera.

Prawy panel z kartami:

- `Podsumowanie`,
- `Statystyki CAN ID`

zajmuje teraz całą dostępną szerokość.

## Informacje techniczne

Dane takie jak:

- ID artefaktu,
- provider,
- wersja providera,
- algorytm,
- schemat,
- ścieżka pliku,
- SHA-256,
- źródła

zostały przeniesione do domyślnie zwiniętej sekcji `Informacje o artefakcie`.

Sekcja jest rozwijana przyciskiem z kierunkową strzałką i nie zajmuje miejsca podczas normalnej analizy statystyk.

## Obsługa wielu artefaktów

Uproszczenie nie usuwa katalogu artefaktów ani jego funkcjonalności.

Selektor:

- wyświetla wszystkie trwałe artefakty przypisane do sesji,
- po zakończeniu analizy wybiera nowo utworzony wynik,
- zachowuje aktualny wybór podczas ręcznego odświeżenia,
- przełącza podsumowanie, tabelę CAN ID i informacje techniczne,
- działa również po ponownym otwarciu sesji.

## Architektura

Nowa warstwa `CompactArtifactSessionViewWidget` rozszerza zaakceptowany widok Stage 6.

Nie zmieniono:

- `SessionAnalysisService`,
- `ArtifactCatalog`,
- Extension Registry i runnera,
- providera `crt.analysis.session_statistics`,
- schematu `session-statistics.json`,
- modeli domenowych i migracji SQLite.

## Bezpieczeństwo danych

Stage 7 jest wyłącznie zmianą prezentacyjną.

Zachowane pozostają:

- niezmienność surowej sesji,
- kontrola SHA-256 artefaktu,
- atomowy zapis wyniku,
- brak ponownego skanowania sesji przez GUI,
- brak automatycznego uruchamiania analiz.

## Testy

Zaktualizowano istniejące smoke testy:

- `session_analysis_workflow_smoke.py`,
- `session_statistics_table_smoke.py`,
- `session_statistics_visual_summary_smoke.py`.

Dodano:

- `session_artifact_selector_smoke.py`.

Nowy smoke sprawdza:

- brak dużej tabeli artefaktów,
- stan bez artefaktów,
- dwa kolejne uruchomienia analizy,
- dwa elementy w selektorze,
- automatyczny wybór najnowszego wyniku,
- ręczne przełączenie na drugi wynik,
- aktualizację informacji technicznych,
- zwijanie i rozwijanie sekcji,
- niezmienność SHA-256 sesji źródłowej.

Test został dodany do:

- `GUI Regressions`,
- `Windows GitHub-Hosted CI`.

## Zachowane kontrakty projektu

- brak zmian `CaptureService`,
- brak zmian backendu Kvaser,
- brak zmian lifecycle CANlib,
- brak zmian formatu sesji i indeksu,
- brak zmian kolejności ani kompletności zapisu ramek,
- brak zmian Live Capture, filtrów i dekoderów,
- brak AI,
- brak funkcji aktywnych i CAN TX.

## Walidacja ręczna

Do sprawdzenia na rzeczywistej sesji:

1. otworzyć zakładkę `Analizy`,
2. potwierdzić pełną szerokość panelu podsumowania,
3. sprawdzić selektor wyniku u góry,
4. rozwinąć `Informacje o artefakcie`,
5. ponownie zwinąć sekcję,
6. opcjonalnie uruchomić analizę drugi raz i przełączyć wyniki w selektorze.
