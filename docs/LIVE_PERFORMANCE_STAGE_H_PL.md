# Etap H — pomiary wydajności Live Capture

**Gałąź:** `agent/live-performance-monitoring`  
**Status:** faza H2 potwierdzona — produkcyjny podgląd ograniczony; oczekuje test H3  
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

## Wynik H1 — bufor 250 000 / 100 000

Pierwszy pomiar stanowiskowy trwał około 220 s i objął 69 068 ramek oraz 65 966
wiadomości logicznych. Nie wystąpiło `snapshot.truncated`, ale wykryto progresywny koszt
rosnących buforów podglądu:

- working set wzrósł z około 116,8 MB do 281,5 MB,
- tempo wzrostu pamięci wynosiło około 45 MB/min,
- średni czas `status()` wzrósł od około 0,055 ms do 3,126 ms,
- średni czas `frames_since()` wzrósł od około 0,023 ms do 3,774 ms,
- średni czas `messages_since()` wzrósł od około 0,037 ms do 4,047 ms.

Przyczyną było wielokrotne kopiowanie całych, wciąż rosnących buforów podczas każdego
odświeżenia Live. Pełny zapis sesji nie był źródłem problemu.

## Faza H2 — ograniczony podgląd

Eksperyment H2 ograniczył wyłącznie bufory prezentacyjne i odpowiadające im snapshoty do:

```text
20 000 ramek
5 000 wiadomości logicznych
```

Drugi pomiar trwał około 243 s i objął 76 344 ramki oraz 72 907 wiadomości logicznych.
Bufor wiadomości osiągnął limit po około 17 s, a bufor ramek po około 65 s. Po tym
momencie koszty przestały rosnąć proporcjonalnie do długości sesji:

- working set wzrósł z około 114,6 MB do 132,6 MB,
- po zapełnieniu buforów wzrost wynosił około 0,4–0,5 MB/min,
- mediana `status()` wyniosła około 0,623 ms,
- mediana `frames_since()` wyniosła około 1,314 ms,
- mediana `messages_since()` wyniosła około 0,344 ms,
- rytm GUI pozostał stabilny na poziomie około 96–97 ms,
- nie wystąpiło `snapshot.truncated`.

Wynik H2 potwierdził, że limity 20 000 / 5 000 rozwiązują regresję bez ingerencji w
`CaptureService`, Kvasera ani pełny zapis sesji. Limity zostały przeniesione do zwykłego
produkcyjnego widoku Live. Tymczasowa klasa `StageHLiveCaptureWidget` została usunięta.

## Uruchomienie na Windows PowerShell

Zalecane uruchomienie korzysta ze skryptu, który ustawia zmienne środowiskowe w tym
samym procesie PowerShell co aplikacja i wypisuje potwierdzenie aktywacji:

```powershell
.\tools\run_stage_h.ps1
```

Inny interwał próbkowania:

```powershell
.\tools\run_stage_h.ps1 -IntervalSeconds 2.0
```

Uruchomienie ręczne pozostaje dostępne:

```powershell
$env:CRT_LIVE_PERF = "1"
$env:CRT_LIVE_PERF_INTERVAL_S = "1.0"
python .\crt_gui.py
```

Ważne: aplikacja musi zostać uruchomiona z tego samego terminala, w którym ustawiono
zmienne. Uruchomienie później przez skrót, osobny terminal albo przycisk Run w innym
procesie może nie odziedziczyć `CRT_LIVE_PERF`.

Po otwarciu projektu i rozpoczęciu Capture raport zostanie zapisany w:

```text
<projekt>\reports\live-performance-YYYYMMDD_HHMMSS-<sesja>.jsonl
```

Katalog i raport powstają dopiero po kliknięciu `Start` dla Live Capture.

Wyłączenie trybu diagnostycznego:

```powershell
Remove-Item Env:CRT_LIVE_PERF -ErrorAction SilentlyContinue
Remove-Item Env:CRT_LIVE_PERF_INTERVAL_S -ErrorAction SilentlyContinue
```

Bez `CRT_LIVE_PERF=1` aplikacja nadal korzysta z ograniczonego produkcyjnego podglądu,
ale używa bezpośrednio zwykłego `LiveCaptureController`. Nie jest wtedy tworzony raport
i nie jest wykonywane próbkowanie zasobów.

## Faza H3 — końcowe potwierdzenie

Ostatni pomiar powinien trwać co najmniej 15 minut na aktywnej magistrali i potwierdzić:

1. stabilny working set po zapełnieniu obu buforów,
2. brak progresywnego wzrostu czasów snapshotów,
3. brak `snapshot.truncated`,
4. stabilny rytm GUI,
5. niezmieniony pełny zapis sesji.

Po H3 instrumentacja `InstrumentedLiveCaptureController`, skrypt `run_stage_h.ps1` oraz
workflow pomiarowy zostaną ocenione do usunięcia. Produkcyjne limity podglądu pozostaną,
ponieważ ich skuteczność została potwierdzona pomiarem stanowiskowym.
