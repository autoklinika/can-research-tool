# CRT Project Workspace

## Zasady trwałości

1. Jeden projekt CRT jest jednym samodzielnym folderem.
2. Wszystkie ścieżki zapisane w indeksie projektu są względne.
3. Surowe sesje i oryginalne pliki są źródłem prawdy.
4. Dekodery, tagi, relacje, hipotezy i notatki tworzą dodatkowe warstwy interpretacji.
5. Wyłączenie dekodera nie może zmieniać ani usuwać danych źródłowych.

## Układ folderów

```text
project/
├─ project.crt.json
├─ .crt/
│  ├─ project.sqlite
│  └─ indexes/
├─ sessions/
│  ├─ live/
│  └─ imported/
│     └─ source/
├─ experiments/
├─ notes/
├─ attachments/
├─ decoders/
│  └─ dbc/
├─ exports/
└─ reports/
```

## Model danych

- **Sesja CAN** jest niezmiennym materiałem źródłowym.
- **Eksperyment** opisuje warunki, wykonane czynności, znaczniki i wynik testu.
- **Obszar badań**, np. EGR lub VGT, agreguje wiedzę i odwołania.
- Jedna sesja może być powiązana z wieloma eksperymentami i obszarami bez kopiowania pliku.
- Pliki importowane są domyślnie kopiowane do projektu.
- Oryginalne logi nie są modyfikowane.

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

Definicje znaczników należą do projektu. Konfigurację otwiera kafelek `Znaczniki` w sekcji `Połączenie i sesja` zakładki `Live Capture`.

Każdy znacznik ma nazwę, skrót, kolor, opcjonalny obszar i stan aktywny. Podczas rejestracji GUI pokazuje tylko aktywne przyciski i skróty. Timestamp powstaje natychmiast przy zdarzeniu z `perf_counter_ns()`, a zapis na dysk odbywa się asynchronicznie.

## Dekodery DBC

Pliki DBC są zarządzane w centralnej zakładce `Dekodery`, a nie w ustawieniach połączenia. Import:

1. waliduje DBC przez `cantools`,
2. kopiuje plik do `decoders/dbc`,
3. zapisuje względną ścieżkę, SHA-256 i liczbę wiadomości w `project.sqlite`,
4. domyślnie ustawia plik jako aktywny.

Każdy DBC można wyłączyć checkboxem bez usuwania. Aktywne DBC tworzą odwracalną nakładkę na wiadomości `RAW`:

```text
RAW + aktywny DBC   → DBC message + signals
RAW + wyłączony DBC → UNKNOWN / bazowy dekoder
```

Gdy kilka aktywnych plików definiuje ten sam CAN ID i typ ramki, pierwszy plik w kolejności projektu ma pierwszeństwo. Zmiana aktywności przeładowuje widok zapisanych sesji. Trwający capture zachowuje zestaw dekoderów wybrany przy `Start`, aby interpretacja nie zmieniała się w połowie rejestracji.

## Wydajność

- pełna sesja jest zapisywana strumieniowo,
- GUI przechowuje ograniczony bufor live,
- aktualizacje tabel są grupowane,
- indeksowanie, import i rekonstrukcja wiadomości są wykonywane poza wątkiem GUI,
- otwarcie projektu ładuje tylko metadane,
- otwarcie sesji ładuje tylko potrzebną stronę ramek i ograniczony zestaw wiadomości.
