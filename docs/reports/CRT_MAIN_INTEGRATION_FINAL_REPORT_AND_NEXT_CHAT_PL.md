# CAN Research Tool — końcowy raport integracji działającej wersji z `main`

## 1. Status dokumentu

Ten dokument zamyka duży etap rozwoju CAN Research Tool obejmujący budowę
podstaw projektu CRT, Live Capture, filtrów, dekoderów, zapisanych sesji,
trwałych analiz oraz pierwszego kompletnego zestawu analiz porównawczych.

Dokument pełni jednocześnie trzy role:

1. końcowego raportu wykonanych prac,
2. opisu obowiązującej działającej wersji bazowej,
3. handoffu i gotowego promptu do następnej rozmowy.

Data zamknięcia etapu: **2026-07-23**.

Repozytorium:

`autoklinika/can-research-tool`

Obowiązująca gałąź bazowa:

`main`

Funkcjonalny squash commit działającego checkpointu:

`fe4d1ecda61607056a51a933d5133b8229b04133`

Dokument raportowy został dodany późniejszym commitem dokumentacyjnym z
`[skip ci]`. Przy analizie wersji programu należy rozróżniać funkcjonalny
checkpoint `fe4d1ecd...` od późniejszego commita zawierającego wyłącznie ten
raport.

---

## 2. Sposób integracji

Końcowy stan CRT rozwijano jako długi stack zależnych gałęzi i pull requestów.
Zamiast scalać każdy etap osobno, ostatnią kompletną gałąź:

`agent/message-sequence-comparison-stage3`

zsynchronizowano z aktualnym `main`, zachowując znajdujące się tam dokumenty
Master Planu i konfigurację GitHub Copilota.

Następnie PR #48 został przestawiony bezpośrednio na `main` i potraktowany jako
jeden końcowy PR integracyjny:

`Integrate validated CAN Research Tool working baseline`

PR #48 został scalony metodą **squash**. Wynikiem jest funkcjonalny commit:

`fe4d1ecda61607056a51a933d5133b8229b04133`

Po merge porównanie commita z `main` wykazało stan identyczny — bez brakujących
ani dodatkowych zmian.

---

## 3. Zakres działającej wersji

### 3.1. Projekt CRT jako teczka jednego ECU

Aktualny CRT realizuje podstawową zasadę architektoniczną:

- jeden projekt opisuje jedno badane ECU,
- projekt jest trwałą teczką badawczą, a nie pojedynczym logiem,
- projekt zawiera sesje, konfigurację, profile, indeksy, analizy i artefakty,
- zapisane sesje oraz surowe ramki pozostają niezmiennym źródłem prawdy.

Dostępne są między innymi:

- tworzenie i otwieranie projektów,
- manifest projektu,
- trwały identyfikator projektu,
- obszary badań,
- import zapisanych logów,
- właściwości projektu,
- centralny katalog projektów CRT,
- profil ECU, pojazdu lub maszyny,
- wyszukiwanie i relokacja projektu,
- bezpieczne usuwanie wpisu katalogowego bez kasowania danych projektu.

### 3.2. Live Capture

Działająca wersja zawiera kompletny przepływ pasywnego przechwytywania CAN:

- obsługę Kvaser CANlib,
- tryb `BENCH — ACK aktywny`,
- tryb `LISTEN ONLY — bez ACK`,
- ograniczony prefetch kolejki CANlib,
- pełny strumieniowy zapis surowych ramek,
- ograniczone modele GUI niezależne od pełnego zapisu,
- świadome włączanie zapisu sesji,
- znaczniki podczas rejestracji,
- bezpieczne kończenie i zapis sesji,
- cleanup plików tymczasowych i uchwytów SQLite,
- blokadę ponownego startu, gdy poprzednia niezapisana sesja wymaga decyzji.

Filtry, pauza widoku i ograniczenie bufora GUI nie ograniczają pełnego zapisu
surowych ramek.

### 3.3. Prezentacja ramek i wiadomości logicznych

CRT udostępnia:

- listę surowych ramek,
- tryb grupowania po kanale, STD/EXT i CAN ID,
- osobne modele dla pełnego i filtrowanego widoku,
- wiadomości logiczne,
- szczegóły wiadomości i ramek źródłowych,
- Inspektor,
- stronicowane widoki dużych zapisanych sesji,
- ograniczone pamięciowo modele Qt.

