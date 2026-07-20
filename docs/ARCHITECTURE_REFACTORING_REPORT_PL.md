# CAN Research Tool — raport architektury i wytyczne do refaktoryzacji

**Data:** 2026-07-16  
**Repozytorium:** `autoklinika/can-research-tool`  
**Gałąź:** `agent/protocol-analysis-stage5`  
**PR:** #10  
**Cel dokumentu:** przekazanie kompletnego kontekstu do rozpoczęcia osobnego etapu poprawy architektury aplikacji bez naruszenia stabilnego odbioru CAN, zapisu sesji i istniejących funkcji analitycznych.

---

## 1. Wniosek ogólny

Aplikacja jest obecnie **warstwowa pod względem przepływu danych i wykonania**, ale nie jest jeszcze w pełni warstwowa pod względem organizacji kodu oraz zależności między klasami.

Najważniejszy sukces obecnej architektury:

- odbiór Kvasera jest odizolowany od GUI, filtrów, dekoderów i zapisu plików,
- filtrowanie nie wpływa na fizyczny odbiór CAN,
- filtrowanie nie ogranicza pełnego zapisu sesji,
- pauza widoku nie zatrzymuje odbioru ani zapisu,
- zmiany prezentacji danych nie powinny wpływać na CANlib,
- dekodowanie protokołów odbywa się po odebraniu i zapisaniu surowej ramki.

Największy problem obecnej architektury:

- `LiveCaptureWidget` zna zbyt wiele szczegółów warstw niższych,
- część funkcji GUI jest dokładana przez runtime patching klas,
- kolejność instalowania modułów integracyjnych ma znaczenie,
- granice odpowiedzialności pomiędzy kontrolerem, serwisem, modelem i widokiem nie są jeszcze jawne.

Refaktoryzacja powinna poprawić organizację kodu, ale **nie może zmienić kolejności ani niezależności krytycznego toru odbioru danych**.

---

## 2. Obecny przepływ danych

```text
Kvaser / CANlib
      │
      ▼
dedykowany wątek odbiorczy Kvasera
      │
      ▼
nieograniczona kolejka ramek w pamięci
      │
      ▼
CaptureService — worker rejestracji
      ├── zapis *.crt.jsonl
      ├── zapis *.frames.csv
      ├── bufor surowych ramek Live
      ├── StreamingTransportPipeline
      │      ├── RAW
      │      ├── ISO-TP
      │      ├── J1939 BAM
      │      └── J1939 RTS/CTS
      ├── ProtocolRegistry
      │      ├── UDS
      │      ├── J1939
      │      └── UNKNOWN
      ├── zapis *.messages.csv
      └── bufor wiadomości logicznych Live
                │
                ▼
GUI pobiera okresowe snapshoty
      ├── FrameTableModel
      ├── LogicalMessageTableModel
      ├── opcjonalna interpretacja DBC
      └── QSortFilterProxyModel / filtry widoku
                │
                ▼
              tabele
```

---

## 3. Co jest już zrobione prawidłowo

### 3.1. Izolowany odbiornik Kvasera

`KvaserPassiveChannel` posiada dedykowany wątek producenta. Ten sam wątek:

- otwiera kanał CANlib,
- ustawia tryb `NORMAL` lub `SILENT`,
- ustawia bitrate,
- wykonuje `busOn()`,
- nieprzerwanie wykonuje `read(timeout=1)`,
- kopiuje ramki do kolejki aplikacji,
- wykonuje `busOff()` i zamyka kanał.

Żaden inny wątek aplikacji nie korzysta bezpośrednio z uchwytu CANlib.

To rozwiązuje wcześniejszy problem, w którym odbiór działał inaczej niż samodzielny monitor Kvasera. Obecne zachowanie zostało potwierdzone testami i testem użytkownika.

### 3.2. Kolejka pomiędzy CANlib i analizą

Ramki usunięte z kolejki sterownika trafiają do kolejki procesu. Dzięki temu:

