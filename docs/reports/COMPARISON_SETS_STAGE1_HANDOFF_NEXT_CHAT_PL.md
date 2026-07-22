# Handoff — Comparison Sets Stage 1

Kontynuujemy CAN Research Tool po implementacji Comparison Sets Stage 1.

Repozytorium:

`autoklinika/can-research-tool`

Gałąź:

`agent/comparison-sets-stage1`

PR:

`#44`

Baza stacked PR:

`agent/project-catalog-stage1` / PR `#43`

Przeczytaj dokładnie:

- `docs/CRT_RESEARCH_PLATFORM_MASTER_PLAN_PL.md`,
- `docs/reports/PROJECT_CATALOG_STAGE1_FINAL_REPORT_PL.md`,
- `docs/reports/PROJECT_CATALOG_STAGE1_HANDOFF_NEXT_CHAT_PL.md`,
- `docs/reports/COMPARISON_SETS_STAGE1_IMPLEMENTATION_REPORT_PL.md`.

Na początku:

1. sprawdź aktualny HEAD gałęzi i PR #44,
2. sprawdź najnowsze GitHub Actions dla aktualnego HEAD,
3. sprawdź review i nierozwiązane wątki PR #44,
4. potwierdź, że PR #44 nadal bazuje na PR #43,
5. sprawdź stan PR #43, PR #35 i zależności stacked PR-ów,
6. nie oznaczaj PR #44 jako Ready for review i nie wykonuj merge bez wyraźnego polecenia.

Comparison Sets Stage 1 dostarcza:

- trwałe tworzenie, odczyt, edycję i usuwanie zestawów wielu sesji,
- opcjonalną sesję bazową,
- zachowanie kolejności sesji,
- blokadę modyfikacji zestawu użytego przez analizę,
- widok `Zestawy porównawcze`,
- modalny wybór sesji,
- integrację akcji `Porównaj`,
- sekcję zestawów w Explorerze,
- testy integralności SHA-256 sesji,
- smoke GUI na Linuxie i Windows.

Etap nie dodaje jeszcze providera analizy porównawczej i nie wykonuje synchronizacji sesji. Nowe zestawy używają `synchronization_mode="none"`.

Najpierw zakończ walidację PR #44:

- przeanalizuj wyniki CI,
- popraw wyłącznie rzeczywiste regresje,
- wykonaj checklistę ręczną z raportu,
- po ręcznym potwierdzeniu przygotuj raport końcowy i zaktualizuj opis PR.

Dopiero po akceptacji wskaż kolejny etap: deterministyczny provider porównawczy statystyk CAN ID działający przez istniejące Extension API i zapisujący wersjonowany artefakt dla `AnalysisInput(kind="comparison_set")`.

Nie zmieniaj bez osobnej decyzji:

- `CaptureService`,
- backendu Kvaser,
- lifecycle CANlib,
- CAN TX/RX,
- formatu sesji,
- kolejności pełnego zapisu surowych ramek,
- trwałych indeksów wyszukiwania,
- schematu `.crt/project.sqlite`,
- kontraktów Project Properties Stage 1,
- kontraktów Project Catalog Stage 1.