### 3.4. Filtry

Zaimplementowano Global Filter Engine obejmujący:

- grupy `AND`, `OR` i `NOT`,
- wynik `MATCH`, `NO_MATCH` i `UNAVAILABLE`,
- CAN ID,
- STD/EXT,
- DLC,
- czas względny,
- tryby Include, Exclude i Highlight,
- trwałe presety w projekcie,
- wizualny edytor drzewa,
- jawne włączanie filtrów dla Live i zapisanych sesji,
- background workers oraz ochronę generacyjną,
- brak wpływu filtrów na zapis źródłowy.

### 3.5. DBC i analiza protokołów

Dostępne są:

- import i walidacja DBC,
- kopiowanie DBC do projektu,
- SHA-256 i ścieżki względne,
- włączanie i wyłączanie DBC,
- odwracalna interpretacja zapisanych sesji,
- ISO-TP dla 11-bit i 29-bit normal-fixed,
- UDS z usługami, NRC, DID, Routine ID, SecurityAccess i TransferData,
- J1939 oraz J1939 TP,
- konserwatywna klasyfikacja ramek 29-bit,
- ponowna interpretacja starszego cache wiadomości przez aktualny dekoder,
- szczegóły protokołu w GUI.

DBC i dekodery są warstwami interpretacji. Nie zmieniają surowych sesji.

### 3.6. Wyszukiwanie

Zaimplementowano:

- trwałe indeksy wyszukiwania,
- wyszukiwanie w zapisanych sesjach,
- wyszukiwanie wiadomości logicznych,
- asynchroniczną pracę poza wątkiem GUI,
- nawigację do ramki znajdującej się na innej stronie sesji,
- obsługę sesji filtrowanych i niefiltrowanych,
- ochronę przed nieaktualnymi wynikami workerów.

Nawigacja używa trwałego `source_row` i nie materializuje pełnej sesji w modelu
Qt.

### 3.7. Model domenowy i Extension API

W projekcie istnieje fundament trwałych analiz:

- modele domenowe projektu ECU,
- wersjonowane migracje `.crt/project.sqlite`,
- comparison sets,
- analysis runs,
- artifacts,
- findings i evidence references,
- `ExtensionManifest`,
- jawny `ExtensionRegistry`,
- read-only `ProjectContext`, `SessionSource` i `FrameQuery`,
- anulowanie i raportowanie postępu,
- atomowy `ArtifactWriter`,
- izolacja wyjątków providerów,
- pasywna polityka odrzucająca `can.tx`.

### 3.8. Analizy pojedynczej sesji

Dostępny jest provider statystyk zapisanej sesji:

`crt.analysis.session_statistics`

Tworzy deterministyczny, wersjonowany artefakt zawierający między innymi:

- liczbę ramek,
- liczbę kluczy wiadomości,
- rozkład kanałów i DLC,
- data/remote/error,
- STD/EXT,
- zakres timestampów,
- interwały dodatnie, zerowe i ujemne,
- częstotliwość,
- jitter i anomalie czasu,
- statystyki per CAN ID.

GUI udostępnia:

- uruchamianie analizy w tle,
- anulowanie,
- postęp,
- trwały katalog artefaktów,
- KPI,
- Top CAN ID,
- sortowalną i filtrowalną tabelę,
- selektor wielu wyników,
- informacje techniczne artefaktu,
- ponowne otwarcie gotowego wyniku.

### 3.9. Zestawy porównawcze

Zestaw porównawczy:

- zawiera co najmniej dwie zapisane sesje,
- zachowuje kolejność sesji,
- może posiadać jawną sesję bazową,
- używa obecnie synchronizacji `none`,
- nie kopiuje ani nie modyfikuje sesji,
- jest trwałym wejściem analiz porównawczych.

Po wykonaniu analiz zestawy nadal można edytować lub usuwać bez utraty historii:

- edycja analizowanego zestawu tworzy nową aktywną wersję z nowym ID,
- poprzednia definicja pozostaje źródłem historycznych analysis runs,
- usunięcie analizowanego zestawu ukrywa go z aktywnego widoku,
- sesje, runs, inputs i artefakty pozostają zachowane.

