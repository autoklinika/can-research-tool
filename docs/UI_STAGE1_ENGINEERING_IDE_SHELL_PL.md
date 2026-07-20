# CRT — UI Stage 1: Engineering IDE Shell

## Cel

Pierwszy etap przebudowy wyglądu przekształca główne okno CRT w klasyczne,
kompaktowe środowisko inżynierskie podobne do IDE. Etap dotyczy wyłącznie
powłoki aplikacji i organizacji przestrzeni roboczej.

## Zakres

- klasyczne menu: `Plik`, `Widok`, `Capture`, `Analiza`, `Narzędzia`,
- kompaktowy górny toolbar z podstawowymi akcjami projektu,
- wąski pionowy Activity Bar oparty na ikonach,
- uporządkowany Explorer projektu,
- centralne zakładki robocze z menu kontekstowym,
- przesuwalne, odpinane i zwijane docki:
  - Projekt,
  - Inspektor,
  - Output,
- dolny panel `Output / Problemy / Zadania / Log CAN`,
- czytelny status projektu, bitrate, trybu i Capture,
- zapis geometrii oraz układu docków w `QSettings`,
- polecenie `Widok → Resetuj układ okna`,
- wspólny neutralny motyw QSS typu engineering workbench,
- gęstszy przegląd projektu z tabelą ostatnich sesji.

## Skróty

```text
Ctrl+B         Explorer projektu
Ctrl+Shift+I   Inspektor
Ctrl+J         Panel dolny
Ctrl+D         Filtry globalne
```

## Zachowane kontrakty

Etap nie zmienia:

- `CaptureService`,
- kodu Kvasera,
- lifecycle CANlib,
- kontrolerów Live Capture,
- kolejności pełnego zapisu ramek,
- formatu `*.crt.jsonl`,
- indeksu sesji,
- semantyki Global Filter Engine,
- dekodowania DBC, ISO-TP, J1939 ani UDS.

Nowa klasa `EngineeringShellMainWindow` dziedziczy po dotychczasowym
`StaticFilterWindowMainWindow`. Istniejące moduły są osadzane w nowej powłoce
bez przenoszenia ich logiki do warstwy GUI.

## Walidacja

Nowy smoke test `tests_gui/engineering_shell_smoke.py` sprawdza:

- użycie nowej klasy głównego okna,
- obecność menu i toolbarów,
- skróty widoków,
- strukturę Explorera,
- status bitrate i trybu,
- nowy przegląd projektu,
- zwijanie dolnego panelu,
- reset domyślnego układu.

Pełna walidacja lokalna powinna obejmować:

```powershell
python -m compileall -q app kvaser gui
python -m pytest -q

$env:QT_QPA_PLATFORM="offscreen"
python .\tests_gui\engineering_shell_smoke.py
python .\tests_gui\filter_manager_window_smoke.py
python .\tests_gui\session_management_smoke.py tree
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
```

Po smoke teście należy uruchomić GUI normalnie i ocenić proporcje docków,
czytelność toolbarów, statusu i Explorera na docelowym monitorze.
