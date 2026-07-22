# CAN Research Tool — zakończenie etapu analiz i handoff do kolejnej rozmowy

## 1. Cel dokumentu

Ten raport zamyka etap budowy fundamentu analiz zapisanych sesji w CAN Research Tool i przekazuje jednoznaczny punkt startowy do kolejnego tematu: tworzenia oraz edytowania projektów CRT.

Raport obejmuje warstwę domenową, Extension API, pierwszy provider analityczny, trwałe artefakty, integrację GUI, statystyki per CAN ID oraz kolejne uproszczenia interfejsu.

## 2. Aktualny stan repozytorium

Repozytorium:

```text
autoklinika/can-research-tool
```

Aktualna gałąź końcowa etapu:

```text
agent/minimal-analysis-chrome-stage8
```

Aktualny funkcjonalny HEAD przed tym raportem:

```text
7f2530349e726f0787321c663e227a52a6e16913
```

Aktualny PR:

```text
PR #34 — Hide idle analysis chrome and single-result selector
```

PR #34 jest draftem, pozostaje otwarty i nie został scalony.

## 3. Ręczna walidacja użytkownika

Użytkownik ręcznie potwierdził poprawne działanie końcowego widoku analiz.

Potwierdzono w szczególności:

- uruchamianie analizy zapisanej sesji,
- zapis trwałego artefaktu,
- wyświetlanie KPI i Top CAN ID,
- tabelę statystyk CAN ID,
- brak dużej tabeli artefaktów,
- brak zbędnych stałych komunikatów i paska `Oczekiwanie / Gotowe`,
- bezpośredni dashboard przy jednym wyniku,
- pojawienie się selektora dopiero przy wielu artefaktach.

Etap analiz można uznać za zakończony w zakresie podstawowym.

## 4. Łańcuch wykonanych etapów i PR-ów

### PR #25 — grupowanie surowych ramek według ID

Gałąź:

```text
agent/raw-frame-grouping-stage1
```

Dodano widoki:

- `Lista`,
- `Grupuj po ID`.

Zmiana dotyczy wyłącznie prezentacji bufora GUI i nie wpływa na pełny zapis ramek.

### PR #26 — fundament danych domenowych CRT

Gałąź:

```text
agent/domain-extension-foundation-stage1
```

Dodano między innymi:

- stabilne identyfikatory domenowe,
- profile ECU,
- zestawy porównawcze,
- uruchomienia analiz,
- artefakty,
- findings,
- dowody i referencje do ramek,
- addytywny schemat SQLite w `project.sqlite`.

### PR #27 — fundament Extension API

Gałąź:

```text
agent/extension-api-foundation-stage2
```

Dodano:

- manifest rozszerzenia,
- jawny registry,
- read-only `ProjectContext`, `SessionSource` i `FrameQuery`,
- runner z granicą wyjątków,
- anulowanie i raportowanie postępu,
- atomowy `ArtifactWriter`,
- `FindingWriter`.

Nie dodano dynamicznego ładowania kodu projektu ani automatycznego skanowania pluginów.

### PR #28 — provider statystyk sesji

Gałąź:

```text
agent/session-statistics-provider-stage3
```

Provider:

```text
crt.analysis.session_statistics
```

Generuje deterministyczny artefakt:

```text
artifacts/<analysis_run_id>/session-statistics.json
```

Artefakt zawiera między innymi:

- liczbę ramek,
- liczbę bajtów payloadu,
- rozkład DLC,
- kanały,
- STD / EXT,
- DATA / RTR / ERROR,
- unikalne CAN ID,
- unikalne klucze wiadomości,
- statystyki interwałów,
- częstotliwość,
- statystyki per klucz wiadomości.

### PR #29 — korekta paska Live Capture

Gałąź:

```text
agent/live-toolbar-layout-fix
```

Poprawiono wyłącznie layout:

- `Widok` przeniesiono przed `Pauza widoku`,
- usunięto osobny wiersz nad tabelą,
- usunięto tekst `Aktywne presety:`.

Nie zmieniono logiki odbioru ani zapisu ramek.

### PR #30 — workflow analizy zapisanej sesji

Gałąź:

```text
agent/session-analysis-workflow-stage4
```

Dodano:

- warstwę aplikacyjną uruchamiania analiz,
- wykonywanie w tle,
- anulowanie,
- trwały katalog artefaktów,
- zakładkę `Analizy` w zapisanej sesji,
- ponowne otwieranie istniejących artefaktów.

### PR #31 — tabela statystyk CAN ID

Gałąź:

```text
agent/session-statistics-table-stage5
```

Dodano sortowalną i filtrowalną tabelę statystyk per CAN ID z danymi technicznymi dotyczącymi ramek, DLC, częstotliwości, jittera oraz interwałów.

### PR #32 — lekkie podsumowanie graficzne

Gałąź:

```text
agent/session-statistics-visual-summary-stage6
```

Dodano:

- kafle KPI,
- Top 5 aktywnych CAN ID,
- subtelne paski udziału,
- delegate w kolumnie `Udział [%]`.

Nie dodano ciężkiego dashboardu, wykresów kołowych ani heatmap.

### PR #33 — kompaktowy selektor artefaktu

Gałąź:

```text
agent/session-artifact-selector-stage7
```

Usunięto dużą tabelę artefaktów z głównej przestrzeni roboczej.

Dodano:

- kompaktowy wybór wyniku,
- domyślnie zwinięte informacje techniczne,
- zachowanie obsługi wielu artefaktów.

### PR #34 — minimalny interfejs analiz

Gałąź:

```text
agent/minimal-analysis-chrome-stage8
```

Usunięto stały szum interfejsu:

- pasek `Oczekiwanie / Gotowe`,
- komunikat `Gotowe. Analiza działa pasywnie...`,
- selektor przy zero lub jednym artefakcie,
- powtórzoną linię nazwy, daty i wersji.

Pasek postępu i status są widoczne tylko podczas pracy, anulowania, błędu lub stanu niedostępności.

## 5. Końcowy zakres funkcjonalny analiz

Po zakończeniu tego etapu CRT potrafi:

1. otworzyć zapisaną sesję,
2. wykryć zarejestrowane analizy dla sesji,
3. uruchomić analizę w tle,
4. raportować postęp i obsłużyć anulowanie,
5. zapisać trwały artefakt w projekcie,
6. zweryfikować integralność artefaktu,
7. ponownie otworzyć wynik bez ponownego skanowania sesji,
8. pokazać podsumowanie sesji,
9. pokazać statystyki per CAN ID,
10. sortować i filtrować dane,
11. zachować dashboard po ponownym otwarciu projektu i sesji,
12. obsłużyć wiele artefaktów bez zajmowania przestrzeni przy pojedynczym wyniku.

## 6. Najważniejsze kontrakty architektoniczne

Obowiązują nadal następujące zasady:

- jeden projekt CRT odpowiada jednemu badanemu ECU,
- surowa sesja jest niezmiennym źródłem prawdy,
- pełny zapis ramek ma pozostać kompletny i w oryginalnej kolejności,
- filtry i analizy wpływają na prezentację lub osobne artefakty,
- funkcje aktywne muszą pozostać oddzielone od pasywnych analiz,
- AI jest opcjonalne i nie może bezpośrednio sterować CAN,
- kod projektu nie jest automatycznie wykonywany jako plugin,
- artefakty są zapisywane atomowo,
- analiza zapisanej sesji nie może modyfikować pliku `*.crt.jsonl`.

Nie wolno bez wyraźnej potrzeby zmieniać:

- `CaptureService`,
- backendu Kvaser,
- lifecycle CANlib,
- formatu sesji,
- kolejności pełnego zapisu surowych ramek,
- istniejących filtrów i dekoderów.

## 7. Walidacja automatyczna

Dla końcowego funkcjonalnego HEAD Stage 8 zakończyły się sukcesem:

- `Tests`,
- `GUI Regressions`,
- `Live Preview Capacity`,
- `Windows GitHub-Hosted CI`.

Dedykowane smoke testy obejmują:

- pełny workflow analizy,
- zapis i ponowne otwieranie artefaktu,
- tabelę statystyk CAN ID,
- podsumowanie graficzne,
- wiele artefaktów,
- minimalny chrome interfejsu,
- identyczny SHA-256 sesji przed i po analizie.

`Windows Self-Hosted CI` nie blokuje tych etapów, ponieważ zmiany nie wymagają fizycznego Kvasera, CANlib ani sprzętu CAN.

## 8. Stan końcowy interfejsu analiz

Dla jednego wyniku użytkownik widzi bezpośrednio:

- kartę `Podsumowanie`,
- KPI,
- Top CAN ID,
- kartę `Statystyki CAN ID`,
- tabelę techniczną.

Nie są wyświetlane zbędne stałe elementy.

Dopiero przy co najmniej dwóch artefaktach pojawia się selektor wyników.

Informacje techniczne artefaktu pozostają dostępne w zwijanej sekcji.

## 9. Elementy świadomie pozostawione na później

Poza zakończonym etapem znajdują się:

- porównania wielu sesji,
- wykresy czasowe,
- nawigacja ze statystyk do konkretnych ramek,
- findings i hipotezy,
- CAN Intelligence,
- AI,
- funkcje aktywne i CAN TX,
- rozbudowane analizy protokołowe jako osobne providery.

Są to przyszłe, niezależne etapy.

## 10. Następny temat: tworzenie i edytowanie projektów CRT

Następna rozmowa ma wrócić do obsługi projektów.

Pierwsze działania powinny obejmować:

1. przeczytanie tego raportu,
2. sprawdzenie aktualnego HEAD gałęzi,
3. analizę istniejących klas i widoków:
   - `CrtProject`,
   - `NewProjectDialog`,
   - `ProjectOverviewWidget`,
   - `ProjectExplorer`,
   - `ProjectNavigator`,
   - przepływ `Nowy projekt / Otwórz projekt / Zapisz projekt`,
4. spisanie aktualnego modelu metadanych projektu,
5. zaprojektowanie bezpiecznej edycji danych projektu bez zmiany ścieżek i referencji sesji,
6. dopiero potem implementację.

Minimalny oczekiwany zakres pierwszego etapu projektu:

- poprawne tworzenie projektu,
- edycja nazwy i metadanych projektu,
- trwały zapis zmian,
- odświeżenie drzewa i przeglądu projektu,
- walidacja pól,
- brak wpływu na sesje, artefakty, indeksy i analizy.

Nie należy zaczynać od przebudowy całego modelu projektu ani od migracji istniejących sesji bez wcześniejszej analizy aktualnego stanu.

## 11. Komendy startowe

```powershell
Set-Location C:\CAN\can-research-tool

git fetch origin --prune
git switch agent/minimal-analysis-chrome-stage8
git pull --ff-only

git status -sb
git log -1 --oneline
```

Następnie uruchomić:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python .\crt_gui.py
```

## 12. Punkt kontrolny

Etap analiz jest zakończony i ręcznie zaakceptowany.

Aktualny checkpoint obejmuje:

- kod na GitHubie,
- osobne gałęzie i draft PR-y,
- raporty etapowe,
- pełne GitHub-hosted CI,
- ręczne potwierdzenie użytkownika,
- niniejszy końcowy handoff.

Nie wykonywać merge ani porządkowania stacked PR-ów bez osobnej decyzji użytkownika.