### 3.10. Provider porównania statystyk

Provider:

`crt.comparison.statistics`

porównuje wiele sesji i zapisuje między innymi:

- nowe klucze wiadomości,
- brakujące klucze wiadomości,
- wspólne klucze,
- liczbę ramek,
- udział,
- średnią częstotliwość,
- pełne źródła sesji z SHA-256 i rolą.

### 3.11. Provider różnic payloadów

Provider:

`crt.comparison.payload_differences`

obsługuje:

- pełne warianty payloadów,
- liczność i udział wariantów,
- pierwszy i ostatni timestamp,
- macierz obecności wariantów,
- nowe i brakujące warianty,
- profile pozycji bajtowych,
- bajty stałe i zmienne,
- histogramy, dominantę, minimum i maksimum,
- zmiany DLC,
- deterministyczny ranking zmian.

W wersji algorytmu 2 próg 1000 wariantów jest progiem przejścia z RAM do
run-scoped SQLite, a nie limitem analizy. Wszystkie warianty pozostają dokładnie
zliczone.

### 3.12. Provider sekwencji wiadomości

Provider:

`crt.comparison.message_sequences`

porównuje kolejność wiadomości w wielu sesjach. Obsługuje między innymi:

- surowe i collapsed sekwencje,
- pary i trójki,
- nowe i brakujące sekwencje,
- samoprzejścia,
- cykle,
- kolejność źródłową niezależną od niemonotonicznych timestampów,
- adaptacyjne przejście RAM → SQLite,
- deterministyczny JSON i SHA-256,
- cleanup magazynu tymczasowego po sukcesie, anulowaniu i błędzie.

### 3.13. Interfejs użytkownika

Powłoka CRT ma obecnie formę zwartego narzędzia inżynierskiego:

- klasyczne menu,
- główny toolbar,
- Explorer projektu,
- centralne zakładki,
- Inspektor,
- docki i odtwarzanie układu,
- day/night theme,
- trwałą geometrię okien,
- katalog projektów,
- okna filtrów i wyszukiwania,
- widoki analiz pojedynczej sesji i porównań.

Duże okna obsługują wspólny pełny ekran `F11` z przywracaniem poprzedniego stanu.
Okno analizy porównawczej i katalog projektów mają również natywny przycisk
maksymalizacji.

---

## 4. Końcowa walidacja

Użytkownik wykonał na końcowej gałęzi Stage 3 rzeczywistą walidację Windows:

- `python tests_gui/project_properties_smoke.py` — PASS,
- testy providerów porównawczych — `16 passed`,
- `python tests_gui/comparison_statistics_smoke.py` — PASS,
- `python tests_gui/payload_difference_smoke.py` — PASS,
- `python tests_gui/message_sequence_comparison_smoke.py` — PASS,
- `python -m gui.main` — aplikacja uruchomiona i zamknięta bez błędu,
- ręczna ocena pełnego ekranu okna analizy porównawczej — PASS.

Poszczególne etapy stacka posiadały zielone przebiegi odpowiednich workflowów:

- `Tests`,
- `GUI Regressions`,
- `Windows GitHub-Hosted CI`,
- `Live Preview Capacity`.

`Windows Self-Hosted CI` był traktowany jako nieblokujący dla etapów
niekorzystających z Kvasera, CANlib ani fizycznego CAN.

Po końcowym przestawieniu PR #48 bezpośrednio na `main` GitHub nie utworzył
nowego kompletu workflowów dla ostatnich commitów synchronizacyjnych i
raportowych. Merge wykonano po:

- wcześniejszych zielonych walidacjach etapowych,
- końcowych smoke testach Windows,
- ręcznej akceptacji użytkownika,
- sprawdzeniu pełnego diffu `main → Stage 3`,
- przywróceniu bez zmian dokumentów znajdujących się wyłącznie na `main`,
- potwierdzeniu stanu `0 behind` i mergeability PR #48.

Nie należy więc opisywać końcowego squash SHA jako osobno przetestowanego przez
nowy, świeży workflow po retargetowaniu. Funkcjonalna zawartość została jednak
zwalidowana na końcowej gałęzi przed integracją.

