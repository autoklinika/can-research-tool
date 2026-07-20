# Research Workspace — Etap I-A

**Gałąź:** `agent/research-workspace-stage-i-a`  
**Baza:** `main` po konsolidacji architektury, analizy protokołów, filtrów i Etapu H  
**Status:** rozpoczęty

## Cel

Etap I-A rozwija istniejący model `StudyArea` w użyteczny moduł organizacji badań. Użytkownik ma móc tworzyć obszary badań, edytować ich opis oraz przypisywać i odpinać zapisane sesje bez modyfikowania danych źródłowych sesji.

Przykładowe obszary:

- komunikacja EGR,
- VGT i sterowanie nastawnikiem,
- diagnostyka UDS ETC3,
- analiza J1939 DM1/DM2,
- badanie konkretnego ECU.

## Zakres I-A

### Zarządzanie obszarami badań

- tworzenie obszaru,
- zmiana nazwy i opisu,
- usuwanie obszaru po potwierdzeniu,
- lista obszarów w Explorerze projektu,
- otwieranie jednego widoku obszaru w centralnej zakładce.

### Powiązanie sesji

- przypisanie jednej lub wielu istniejących sesji do obszaru,
- odpięcie sesji bez usuwania jej z projektu,
- możliwość przypisania jednej sesji do wielu obszarów,
- widoczny stan sesji: `recording`, `ready`, `error` lub inny stan zapisany w projekcie,
- otwarcie powiązanej sesji z widoku obszaru.

### Podsumowanie obszaru

- liczba powiązanych sesji,
- łączna liczba ramek,
- łączny czas rejestracji,
- liczba markerów,
- zakres dat badań,
- jasny komunikat dla pustego obszaru.

## Poza zakresem

Do kolejnych etapów pozostają:

- I-B: eksperymenty, cele, warunki stanowiskowe, wyniki i notatki,
- I-C: porównywanie sesji, częstotliwości, CAN ID, PGN, UDS i okien wokół markerów,
- edytor hipotez i autorskich sygnałów,
- aktywna transmisja CAN.

## Nienaruszalne kontrakty

- brak zmian w `CaptureService`,
- brak zmian w Kvaserze i lifecycle CANlib,
- brak zmian w formacie `*.crt.jsonl`,
- brak modyfikacji surowych ramek i plików źródłowych sesji,
- przypisanie do obszaru jest wyłącznie metadanymi projektu,
- istniejące projekty muszą otwierać się po zmianach bez ręcznej migracji użytkownika,
- usunięcie obszaru nie może usuwać sesji ani plików.

## Plan implementacji

1. Rozszerzyć repozytorium projektu o bezpieczne operacje CRUD dla `StudyArea`.
2. Dodać jawne operacje przypisywania i odpinania sesji.
3. Dodać kontroler widoku obszaru badań, zamiast wykonywać zapytania bezpośrednio w widżecie.
4. Rozbudować `StudyAreaViewWidget` o edycję, listę sesji i podsumowanie.
5. Podłączyć odświeżanie Explorera po zmianie obszarów.
6. Dodać testy domenowe, projektowe i GUI smoke.

## Kryteria akceptacji

- nowy obszar pojawia się w Explorerze bez restartu aplikacji,
- nazwę i opis można zmienić i są zachowane po ponownym otwarciu projektu,
- sesję można przypisać i odpiąć,
- jedna sesja może należeć do kilku obszarów,
- usunięcie obszaru pozostawia sesje i ich pliki nietknięte,
- podsumowania odpowiadają rekordom zapisanym w projekcie,
- projekty utworzone przed I-A otwierają się poprawnie,
- pełne testy i regresje GUI pozostają zielone.
