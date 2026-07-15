# Global Filter Engine — Etap 1

## Cel

Etap 1 tworzy niezależny od GUI fundament wspólnego silnika filtrów CRT. Ten sam model ma być używany przez Live Capture, zapisane sesje, analizę i eksport. Filtr nigdy nie ogranicza zapisu surowych ramek CAN.

## Zakres implementacji

Pierwsza wersja obsługuje:

- drzewo logiczne `AND`, `OR`, `NOT`,
- wynik trójstanowy `MATCH`, `NO_MATCH`, `UNAVAILABLE`,
- warunki numeryczne dla CAN ID, STD/EXT, DLC i czasu względnego,
- operatory porównania, zakresy i zbiory,
- walidację pustych grup, reguły `NOT`, liczby argumentów i limitu zagnieżdżenia,
- kompilację definicji filtra do predykatu wykonawczego,
- wspólny `FilterContext` przygotowany do rozszerzenia o DBC, markery i historię,
- testy jednostkowe bez zależności zewnętrznych.

## Główne typy

- `FilterPreset` — trwała definicja filtra projektu.
- `FilterNode` — wariant grupy lub warunku.
- `FilterGroup` — operator logiczny i lista dzieci.
- `FilterCondition` — pojedynczy warunek.
- `FilterCompiler` — waliduje i kompiluje model.
- `CompiledFilter` — wydajny predykat wykonywany dla rekordów.
- `FilterContext` — dostępne dane wejściowe.
- `FilterResult` — wynik oraz przyczyna `UNAVAILABLE`.

## Semantyka UNAVAILABLE

`UNAVAILABLE` oznacza, że warunku nie można ocenić, ponieważ w kontekście brakuje wymaganego pola. Na tym etapie brak rekordu CAN daje `UNAVAILABLE`.

Zachowanie grup:

- `AND`: natychmiast zwraca `NO_MATCH`, gdy dowolne dziecko nie pasuje; w pozostałych przypadkach obecność niedostępnego dziecka daje `UNAVAILABLE`.
- `OR`: natychmiast zwraca `MATCH`, gdy dowolne dziecko pasuje; w pozostałych przypadkach obecność niedostępnego dziecka daje `UNAVAILABLE`.
- `NOT`: odwraca `MATCH` i `NO_MATCH`; zachowuje `UNAVAILABLE`.

Warstwa używająca silnika może traktować `UNAVAILABLE` jako brak dopasowania, ale powinna pokazać ostrzeżenie użytkownikowi.

## Proponowany zapis JSON w project.sqlite

```json
{
  "formatVersion": 1,
  "id": "egr-change-filter",
  "name": "EGR — zmiany po odłączeniu",
  "description": "Przykładowy preset projektu",
  "enabled": true,
  "mode": "include",
  "scope": ["liveCapture", "storedSession"],
  "shortcut": "Ctrl+1",
  "root": {
    "type": "group",
    "operator": "and",
    "children": [
      {
        "type": "condition",
        "id": "can-id",
        "label": "CAN ID",
        "field": "can.id",
        "operator": "equal",
        "values": [419343920]
      },
      {
        "type": "condition",
        "id": "dlc",
        "label": "DLC",
        "field": "can.dlc",
        "operator": "equal",
        "values": [8]
      }
    ]
  }
}
```

Serializacja nie jest jeszcze częścią kodu wykonawczego. Schemat jest wersjonowany od początku, aby późniejsze migracje nie wymagały zmiany modelu domenowego.

## Integracja

```cpp
FilterCompiler compiler;
ValidationResult validation;
auto compiled = compiler.compile(preset, &validation);

if (compiled) {
    const FilterResult result = compiled->evaluate(FilterContext{&frame});
}
```

W Live Capture kompilacja powinna następować tylko po zmianie definicji filtra. Każda ramka korzysta następnie z gotowego `CompiledFilter`. Model Qt nie powinien otrzymywać sygnału dla pojedynczej ramki; wyniki powinny być przekazywane paczkami.

## Następny etap

1. Wersjonowana serializacja JSON i migracje.
2. Kompozycja wielu aktywnych presetów w trybie AND/OR.
3. Tryby Include, Exclude i Highlight na poziomie orkiestratora.
4. Pola kanału, RTR, error frame, maski CAN ID i payload.
5. Jawny interfejs dla warunków stateful.
6. Adaptery dla Live Capture i zapisanych sesji.
