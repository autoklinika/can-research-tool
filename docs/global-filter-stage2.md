# Global Filter Engine — Etap 2

Etap 2 dodaje warstwę projektu i pierwszy interfejs Qt/QML nad silnikiem z Etapu 1.

## Zakres

- `FilterPresetStore` jako `QAbstractListModel` dostępny z QML,
- tworzenie, usuwanie, aktywowanie i nazywanie presetów,
- przypisywanie skrótów klawiszowych,
- wersjonowany zapis i odczyt JSON,
- rekurencyjna serializacja grup `AND`, `OR`, `NOT` i warunków,
- walidacja przez rzeczywisty `FilterCompiler`,
- testowanie presetu na ręcznie wprowadzonej ramce CAN,
- ekran menedżera presetów i pierwsza wizualizacja drzewa,
- opcjonalny target Qt; sam silnik nadal buduje się bez Qt.

## Uruchomienie

Wymagane jest Qt 6.5 lub nowsze z modułami Core, Gui, Qml, Quick i Quick Controls 2.

```bash
cmake -S . -B build -DCRT_BUILD_FILTER_EDITOR=ON
cmake --build build
./build/crt_filter_editor
```

Plik presetów demonstratora jest zapisywany w katalogu danych aplikacji jako `filter-presets.json`. Docelowa integracja CRT przeniesie tę warstwę do `.crt/project.sqlite`, zachowując ten sam wersjonowany dokument JSON.

## Granica Etapu 2

Interfejs nie filtruje jeszcze prawdziwego strumienia Kvaser. Połączenie z modelem Live Capture, aktualizacja liczników wszystkich/widocznych rekordów i natychmiastowe przełączanie widoku należą do Etapu 3.

Pierwszy ekran pokazuje strukturę drzewa i pozwala zarządzać presetami. Pełne operacje przeciągania, zagnieżdżania i edycji dowolnej gałęzi wymagają dedykowanego modelu drzewa Qt i pozostają następnym rozwinięciem GUI.