- zapis na dysk nie blokuje bezpośrednio `channel.read()`,
- dekodowanie ISO-TP/J1939 nie blokuje bezpośrednio CANlib,
- filtry nie blokują bezpośrednio CANlib,
- aktualizacja GUI nie blokuje bezpośrednio CANlib.

Obecna kolejka jest nieograniczona. Jest to bezpieczne pod względem chwilowych opóźnień konsumenta, ale wymaga później kontrolowanego monitoringu zużycia pamięci.

### 3.3. Oddzielenie pełnego zapisu od bufora GUI

Pełny zapis sesji i bufor widoku są niezależne.

Bufory GUI mają obecnie pojemności:

- `250 000` surowych ramek,
- `100 000` wiadomości logicznych.

Przekroczenie pojemności usuwa najstarsze rekordy wyłącznie z widoku. Nie usuwa ich z zapisanego pliku sesji.

### 3.4. Kolejność obsługi ramki w CaptureService

Dla każdej odebranej ramki wykonywana jest kolejność:

1. pobranie ramki z kanału,
2. normalizacja czasu,
3. zapis do `*.crt.jsonl`, jeśli zapis jest włączony,
4. zapis do `*.frames.csv`, jeśli zapis jest włączony,
5. dodanie do kolejki publikacji Live,
6. przekazanie do transport pipeline,
7. dekodowanie wiadomości logicznej,
8. zapis do `*.messages.csv`,
9. publikacja wiadomości logicznej do bufora Live.

Oznacza to, że błędna interpretacja protokołu nie powinna uszkodzić ani ograniczyć surowego zapisu.

### 3.5. Filtry jako warstwa widoku

`ActiveFilterSet` nie uczestniczy w torze odbioru ani zapisu. Filtry sterują:

- widocznością wierszy `Include`/`Exclude`,
- przyszłym lub częściowym wyróżnianiem `Highlight`,
- prezentacją zapisanych sesji.

Dla Live filtr jest nakładany jako proxy na pełny model źródłowy. Źródłowy model nadal posiada wszystkie ramki zachowane w buforze GUI.

### 3.6. Filtrowanie poza wątkiem GUI

Pełne przeliczenie dużego bufora Live odbywa się w `QThreadPool` na niezmiennym snapshotcie ramek. Po zakończeniu GUI wykonuje szybkie sprawdzenie obecności numeru sekwencji w zbiorze wyników.

Podczas przeliczania pełny bufor pozostaje widoczny. Wyniki spóźnionego zadania są odrzucane przez numer generacji.

### 3.7. Zakresy filtrów

Preset może być przypisany do:

- `live`,
- `stored_session`.

Preset przeznaczony wyłącznie dla zapisanej sesji nie wpływa na Live i odwrotnie.

Filtry są domyślnie wyłączone i wymagają świadomego zaznaczenia `Zastosuj filtry`.

### 3.8. DBC jako warstwa interpretacji

DBC nie zmienia surowego payloadu. Dla otwartych zapisanych sesji może zostać włączony lub wyłączony i powoduje ponowną interpretację bez modyfikowania źródłowej sesji.

W Live zestaw aktywnych DBC jest przygotowywany przed rozpoczęciem rejestracji. Zmiana aktywności DBC nie modyfikuje już trwającej rejestracji.

### 3.9. Rozdzielenie sesji Live i Importowanych

Zarządzanie sesjami jest przeniesione do `app/session_management.py`, a GUI tylko wywołuje operację.

Dla Live usuwane są:

- wpis z bazy projektu,
- `*.crt.jsonl`,
- `*.frames.csv`,
- `*.messages.csv`,
- `*.markers.jsonl`,
- indeks sesji.

Dla Importowanych usuwane są:

- wpis z bazy projektu,
- wszystkie kopie i pliki pochodne wewnątrz projektu,
- projektowa kopia pliku CSV z `sessions/imported/source`, jeśli istnieje.

