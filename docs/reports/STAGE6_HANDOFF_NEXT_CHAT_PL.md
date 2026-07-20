# CAN Research Tool — przekazanie do nowej rozmowy po Etapie 6

## Kontekst projektu

Kontynuujemy repozytorium `autoklinika/can-research-tool`.

Aktualna gałąź robocza:

```text
agent/filter-engine-v2-static
```

Pull Request:

```text
#21 — Global Filter Engine v2 — complete static filter Stage 6A
```

PR jest otwarty, draft i niescalony. Nie scalać bez wyraźnej decyzji użytkownika.

## Co zakończono

Etap 6A Global Filter Engine v2 jest zakończony implementacyjnie:

- wzorce CAN ID i payloadu,
- maski i wildcardy,
- statyczny kompilator filtrów,
- pola kanał, RTR, error frame i payload,
- integracja Live Capture i zapisanych sesji,
- wspólna semantyka filtrów dla Live/stored,
- edytor GUI,
- testy hot path, parytetu i granicy raw/logical.

## Końcowe decyzje GUI

Obowiązują następujące zasady:

1. Brak autosave podczas edycji filtrów.
2. Zmiany są robocze do kliknięcia `Zastosuj zmiany`.
3. `Odrzuć zmiany` przywraca ostatni zapisany stan.
4. Zamknięcie okna z niezastosowanymi zmianami wymaga decyzji użytkownika.
5. Skrót presetu nie może zapisać ani przełączyć stanu przy brudnym edytorze.
6. Kursor w polu `Wartość / wartości` nie może przeskakiwać na koniec.
7. `Test presetu` pozostaje domyślnie zwinięty.
8. Wyniki testu są po polsku: `PASUJE`, `NIE PASUJE`, `NIEDOSTĘPNE`.
9. Zachowany jest wcześniejszy układ trzech kolumn. Ostatnia szeroka reorganizacja wizualna została wycofana.

## Najważniejsze kontrakty techniczne

- nie zmieniać `CaptureService`,
- nie zmieniać Kvasera ani lifecycle CANlib,
- nie zmieniać formatu `*.crt.jsonl` ani indeksu sesji,
- zapis ramki pozostaje przed oceną filtra,
- filtry nie mogą modyfikować payloadu ani dekodowania,
- stare presety v1 muszą pozostać zgodne,
- niezastosowana konfiguracja nie wpływa na Live ani stored-session.

## Walidacja

Ostatnia pełna walidacja na `9d7aa2d`:

```text
177 passed in 3.79s
```

oraz cztery smoke testy GUI bez tracebacka.

Późniejsze poprawki GUI zostały sprawdzone ręcznie przez użytkownika, ale po utworzeniu raportów trzeba wykonać jeden pełny lokalny przebieg na aktualnym headzie.

GitHub Actions może nie działać z powodu wyczerpanego miesięcznego limitu. Działamy nadal po staremu i wykonujemy testy lokalnie. Self-hosted runner nie jest teraz konfigurowany.

## Pierwsza czynność w nowej rozmowie

Najpierw ustalić aktualny head:

```powershell
cd C:\CAN\can-research-tool
git switch agent/filter-engine-v2-static
git pull --ff-only
git rev-parse --short HEAD
```

Następnie uruchomić:

```powershell
python -m compileall -q app kvaser gui
python -m pytest -q

$env:QT_QPA_PLATFORM="offscreen"
python .\tests_gui\static_filter_editor_smoke.py
python .\tests_gui\filter_manager_window_smoke.py
python .\tests_gui\static_filter_live_stored_smoke.py
python .\tests_gui\live_filter_worker_smoke.py
python .\tests_gui\live_buffer_performance_smoke.py
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
```

Po pozytywnym wyniku:

1. krótki test ręczny okna filtrów, Live i jednej zapisanej sesji,
2. aktualizacja opisu PR wynikami,
3. oznaczenie PR jako ready for review,
4. merge wyłącznie po jednoznacznej zgodzie użytkownika.

## Następny planowany obszar

Po formalnym zamknięciu PR #21 można rozpocząć Etap 6B — filtry stateful:

- częstotliwość i okres,
- jitter,
- zmiana względem poprzedniej ramki,
- maska zmienności,
- missing-frame timeout,
- wykrywanie liczników.

Nie rozpoczynać 6B przed walidacją i decyzją dotyczącą PR #21.
