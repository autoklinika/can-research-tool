# Etap 5E — filtry protokołowe w GUI

Edytor Global Filter Engine udostępnia pola surowych ramek oraz wiadomości logicznych J1939, ISO-TP i UDS.

## Zastosowanie

1. Otwórz menedżer filtrów projektu.
2. Dodaj warunek i wybierz pole z kategorii `J1939`, `ISO-TP` albo `UDS`.
3. Zapisz i aktywuj preset dla zakresu `live`, `stored_session` lub obu.
4. W widoku Live albo zapisanej sesji zaznacz `Zastosuj filtry`.

Ten sam przełącznik filtruje tabelę surowych ramek i tabelę wiadomości logicznych. Warunek niedostępny w danym kontekście jest neutralny, dlatego filtr UDS nie ukrywa całej tabeli ramek surowych, a filtr DLC nie ukrywa całej tabeli wiadomości logicznych.

## Kontrakty bezpieczeństwa danych

- filtrowanie dotyczy wyłącznie prezentacji,
- zapis surowych ramek pozostaje niezmieniony,
- filtry Live i zapisanych sesji są domyślnie wyłączone,
- pełne skany wiadomości logicznych działają poza wątkiem GUI i ignorują nieaktualne generacje,
- nowe wiadomości są oceniane przyrostowo po zakończeniu skanu.

## Walidacja

```powershell
python -m pytest -q
python -m ruff check app gui tests tests_gui
$env:QT_QPA_PLATFORM = "offscreen"
python tests_gui/protocol_filter_gui_smoke.py
```
