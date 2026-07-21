# CRT Extension API Foundation — Stage 2

## Status

Drugi krok fundamentu architektonicznego CRT, oparty na modelu domenowym i
migracjach z `DOMAIN_EXTENSION_FOUNDATION_STAGE1_PL.md`.

Etap przygotowuje stabilne granice dla przyszłych filtrów, analiz, wzorców,
dekoderów, porównań i eksporterów. Nie dodaje jeszcze funkcji analitycznej do
normalnego GUI.

## Extension Manifest v1

Każde rozszerzenie deklaruje:

- stabilny identyfikator,
- nazwę,
- SemVer modułu,
- wersję API rozszerzeń CRT,
- typ rozszerzenia,
- obsługiwane wejścia,
- typy wyników,
- obsługę Live,
- zależność od AI,
- zależność od CAN TX,
- wymagane uprawnienia.

Manifest jest walidowany rygorystycznie. Nieprawidłowe typy JSON, powtórzone
wejścia, niespójne uprawnienia lub niepoprawna wersja są odrzucane przed
rejestracją providera.

Wersja API tego etapu:

```text
CRT_EXTENSION_API_VERSION = "1"
```

## Jawny Extension Registry

`ExtensionRegistry` przyjmuje wyłącznie provider przekazany jawnie przez kod
CRT.

W tym etapie rejestr:

- nie skanuje katalogów,
- nie importuje kodu z projektu ECU,
- nie instaluje zależności,
- nie wykonuje entrypointów z plików manifestu,
- odrzuca powtórzone ID,
- odrzuca niezgodną wersję API,
- zapisuje kontrolowane błędy `try_register`,
- pozwala wyszukiwać capabilities według typu i rodzaju wejścia.

Jest to świadome ograniczenie pierwszej wersji. Dynamiczne ładowanie może
zostać dodane dopiero po utrwaleniu polityki zaufania, zależności i izolacji
procesowej.

## Polityka pasywnego runtime

Domyślny registry działa jako `passive_only=True` oraz `ai_enabled=False`.

Dozwolone uprawnienia:

```text
project.read
session.read
artifact.write
finding.write
```

Odrzucane są:

```text
can.tx
ai.use
```

Manifest `requires_can_tx=true` nie może zostać zarejestrowany w pasywnym
runtime. AI pozostaje wyłączone. Typy przyszłych rozszerzeń mogą być opisane w
modelu, ale nie omijają polityki wykonawczej.

## Read-only ProjectContext

Provider analizy otrzymuje `ProjectContext`, a nie `CrtProject`, połączenie
SQLite, kontroler GUI, CaptureService ani obiekt Kvasera.

Publiczny kontrakt udostępnia:

- `project_id`,
- `project_name`,
- listę sesji,
- wybór sesji po ID,
- metadane sesji,
- `FrameQuery`.

`FrameQuery` korzysta z istniejącego `SessionPagedReader` i zapewnia:

- liczbę ramek,
- ograniczony odczyt strony,
- odczyt ramki po `source_row`,
- strumieniową iterację,
- okresowe sprawdzanie anulowania.

Nie posiada metody zapisu. Nie udostępnia `SessionStreamWriter`.

## CancellationToken i ProgressReporter

Każda analiza otrzymuje wspólny `CancellationToken`. Kontrakt może przerwać:

- odczyt sesji,
- zapis artefaktu przed atomową publikacją,
- wykonanie providera przez `ExtensionRunner`.

`ProgressReporter` zapisuje ostatni postęp, odrzuca wartości ujemne i cofanie
postępu w obrębie tego samego totalu oraz opcjonalnie wywołuje callback GUI.

Ten etap nie wiąże callbacku z Qt.

## Atomowy ArtifactWriter

Rozszerzenie nie zapisuje pliku wynikowego bezpośrednio.

`ArtifactWriter`:

1. dopuszcza tylko bezpieczną pojedynczą nazwę pliku,
2. zapisuje dane do unikalnego pliku tymczasowego,
3. wykonuje flush i `fsync`,
4. ponownie sprawdza anulowanie,
5. atomowo zastępuje ścieżkę docelową,
6. oblicza SHA-256,
7. rejestruje artefakt i źródła w `project.sqlite`,
8. usuwa plik docelowy, jeżeli rejestracja metadanych się nie powiedzie,
9. zawsze usuwa plik tymczasowy.

Pliki trafiają wyłącznie do:

```text
artifacts/<analysis_run_id>/
```

Nie są zapisywane w `sessions/` ani `.crt/indexes/`.

## FindingWriter

`FindingWriter` jest kontrolowaną fasadą do `ProjectDomainStore`. Znalezisko:

- wymaga dowodu,
- zachowuje algorytm i wersję,
- przechodzi walidację referencji,
- nie może zmodyfikować sesji.

## ExtensionRunner

`ExtensionRunner` stanowi granicę wyjątków providera.

Przepływ:

```text
pending -> running -> completed
                   -> failed
                   -> cancelled
```

Wyjątek providera:

- ustawia uruchomienie analizy na `failed`,
- zapisuje komunikat błędu,
- jest opakowany w `ExtensionExecutionError`,
- nie zatrzymuje CaptureService,
- nie modyfikuje surowych danych.

Anulowanie otrzymuje osobny status i wyjątek `ExtensionCancelled`.

## Provider referencyjny

Provider referencyjny istnieje tylko w testach. Nie jest rejestrowany w
normalnym GUI.

Testowy przepływ:

1. pobiera sesję przez `ProjectContext`,
2. odczytuje pierwszą ramkę przez `FrameQuery`,
3. raportuje postęp,
4. zapisuje atomowy artefakt JSON,
5. tworzy znalezisko wskazujące artefakt,
6. kończy analizę statusem `completed`.

## Testy bezpieczeństwa i zgodności

Testy obejmują:

- round-trip manifestu JSON,
- rygorystyczną walidację pól,
- odrzucenie duplikatu ID,
- odrzucenie `can.tx`,
- odrzucenie niezgodnego API,
- filtrowanie capabilities,
- read-only odczyt sesji,
- pełny przebieg providera referencyjnego,
- atomowy artefakt i poprawny SHA-256,
- znalezisko z dowodem,
- izolację wyjątku providera,
- status `failed`,
- anulowanie przed zapisem,
- usuwanie pliku po błędzie rejestracji metadanych,
- brak plików tymczasowych,
- identyczny SHA-256 sesji przed i po analizie.

## Chronione kontrakty

Etap nie zmienia:

- `CaptureService`,
- backendu Kvaser,
- lifecycle CANlib,
- formatu `*.crt.jsonl`,
- formatu indeksu sesji,
- kolejności i kompletności zapisu ramek,
- filtrów i grupowania GUI,
- aktualnych dekoderów,
- funkcji aktywnych,
- AI.

## Granica zaufania

Stage 2 tworzy stabilne API dla jawnie zaufanych providerów działających w tym
samym procesie Pythona. Nie jest jeszcze sandboxem bezpieczeństwa dla
niezaufanego kodu.

Przed obsługą zewnętrznych paczek należy zaprojektować co najmniej:

- podpisy lub listę zaufanych źródeł,
- kontrolę zależności,
- osobny proces wykonawczy,
- limity pamięci i czasu,
- protokół IPC,
- wersjonowane migracje providerów.

## Następny etap

Pierwszym rzeczywistym modułem korzystającym z tego API powinny być pasywne,
deterministyczne statystyki pojedynczej sesji:

- liczba ramek,
- liczba CAN ID,
- liczba STD/EXT,
- liczba kanałów,
- czas trwania,
- podstawowa częstotliwość per ID.

Wynik musi zostać zapisany jako wersjonowany artefakt przez `ArtifactWriter`, a
nie jako jednorazowe okno GUI.