Nigdy nie jest usuwany oryginalny plik znajdujący się poza katalogiem projektu.

### 3.10. Testy regresji

Istnieją testy obejmujące między innymi:

- lifecycle kanału CANlib w jednym wątku,
- niezależne opróżnianie kolejki CANlib,
- tryb BENCH i LISTEN ONLY,
- filtrowanie Live w workerze,
- zakresy filtrów,
- zapisane sesje i stronicowanie,
- dekodowanie ISO-TP, UDS i J1939,
- zachowanie DBC,
- usuwanie sesji Live i Importowanych,
- ochronę plików źródłowych poza projektem,
- smoke testy GUI.

---

## 4. Co nadal jest zbyt mocno sprzężone

### 4.1. LiveCaptureWidget ma zbyt szeroką odpowiedzialność

Obecny widget jednocześnie:

- buduje GUI,
- wyszukuje adaptery Kvaser,
- wybiera bitrate i tryb odbioru,
- tworzy `CaptureService`,
- buduje `CaptureConfig`,
- uruchamia i zatrzymuje rejestrację,
- rejestruje sesję w projekcie,
- pobiera snapshoty,
- aktualizuje modele tabel,
- nakłada interpretację DBC,
- aktualizuje statusy i liczniki,
- obsługuje znaczniki.

To jest główny kandydat do rozdzielenia.

### 4.2. GUI zna typy z warstwy Kvasera

`LiveCaptureWidget` importuje bezpośrednio:

- `KvaserReceiveMode`,
- `list_channels`.

Docelowo GUI powinno operować na neutralnym interfejsie adaptera i danych konfiguracyjnych, a mapowanie na Kvasera powinno znajdować się w kontrolerze lub warstwie infrastruktury.

### 4.3. Runtime patching klas

Część funkcji jest instalowana przez modyfikowanie klas podczas uruchamiania aplikacji:

- `install_live_filter_integration()`,
- `install_live_save_integration()`,
- `install_session_filter_integration()`,
- `install_protocol_view_integration()`,
- `install_session_management_integration()`.

Moduły zapisują lub nadpisują między innymi:

- `LiveCaptureWidget.__init__`,
- `LiveCaptureWidget._update_status`,
- `LiveCaptureWidget._frame_selected`,
- `SessionViewWidget.__init__`,
- metody `MainWindow`.

Ryzyka:

- kolejność instalacji wpływa na rezultat,
- integracja może przechwycić wersję metody zmodyfikowaną przez inną integrację,
- trudniej analizować finalne zachowanie klasy,
- trudniej testować pojedynczą warstwę,
- późniejsze zmiany mogą powodować ukryte regresje.

Runtime patching powinien zostać usunięty po przeniesieniu funkcji do jawnych klas i kontrolerów.

### 4.4. Importy z warstw niższych do GUI

GUI importuje bezpośrednio klasy infrastruktury, repozytoria projektu oraz dekodery. Część tych importów jest prawidłowa dla warstwy prezentacji, ale sterowanie sprzętem i lifecycle sesji powinno zostać przeniesione do kontrolera aplikacyjnego.

### 4.5. Brak jawnego kontraktu zdarzeń

Obecnie komunikacja opiera się na mieszance:

- timerów Qt,
- odpytywania statusu,
- sygnałów Qt,
- bezpośrednich wywołań metod,
- monkey patchingu.

Docelowo powinien istnieć jeden jawny kontrakt pomiędzy usługą rejestracji a GUI.

### 4.6. Nieograniczona kolejka Kvasera

Nieograniczona kolejka chroni przed krótkimi opóźnieniami konsumenta, ale przy długotrwałym przeciążeniu może zużyć cały RAM.

Nie należy jej pochopnie zastępować małą kolejką z odrzucaniem ramek. Najpierw potrzebne są:

- metryki backlogu,
- ostrzeżenie o rosnącej kolejce,
- test obciążeniowy,
- określenie polityki awaryjnej,
- ewentualny zapis awaryjny lub kontrolowane zatrzymanie sesji.

