# Global Filter Engine — Etap 2B: integracja z CRT

## Cel

Etap 2B usuwa zależność od osobnej aplikacji demonstracyjnej i osadza stronę filtrów w pierwszym właściwym shellu CAN Research Tool.

## Dodane elementy

- główny target aplikacji `crt_app`,
- główne okno CRT,
- lewy pasek aktywności,
- strony Live Capture, Sesje, Filtry, Analiza i Ustawienia,
- działająca nawigacja do strony Filtry,
- jeden współdzielony `FilterPresetStore` rejestrowany przy uruchomieniu CRT,
- komunikat `Zapis: wszystkie ramki` na stronie filtrów,
- zapis presetów w katalogu danych CRT.

## Uruchomienie

```bash
cmake -S . -B build -DCRT_BUILD_APP=ON
cmake --build build
./build/crt_app
```

Na generatorach wielokonfiguracyjnych aplikacja może znajdować się w `build/Debug/crt_app.exe`.

## Granice etapu

Repozytorium nie zawierało wcześniej kompletnego głównego GUI CRT. Ten etap tworzy minimalny, docelowo rozszerzalny shell zamiast integrować filtry z nieistniejącą nawigacją.

Live Capture i zapisane sesje są obecnie stronami zastępczymi. Podłączenie prawdziwych modeli ramek, liczników wszystkich/widocznych danych i filtrowania w czasie rzeczywistym pozostaje zakresem Etapu 3.
