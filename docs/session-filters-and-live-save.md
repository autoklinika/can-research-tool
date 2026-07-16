# Filtrowanie zapisanych sesji i świadomy zapis Live Capture

## Zapisane sesje

Zakładka zapisanej sesji korzysta z tych samych aktywnych presetów projektu co Live Capture.

- `Include` ogranicza widok do dopasowanych ramek.
- `Exclude` usuwa dopasowane ramki z widoku.
- `Highlight` nie ogranicza liczby rekordów; kolorowanie będzie rozwijane osobno.
- plik `*.crt.jsonl` nigdy nie jest modyfikowany przez filtr.
- zmiana presetu w zakładce `Filtry` automatycznie uruchamia ponowne przeliczenie otwartych sesji.

Przy aktywnym filtrze zapisany log jest skanowany w zadaniu `QThreadPool`. W pamięci pozostaje tylko ostatnie 20 000 dopasowanych ramek, natomiast GUI pokazuje liczbę dopasowań w całej sesji. Etap indeksowego planowania zapytań pozostaje częścią późniejszej optymalizacji dużych logów.

## Live Capture bez automatycznego zapisu

Live Capture domyślnie działa jako podgląd tymczasowy:

```text
Start bez uzbrojenia zapisu
  -> odbiór Kvaser
  -> pełny ograniczony bufor GUI
  -> dekodowanie wiadomości
  -> brak plików sesji, CSV i markerów
```

Aby zapisać sesję, użytkownik musi przed `Start` kliknąć przycisk:

```text
Zapisz sesję: NIE -> Zapisz sesję: UZBROJONY
```

Dopiero wtedy następne uruchomienie tworzy:

- `*.crt.jsonl`,
- `*.crt.jsonl.idx.json`,
- `*.frames.csv`,
- `*.messages.csv`,
- `*.markers.jsonl`,
- wpis sesji w `.crt/project.sqlite`.

Uzbrojenie zapisu jest jednorazowe. Po zakończeniu sesji przycisk automatycznie wraca do stanu `NIE`, dzięki czemu każda kolejna rejestracja wymaga świadomej decyzji użytkownika.

Filtry Live nadal działają wyłącznie na widoku. Gdy zapis jest uzbrojony, na dysk trafia pełny strumień niezależnie od aktywnych filtrów.