---

## 5. Odpowiedź na pytanie o wpływ zmian

### 5.1. Zmiany czysto wizualne GUI

Przykłady:

- kolory,
- układ przycisków,
- menu kontekstowe,
- szerokości kolumn,
- tekst Inspektora,
- format liczników.

**Nie powinny wpływać na Kvasera ani zapis.**

Mogą wpłynąć na wydajność głównego wątku GUI, ale dedykowany wątek Kvasera nadal powinien odbierać ramki.

### 5.2. Zmiany GUI związane ze Start/Stop

Przykłady:

- budowa `CaptureConfig`,
- wybór kanału,
- wybór bitrate,
- wybór BENCH/LISTEN ONLY,
- tworzenie `CaptureService`,
- rozpoczęcie i zatrzymanie sesji.

**Mogą bezpośrednio wpłynąć na Kvasera**, ponieważ GUI obecnie steruje konfiguracją usługi.

### 5.3. Zmiany silnika filtrów

**Nie powinny wpływać na Kvasera ani pełny zapis**, o ile filtry pozostają używane wyłącznie w modelach widoku i loaderach zapisanych sesji.

Mogą wpływać na:

- widoczne wiersze,
- CPU,
- RAM,
- czas przeliczania,
- responsywność tabel.

### 5.4. Zmiany integracji filtrów GUI

Mogą wpłynąć na GUI i jego wydajność. Nie powinny wpływać na odbiornik Kvasera, ale błędna zmiana w `LiveCaptureWidget` może przypadkowo naruszyć kod Start/Stop albo sposób pobierania snapshotów.

### 5.5. Zmiany dekoderów protokołów

Mogą zmienić:

- `*.messages.csv`,
- klasyfikację UDS/J1939/UNKNOWN,
- pola Inspektora,
- nazwy wiadomości logicznych.

Nie powinny zmienić:

- `*.crt.jsonl`,
- `*.frames.csv`,
- liczby fizycznie odebranych ramek.

### 5.6. Zmiany warstwy Kvasera lub CaptureService

Są zmianami krytycznymi. Mogą wpłynąć na:

- kompletność odbioru,
- bitrate,
- ACK,
- kolejność ramek,
- timestampy,
- zapis sesji,
- obciążenie pamięci i CPU.

Każda taka zmiana wymaga osobnych testów oraz testu z rzeczywistym adapterem Kvaser.

---

## 6. Docelowa architektura

Rekomendowany podział:

```text
┌─────────────────────────────────────────────┐
│ Presentation / GUI                          │
│ MainWindow, widoki, modele Qt, delegaty     │
└──────────────────────┬──────────────────────┘
                       │ komendy + zdarzenia
┌──────────────────────▼──────────────────────┐
│ Application / Controllers                   │
│ LiveCaptureController                       │
│ SessionController                           │
│ FilterController                            │
│ DecoderController                           │
└──────────────────────┬──────────────────────┘
                       │ neutralne interfejsy
┌──────────────────────▼──────────────────────┐
│ Domain / Core                               │
│ modele CAN, filtry, protokoły, sesje        │
│ bez Qt i bez CANlib                         │
└──────────────────────┬──────────────────────┘
                       │ porty / interfejsy
┌──────────────────────▼──────────────────────┐
│ Infrastructure                              │
│ Kvaser CANlib, SQLite, pliki, eksport CSV   │
└─────────────────────────────────────────────┘
```

### 6.1. Presentation / GUI

Powinna odpowiadać tylko za:

- tworzenie kontrolek,
- wyświetlanie stanu,
- zbieranie intencji użytkownika,
- wysyłanie komend do kontrolerów,
- prezentację modeli.

Nie powinna:

- otwierać CANlib,
- tworzyć backendu Kvasera,
- zarządzać transakcjami SQLite,
- usuwać plików bezpośrednio,
- znać szczegółów lifecycle wątku odbiorczego.

### 6.2. Application / Controllers

