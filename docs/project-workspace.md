# CRT Project Workspace

## Założenie

Jedna jednostka pracy CRT to jeden samodzielny folder projektu. Projekt agreguje sesje, obszary badań, znaczniki, eksperymenty, sygnały, hipotezy, dekodery, notatki i załączniki.

## Model danych

- sesja CAN jest materiałem źródłowym,
- eksperyment opisuje warunki i wykonane czynności,
- obszar badań, np. EGR lub VGT, agreguje wiedzę i odwołania,
- jedna sesja może być powiązana z wieloma obszarami bez kopiowania pliku,
- wszystkie ścieżki zapisane w projekcie są względne,
- pliki importowane są domyślnie kopiowane do projektu,
- oryginalne logi nie są modyfikowane.

## Układ GUI

```text
Activity Bar | Explorer projektu | Zakładki robocze | Inspektor
             |                    |                  |
             +--------------------+------------------+
             | Output / Problemy / Zadania           |
             +----------------------------------------+
             | Pasek statusu                          |
```

Explorer i tabele korzystają z modeli Qt. Dane ramek nie są przechowywane w drzewie projektu.

## Znaczniki

Znaczniki są definiowane przed rejestracją. Każdy ma nazwę, skrót, kolor, opcjonalny obszar i stan aktywny. W czasie logowania skrót lub przycisk zapisuje timestamp natychmiast, bez otwierania okna dialogowego.

Timestamp znacznika i ramki korzysta z `perf_counter_ns()`. Zapis na dysk odbywa się później w wątku roboczym, ale zachowuje czas z momentu reakcji operatora.

## Wydajność

- pełna sesja jest zapisywana strumieniowo,
- GUI przechowuje ograniczony bufor live,
- aktualizacje tabeli są grupowane,
- indeksowanie i import są wykonywane poza wątkiem GUI,
- otwarcie projektu ładuje tylko metadane,
- otwarcie sesji ładuje tylko potrzebną stronę ramek.
