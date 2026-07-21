# CRT — Session Statistics Provider — Stage 3

## 1. Cel etapu

Stage 3 jest pierwszym rzeczywistym modułem analitycznym zbudowanym na `Extension API Foundation`.

Moduł wykonuje deterministyczną, pasywną analizę jednej zapisanej sesji surowych ramek i zapisuje wynik jako trwały, wersjonowany artefakt JSON.

Etap nie dodaje GUI, CAN Intelligence, AI ani funkcji aktywnych.

## 2. Gałąź i zależność

Gałąź:

```text
agent/session-statistics-provider-stage3
```

Baza:

```text
agent/extension-api-foundation-stage2
```

Stage 3 jest stacked na PR #27 i wymaga kontraktów dodanych w PR #26 oraz PR #27.

## 3. Provider

Identyfikator:

```text
crt.analysis.session_statistics
```

Wersje:

```text
provider: 1.0.0
algorithm: 1
CRT extension API: 1
artifact schema: 1
```

Manifest deklaruje:

- typ `analysis`,
- wejście `session`,
- wyjście `session_statistics`,
- `project.read`,
- `session.read`,
- `artifact.write`,
- brak AI,
- brak CAN TX,
- brak obsługi Live Capture.

## 4. Jawna rejestracja

Dodano katalog:

```text
app/extensions/builtin/
```

`builtin_analysis_providers()` zwraca zaufane moduły należące do CRT.

`register_builtin_extensions(registry)` rejestruje je jawnie w przekazanym `ExtensionRegistry`.

Import pakietu nie uruchamia globalnej rejestracji, nie skanuje folderów i nie ładuje kodu z projektu ECU.

## 5. Zakres statystyk

Artefakt zawiera:

- identyfikację providera, algorytmu i schematu,
- identyfikację projektu oraz sesji,
- parametry wejściowe analizy,
- deklarowaną i zaobserwowaną liczbę ramek,
- SHA-256 sesji źródłowej,
- całkowitą liczbę ramek i bajtów payloadu,
- liczbę ramek data, remote i error,
- liczbę ramek standardowych i extended,
- liczbę unikalnych arbitration ID,
- liczbę unikalnych kluczy wiadomości,
- pierwszy i ostatni sequence,
- pierwszy, ostatni, minimalny i maksymalny timestamp,
- zakres timestampów,
- rozkład ramek według kanałów,
- rozkład DLC,
- statystyki osobno dla każdego klucza wiadomości.

Klucz wiadomości obejmuje:

```text
channel + arbitration_id + is_extended_id + is_remote_frame + is_error_frame
```

Dzięki temu ramki data, remote i error nie są łączone tylko dlatego, że używają tego samego CAN ID.

## 6. Statystyki czasowe

Dla całej sesji oraz każdego klucza wiadomości raportowane są:

- liczba interwałów,
- liczba interwałów dodatnich,
- liczba interwałów zerowych,
- liczba interwałów ujemnych,
- minimalny dodatni interwał,
- maksymalny dodatni interwał,
- średni dodatni interwał,
- odchylenie standardowe populacji dla dodatnich interwałów,
- częstotliwość wynikająca ze średniego dodatniego interwału.

Interwały zerowe i ujemne są raportowane jako anomalie danych czasowych i nie są używane do obliczania częstotliwości.

Provider nie koryguje i nie porządkuje timestampów źródłowych.

## 7. Determinizm

Artefakt nie zawiera:

- czasu wykonania analizy,
- identyfikatora `analysis_run`,
- losowych wartości,
- danych zależnych od GUI lub środowiska wykonawczego.

Dla tej samej sesji, tych samych parametrów i tych samych wersji provider/algorytm wynik JSON ma identyczną treść i SHA-256.

Elementy kolekcji są sortowane deterministycznie:

- kanały numerycznie,
- DLC numerycznie,
- wiadomości według kanału, formatu ID, arbitration ID oraz typu ramki.

## 8. Pochodzenie danych

Artefakt jest zapisywany jako:

```text
artifacts/<analysis_run_id>/session-statistics.json
```

`ArtifactSource` wskazuje całą sesję poprzez:

```text
source_kind = session
session_id
frame_count
sha256
```

Plik jest tworzony wyłącznie przez atomowy `ArtifactWriter`.

Provider nie posiada API zapisu do sesji, indeksu sesji ani Live Capture.

## 9. Obsługa pustych i wadliwych danych

Pusta sesja tworzy poprawny artefakt:

- `frame_count = 0`,
- puste rozkłady,
- pusta lista wiadomości,
- brak sztucznie wyliczonej częstotliwości,
- timestampy i zakres jako `null`.

Nieciągłe timestampy nie przerywają analizy. Provider zapisuje liczbę interwałów zerowych i ujemnych.

Provider odrzuca wejście inne niż dokładnie jedna sesja. `ExtensionRunner` ustawia wtedy `analysis_run` na `failed`, bez utworzenia artefaktu.

## 10. Postęp i anulowanie

Provider korzysta z `CancellationToken` podczas iteracji po ramkach.

Postęp jest raportowany:

- przed rozpoczęciem odczytu,
- okresowo co 4096 ramek,
- po odczytaniu ostatniej ramki,
- po atomowym zapisaniu artefaktu.

Anulowanie jest obsługiwane przez istniejący `ExtensionRunner` i `ArtifactWriter`.

## 11. Testy

Dodano testy obejmujące:

- jawną rejestrację built-in providera,
- manifest i dostęp przez `ExtensionRegistry`,
- mieszaną sesję standard/extended/data/remote/error,
- rozkład kanałów i DLC,
- statystyki per-ID,
- interwały i częstotliwość,
- trwałość artefaktu i jego źródła,
- brak automatycznego tworzenia findings,
- identyczny wynik i SHA-256 przy ponownym uruchomieniu,
- niezmienność SHA-256 sesji źródłowej,
- pustą sesję,
- timestampy zerowe i malejące,
- odrzucenie wielu sesji,
- zmianę statusu niepoprawnego uruchomienia na `failed`.

## 12. Zachowane kontrakty

Etap nie zmienia:

- `CaptureService`,
- backendu Kvaser,
- lifecycle CANlib,
- formatu sesji,
- formatu indeksu sesji,
- `SessionStreamWriter`,
- `SessionPagedReader`,
- kolejności ani kompletności zapisu ramek,
- filtrów,
- dekoderów,
- wyszukiwania,
- GUI.

## 13. Poza zakresem

Stage 3 nie obejmuje:

- wykorzystania magistrali na podstawie bitrate,
- estymacji obciążenia bitowego CAN/CAN FD,
- grupowania logicznych wiadomości ISO-TP/J1939,
- porównywania wielu sesji,
- detekcji wzorców,
- automatycznego tworzenia hipotez,
- CAN Intelligence,
- AI,
- replay i CAN TX,
- integracji z menu aplikacji.

## 14. Następny bezpieczny krok

Po walidacji Stage 3 można dodać warstwę aplikacyjną uruchamiającą providery dla zapisanej sesji oraz widok artefaktów, bez przenoszenia logiki algorytmu do GUI.

Alternatywnym kolejnym etapem analitycznym jest provider porównania dwóch lub większej liczby artefaktów `session_statistics` poprzez istniejący model `ComparisonSet`.