Powinna odpowiadać za przypadki użycia:

- rozpocznij rejestrację,
- zatrzymaj rejestrację,
- dodaj znacznik,
- usuń sesję,
- zastosuj filtr,
- przeładuj DBC,
- otwórz zapisaną sesję.

Kontroler powinien przekazywać GUI neutralne statusy i snapshoty.

### 6.3. Domain / Core

Powinien pozostać niezależny od PySide6 i CANlib:

- `CanFrame`,
- `CaptureSession`,
- filtry i kompilator filtrów,
- transport messages,
- protokoły,
- modele sesji,
- logika dopasowania DBC, jeśli da się ją utrzymać bez GUI.

### 6.4. Infrastructure

Powinna zawierać:

- Kvaser CANlib,
- implementację kanału CAN,
- zapis plików,
- SQLite,
- import/eksport,
- otwieranie lokalizacji w systemie operacyjnym.

---

## 7. Proponowane interfejsy

### 7.1. Neutralny interfejs kanału CAN

```python
class CanReceiveChannel(Protocol):
    def open(self) -> None: ...
    def read(self, timeout_ms: int) -> CanFrame | None: ...
    def close(self) -> None: ...
```

Ten interfejs już częściowo istnieje w `CaptureService` jako `ReadableCanChannel`. Należy go zachować i rozszerzać zamiast importować Kvasera do GUI.

### 7.2. Provider adapterów

```python
class CanAdapterProvider(Protocol):
    def list_adapters(self) -> list[CanAdapterInfo]: ...
```

GUI powinno otrzymywać `CanAdapterInfo`, a nie `KvaserChannelInfo`.

### 7.3. Kontroler Live Capture

Przykładowa odpowiedzialność:

```python
class LiveCaptureController:
    def list_adapters(self) -> list[CanAdapterInfo]: ...
    def start(self, request: StartCaptureRequest) -> None: ...
    def stop(self) -> None: ...
    def add_marker(self, marker_id: str) -> None: ...
    def status(self) -> LiveCaptureViewState: ...
    def frames_since(self, sequence: int | None) -> FrameSnapshot: ...
    def messages_since(self, sequence: int | None) -> MessageSnapshot: ...
```

GUI nie powinno samodzielnie tworzyć `CaptureConfig` ani bezpośrednio wywoływać infrastruktury.

### 7.4. Kontroler sesji

Powinien obsługiwać:

- otwieranie,
- zamykanie,
- usuwanie,
- importowanie,
- eksportowanie,
- powiązanie z obszarami badawczymi.

`app/session_management.py` jest dobrym początkiem tej warstwy.

### 7.5. Kontroler filtrów

Powinien:

- pobierać aktywne presety,
- kompilować zestaw dla określonego scope,
- uruchamiać worker,
- publikować wynik i status,
- nie znać tabeli Qt.

`QSortFilterProxyModel` powinien jedynie prezentować gotowy wynik.

---

## 8. Zasady obowiązujące podczas refaktoryzacji

### Zasada 1 — nie zmieniać stabilnego lifecycle CANlib

Cały lifecycle uchwytu Kvasera ma pozostać w jednym dedykowanym wątku:

- `openChannel`,
- ustawienie drivera,
- ustawienie bitrate,
- `busOn`,
- wszystkie `read`,
- `busOff`,
- `close`.

### Zasada 2 — GUI nigdy nie może czytać bezpośrednio z CANlib

GUI może pobierać wyłącznie snapshoty lub zdarzenia z kontrolera/usługi.

### Zasada 3 — surowy zapis przed analizą

Surowa ramka ma być zapisana przed:

- filtrowaniem,
- DBC,
- UDS,
- J1939,
- prezentacją GUI.

### Zasada 4 — filtry nie mogą ograniczać zapisu

Filtr może zmienić tylko:

- widok,
- wynik wyszukiwania,
- eksport świadomie wybranego podzbioru w przyszłości.

