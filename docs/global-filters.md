# Global Filter Engine — fundament Python/PySide6

Moduł jest zintegrowany z właściwą aplikacją CRT uruchamianą przez `python .\crt_gui.py`.

## Zakres tej iteracji

- pozycja `Filtry` na pionowym pasku aktywności i w menu `Widok`,
- centralna zakładka menedżera presetów,
- model drzewa `AND`, `OR`, `NOT`,
- wyniki `MATCH`, `NO_MATCH`, `UNAVAILABLE`,
- warunki `CAN ID`, `STD/EXT`, `DLC` i czas względny,
- tryby `include`, `exclude`, `highlight`,
- walidacja drzewa i wartości,
- testowanie presetu na ręcznie zdefiniowanej ramce,
- zapis wersjonowanego JSON w `.crt/project.sqlite`,
- kontrola unikalności aktywnych skrótów filtrów.

## Gwarancja zapisu

Menedżer filtrów nie jest podłączony do toru zapisu sesji. Surowy strumień nadal trafia w całości do plików sesji. Widok stale pokazuje komunikat:

```text
Zapis: wszystkie ramki
```

## Tabela projektu

Presety są przechowywane w tabeli `filter_presets`. Definicja drzewa znajduje się w `tree_json`, a zakres zastosowania w `scope_json`. Schemat jest tworzony przez `ProjectFilterRepository` przy pierwszym otwarciu modułu filtrów.

## Następny etap

Kolejny etap podłączy skompilowane aktywne presety do modeli `LiveCaptureWidget` i `SessionViewWidget`. Filtrowany będzie wyłącznie model GUI oraz materiał wejściowy analiz i eksportu — nigdy strumień zapisywany na dysku.