---

## 5. Zachowane kontrakty bezpieczeństwa

W całym zakończonym etapie obowiązują nadal następujące zasady:

- surowe ramki i pliki sesji są źródłem prawdy,
- filtry, pauza widoku i ograniczone modele GUI nie ograniczają pełnego zapisu,
- brak automatycznej transmisji CAN,
- otwarcie projektu, sesji, widoku lub analizy nie wysyła ramek,
- providery analiz są pasywne,
- CaptureService pozostaje właścicielem lifecycle Capture,
- lifecycle Kvasera i CANlib pozostaje jawny,
- kolejność i kompletność pełnego zapisu ramek pozostaje zachowana,
- analizy nie modyfikują sesji źródłowych,
- artefakty są trwałe, wersjonowane i atomowo zapisywane,
- DBC i dekodery są odwracalną warstwą interpretacji,
- duże sesje pozostają stronicowane i ograniczone pamięciowo,
- praca ciężka nie powinna odbywać się w wątku GUI,
- jeden projekt CRT nadal dotyczy jednego badanego ECU.

---

## 6. Porządek wykonany na GitHub

PR #48 został scalony do `main`.

Historyczne PR-y zostały zamknięte jako zastąpione przez końcową integrację:

- #1–#10,
- #22,
- #24–#35,
- #43–#47.

Nie wykonywano osobnego merge każdego historycznego PR-a, ponieważ ich końcowy,
skumulowany wynik znajduje się w squash commicie PR #48.

Zamknięte PR-y zachowują:

- opisy etapów,
- komentarze,
- review,
- historię commitów,
- powiązania z raportami.

Historyczne gałęzie nie zostały usunięte. Pozostają jako dodatkowy ślad rozwoju
i kopia bezpieczeństwa. Nie są jednak bazą kolejnych prac.

Stary automatyczny monitoring PR #45–#48 został wyłączony.

Od tej chwili kolejne etapy należy rozpoczynać wyłącznie od aktualnego `main`.

---

## 7. Znane ograniczenia i tematy otwarte

### 7.1. Serializacja bardzo dużego wyniku payloadów

Adaptacyjny magazyn wariantów przechodzi z RAM do SQLite, lecz końcowy JSON i
pełna macierz wariantów są nadal materializowane przez istniejący
`ArtifactWriter.write_json`. Ekstremalnie duży wynik może zwiększyć szczytowe
zużycie pamięci podczas końcowej serializacji.

### 7.2. Archiwum ukrytych zestawów

Usunięte zestawy posiadające historyczne analizy pozostają zachowane w bazie,
ale nie istnieje jeszcze osobny widok archiwum umożliwiający ich przeglądanie z
GUI.

### 7.3. Synchronizacja zestawów porównawczych

Aktualne providery porównawcze obsługują `synchronization_mode="none"`.
Synchronizacja po znacznikach, zdarzeniach, czasie lub etapach eksperymentu
pozostaje osobnym przyszłym etapem.

### 7.4. Brak automatycznej interpretacji naprawy ECU

Aktualne analizy dostarczają deterministycznych danych porównawczych. Nie
wydają automatycznie werdyktu, czy ECU jest naprawione poprawnie, i nie tworzą
nieudokumentowanych hipotez protokołu.

### 7.5. Brak aktywnych funkcji CAN

Obecna platforma badawcza pozostaje pasywna. Replay, scenariusze aktywne,
emulacja i CAN TX wymagają osobnego projektu bezpieczeństwa, jawnych uprawnień
i niezależnej walidacji sprzętowej.

---

## 8. Zasady rozpoczęcia kolejnego etapu

1. Zaktualizować lokalny `main`.
2. Sprawdzić rzeczywisty aktualny HEAD — commit raportowy będzie nowszy od
   funkcjonalnego squash commita `fe4d1ecd...`.
3. Przeczytać:
   - `docs/CRT_RESEARCH_PLATFORM_MASTER_PLAN_PL.md`,
   - ten raport,
   - raporty etapowe dotyczące wybranego obszaru.