Nie może zmieniać pełnego pliku źródłowego sesji.

### Zasada 5 — zapisane sesje są niezmienne

Otwarcie, filtrowanie, DBC i ponowna interpretacja nie mogą modyfikować źródłowego `*.crt.jsonl`.

### Zasada 6 — usunąć runtime patching etapami

Nie usuwać wszystkich integracji naraz. Każdą należy przenieść do jawnej klasy lub kontrolera, zachowując test regresji.

### Zasada 7 — każdy etap musi pozostawiać aplikację uruchamialną

Po każdym etapie:

- `compileall`,
- `pytest`,
- GUI smoke,
- ręczny Start/Stop z Kvaserem,
- sprawdzenie kompletności zapisu.

### Zasada 8 — nie łączyć refaktoryzacji z nowymi funkcjami

Pierwsze etapy powinny zmieniać strukturę bez zmiany zachowania użytkowego. Nowe funkcje należy dodawać dopiero po ustabilizowaniu granic.

---

## 9. Zalecana kolejność refaktoryzacji

### Etap A — testy architektoniczne i charakterystyka zachowania

1. Dodać test potwierdzający, że filtr nie zmienia liczby zapisanych ramek.
2. Dodać test potwierdzający, że pauza GUI nie zatrzymuje `CaptureService`.
3. Dodać test backlogu Kvasera przy wolnym konsumencie.
4. Dodać test kolejności: raw write przed protocol decode.
5. Dodać test, że GUI nie importuje bezpośrednio `canlib`.

### Etap B — wydzielenie LiveCaptureController

1. Kontroler przejmuje tworzenie `CaptureService`.
2. Kontroler przejmuje `CaptureConfig`.
3. Kontroler udostępnia neutralną listę adapterów.
4. Widget wysyła tylko request start/stop.
5. Zachować obecny wygląd i zachowanie GUI.

### Etap C — usunięcie Kvasera z GUI

1. Usunąć importy `kvaser.backend` z widoków.
2. Mapowanie trybu BENCH/LISTEN ONLY przenieść do infrastruktury lub kontrolera.
3. GUI operuje neutralnym enumem trybu odbioru.

### Etap D — przeniesienie integracji Live do jawnej klasy

1. Wbudować `LiveFrameFilterProxy` jawnie w konstruktor widgetu lub kompozytora widoku.
2. Usunąć patchowanie `LiveCaptureWidget.__init__`.
3. Usunąć patchowanie `_update_status` i `_frame_selected`.
4. Wstrzyknąć zależności w konstruktorze.

### Etap E — uporządkowanie SessionView

1. Przenieść filtry zapisanych sesji do `StoredSessionController`.
2. Przenieść stronicowanie i worker poza widget.
3. Widok ma otrzymywać gotowy `StoredSessionPageState`.
4. Usunąć patchowanie `SessionViewWidget`.

### Etap F — kontroler projektu i sesji

1. Przenieść otwieranie i zamykanie zakładek sesji do kontrolera/nawigatora.
2. Pozostawić `session_management.py` jako warstwę aplikacyjną lub rozdzielić ją na use case + repository.
3. Przenieść systemowe `Idź do pliku` do infrastruktury desktopowej.
4. Usunąć patchowanie `MainWindow`.

### Etap G — kompozycja aplikacji

1. Stworzyć jedno miejsce budowania zależności, np. `ApplicationContainer` lub `AppServices`.
2. `gui/main.py` tworzy serwisy, kontrolery i widoki jawnie.
3. Usunąć funkcje `install_*_integration()`.
4. Udokumentować graf zależności.

### Etap H — monitoring i odporność

1. Dodać metrykę backlogu kolejki Kvasera.
2. Dodać stan ostrzegawczy przy rosnącym backlogu.
3. Zmierzyć RAM i CPU przy dużym ruchu.
4. Dopiero na podstawie pomiarów ustalić politykę limitowania kolejki.

---

## 10. Kryteria akceptacji poprawionej architektury

