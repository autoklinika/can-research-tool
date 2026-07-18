# Etap H — pomiary wydajności Live Capture

**Gałąź:** `agent/live-performance-monitoring`  
**Status:** faza H1 — instrumentacja bazowa  
**Zakres:** obserwacja granicy aplikacyjnej Live Capture bez zmian w GUI i torze CAN

## Cel

Etap H ma dostarczyć rzeczywiste dane o zachowaniu Live Capture pod obciążeniem.
Instrumentacja ma odpowiedzieć, czy przy długiej rejestracji rośnie opóźnienie
odświeżania, rozmiar paczek oczekujących na GUI, użycie pamięci albo koszt pobierania
snapshotów.

Etap H nie jest nową funkcją użytkową. Kod pomiarowy jest domyślnie wyłączony i po
zakończeniu testów zostanie oceniony pod kątem usunięcia. W kodzie produkcyjnym mogą
pozostać wyłącznie lekkie zabezpieczenia lub metryki, których przydatność potwierdzą
pomiary.

## Nienaruszalne granice

Instrumentacja:

- nie zmienia `CaptureService`,
- nie zmienia `kvaser/backend.py` ani lifecycle CANlib,
- nie wpływa na odbiór CAN,
- nie zmienia kolejności pełnego zapisu surowej ramki przed dekodowaniem,
- nie zmienia formatów sesji,
- nie dodaje kontrolek, etykiet ani paneli diagnostycznych do GUI,
- nie odrzuca ramek i nie wprowadza limitu sprzętowej kolejki odbiorczej.

## Faza H1 — pomiary bazowe

Dekorator `InstrumentedLiveCaptureController` obserwuje wyłącznie wywołania na granicy
`LiveCaptureWidget → LiveCaptureController`:

- odstęp pomiędzy kolejnymi odpytywaniami statusu,
- czas wykonania `status()`, `frames_since()` i `messages_since()`,
- liczbę ramek i wiadomości zwróconych w paczkach,
- maksymalny rozmiar paczki,
- liczbę przypadków `snapshot.truncated`,
- tempo ramek i wiadomości na sekundę,
- pojemność, zajętość i przepełnienie ograniczonych buforów Live,
- CPU procesu liczone względem jednego rdzenia,
- pamięć procesu: bieżący working set/RSS, a na platformach bez takiego odczytu
  wartość szczytową.

Pomiary są agregowane i zapisywane domyślnie raz na sekundę. Nie jest zapisywany rekord
na każde odświeżenie GUI ani na każdą ramkę CAN.

## Uruchomienie na Windows PowerShell

```powershell
$env:CRT_LIVE_PERF = "1"
$env:CRT_LIVE_PERF_INTERVAL_S = "1.0"
python .\crt_gui.py
```

Po otwarciu projektu i rozpoczęciu Capture raport zostanie zapisany w:

```text
<projekt>\reports\live-performance-YYYYMMDD_HHMMSS-<sesja>.jsonl
```

Wyłączenie trybu diagnostycznego:

```powershell
Remove-Item Env:CRT_LIVE_PERF -ErrorAction SilentlyContinue
Remove-Item Env:CRT_LIVE_PERF_INTERVAL_S -ErrorAction SilentlyContinue
```

Bez `CRT_LIVE_PERF=1` aplikacja używa bezpośrednio zwykłego `LiveCaptureController`.
Nie jest wtedy tworzony raport i nie jest wykonywane próbkowanie zasobów.

## Zalecana sekwencja testu H1

1. Uruchomić CRT bez filtrów i rejestrować aktywną magistralę przez ustalony okres.
2. Powtórzyć test z aktywnymi filtrami Live.
3. W obu próbach wykonać chwilowe `Pauza widoku` i ponownie wznowić widok.
4. Powtórzyć test przy możliwie wysokim obciążeniu magistrali.
5. Zachować raporty JSONL wraz z informacją o adapterze, bitrate i warunkach testu.
6. Porównać tempo danych, odstęp odpytywania, czasy snapshotów, przepełnienia buforów,
   CPU oraz pamięć.

## Decyzja po pomiarach

Po analizie raportów wykonamy jedną z trzech decyzji:

1. Brak problemu — usuwamy instrumentację Etapu H.
2. Przydatna jest minimalna ochrona diagnostyczna — zostawiamy tylko uzasadniony,
   domyślnie wyłączony fragment.
3. Wykryto wąskie gardło — naprawa powstaje jako osobny etap, a tymczasowe sondy są
   usuwane po potwierdzeniu rezultatu.

Samo istnienie kodu pomiarowego nie jest podstawą do pozostawienia go w aplikacji.