4. Wybrać jeden mały i jednoznaczny kolejny etap.
5. Utworzyć nową gałąź z aktualnego `main`.
6. Otworzyć draft PR.
7. Nie modyfikować obszarów chronionych bez jawnej decyzji użytkownika.
8. Pełną walidację automatyczną wykonywać na GitHub Actions.
9. Runner sprzętowy stosować tylko do Kvasera, CANlib i fizycznego CAN.
10. Po większym etapie wykonać commit, push i nowy raport/handoff.

Copilot powinien być używany przede wszystkim do code review oraz małych,
precyzyjnie wydzielonych zadań, a nie jako samodzielny właściciel architektury.

---

## 9. Gotowy prompt do następnej rozmowy

```text
Kontynuujemy rozwój CAN Research Tool.

Repozytorium:
autoklinika/can-research-tool

Obowiązująca gałąź bazowa:
main

Działająca wersja CRT została scalona przez PR #48 metodą squash.
Funkcjonalny checkpoint integracji:
fe4d1ecda61607056a51a933d5133b8229b04133

Po tym commicie dodano wyłącznie końcowy raport dokumentacyjny, dlatego najpierw
sprawdź rzeczywisty aktualny HEAD `main` i nie zakładaj, że nadal jest równy
`fe4d1ecd...`.

Przeczytaj dokładnie:

- docs/CRT_RESEARCH_PLATFORM_MASTER_PLAN_PL.md
- docs/reports/CRT_MAIN_INTEGRATION_FINAL_REPORT_AND_NEXT_CHAT_PL.md

Następnie:

1. sprawdź aktualny HEAD `main`, stan repozytorium, otwarte PR-y i ostatnie
   workflowy GitHub Actions,
2. potwierdź, że PR #48 jest scalony, a historyczny stack PR-ów jest zamknięty,
3. nie usuwaj historycznych gałęzi bez mojego wyraźnego polecenia,
4. podsumuj aktualne możliwości działającego CRT,
5. na podstawie Master Planu zaproponuj 2–3 logiczne kandydatury na następny
   mały etap rozwoju wraz z zależnościami, ryzykiem i kryteriami ukończenia,
6. nie zmieniaj jeszcze kodu, dopóki nie wybiorę kolejnego etapu.

Stałe ograniczenia:

- nie zmieniaj CaptureService bez mojego jawnego polecenia,
- nie zmieniaj backendu Kvaser ani lifecycle CANlib,
- nie dodawaj CAN TX ani automatycznej transmisji,
- nie zmieniaj formatu sesji,
- nie zmieniaj kolejności ani kompletności pełnego zapisu surowych ramek,
- nie zwiększaj modeli GUI do pełnej liczby ramek,
- zachowuj stronicowanie, trwałe indeksy, bounded models i pracę asynchroniczną,
- analizy mają być pasywne, deterministyczne i nie mogą modyfikować źródeł,
- jeden projekt CRT nadal dotyczy jednego badanego ECU.

Pełne testy wykonujemy na GitHub Actions. Windows self-hosted wykorzystujemy
wyłącznie do testów wymagających fizycznego Kvasera, CANlib lub sprzętu CAN.

Copilota używamy głównie do code review i małych, dokładnie wydzielonych zadań,
nie jako podstawowego wykonawcę dużych zmian architektonicznych.

Nie oznaczaj przyszłych PR-ów jako ready i nie wykonuj merge bez mojego
wyraźnego polecenia.

Na końcu każdego większego etapu zawsze zaproponuj punkt kontrolny obejmujący
commit, push oraz — gdy ma to sens — raport/handoff do kolejnej rozmowy.
```

---

## 10. Podsumowanie końcowe

CAN Research Tool posiada obecnie spójną, działającą bazę obejmującą pełny
przepływ od pasywnego Capture i trwałej sesji, przez filtrowanie, dekodowanie,
wyszukiwanie i projekty CRT, aż do deterministycznych analiz pojedynczych sesji
oraz pierwszych analiz porównawczych wielu logów.

Obowiązującym źródłem kolejnych prac jest aktualny `main`.

Historyczny stack został zamknięty, ale zachowany jako dokumentacja rozwoju.
Kolejny etap powinien rozpocząć się od nowej, małej gałęzi utworzonej z
aktualnego `main`, po świadomym wyborze zakresu zgodnego z Master Planem.