Refaktoryzację można uznać za zakończoną, gdy:

- GUI nie importuje `KvaserPassiveChannel` ani CANlib,
- `LiveCaptureWidget` nie tworzy `CaptureService`,
- GUI nie buduje bezpośrednio `CaptureConfig`,
- brak runtime patchingu klas,
- wszystkie integracje są jawnymi zależnościami,
- filtry są niezależne od zapisu,
- surowy zapis pozostaje przed dekodowaniem,
- lifecycle CANlib pozostaje w jednym wątku,
- zachowanie Start/Stop jest identyczne jak wcześniej,
- testy jednostkowe i GUI przechodzą,
- test rzeczywistego odbioru Kvasera nie wykazuje utraty ramek,
- pliki sesji zachowują kompatybilność.

---

## 11. Elementy, których nie należy teraz przepisywać

Bez wyraźnej potrzeby nie należy zmieniać:

- implementacji wątku odbiorczego `KvaserPassiveChannel`,
- kolejności `openChannel` → driver → bitrate → `busOn`,
- pętli `read(timeout=1)`,
- modelu `CanFrame`,
- formatu `*.crt.jsonl`,
- pełnego zapisu `*.frames.csv`,
- podstaw `StreamingTransportPipeline`,
- działających dekoderów UDS/J1939,
- ochrony oryginalnych plików importowanych,
- obowiązujących testów regresji.

Te elementy mogą zostać opakowane nowymi interfejsami, ale nie powinny być równocześnie przeprojektowywane.

---

## 12. Znane ryzyka nowego etapu

1. **Ukryta zależność kolejności integracji**  
   Usuwanie monkey patchingu może ujawnić, że jedna integracja polega na wcześniejszej modyfikacji innej.

2. **Zmiana zachowania Start/Stop**  
   Przeniesienie odpowiedzialności z widgetu do kontrolera może zmienić kolejność czyszczenia modeli, rejestracji sesji lub obsługi błędów.

3. **Podwójne połączenia sygnałów Qt**  
   Podczas przejściowego okresu stary i nowy kod mogą jednocześnie podłączać te same sygnały.

4. **Lifetime workerów**  
   Obiekty `QRunnable`, sygnały i widgety muszą być poprawnie utrzymywane, aby nie dochodziło do callbacków po zamknięciu widoku.

5. **Backlog pamięciowy**  
   Wydzielenie kontrolerów nie rozwiązuje automatycznie ryzyka nieograniczonej kolejki.

6. **Kompatybilność zapisanych sesji**  
   Refaktoryzacja nie może wymusić migracji istniejących plików bez jawnego planu wersjonowania.

---

## 13. Pierwsze zadanie w nowej rozmowie

Rekomendowane pierwsze zadanie:

> Wydzielić `LiveCaptureController` bez zmiany zachowania aplikacji. Kontroler ma przejąć tworzenie `CaptureService`, listowanie adapterów, budowę `CaptureConfig`, Start/Stop oraz udostępnianie statusu i snapshotów. `LiveCaptureWidget` ma zachować obecny wygląd, modele i sygnały, ale nie może importować `kvaser.backend` ani tworzyć `CaptureService`.

Zakres pierwszego PR/refaktoryzacji powinien być ograniczony do tej jednej granicy.

---

## 14. Podsumowanie przekazania

Obecna aplikacja posiada dobry fundament wykonawczy:

- stabilny odbiór Kvasera,
- kolejkę oddzielającą CANlib od analizy,
- pełny zapis niezależny od GUI,
- dekodowanie warstwowe,
- filtry jako warstwę prezentacji,
- testy regresji.

Kolejny etap nie powinien być „przepisaniem aplikacji”, lecz uporządkowaną migracją odpowiedzialności:

```text
widok → kontroler → core → infrastruktura
```

Najważniejsza reguła całego etapu:

> Poprawiamy zależności i organizację kodu, nie zmieniając sprawdzonego toru odbioru i zapisu CAN.
