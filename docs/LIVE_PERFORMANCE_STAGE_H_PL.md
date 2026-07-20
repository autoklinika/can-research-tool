# Etap H — wydajność Live Capture

**Status:** zakończony  
**Gałąź robocza:** `agent/live-performance-monitoring`  
**Zakres:** stabilizacja podglądu Live bez zmian w `CaptureService`, Kvaserze, lifecycle CANlib i pełnym zapisie sesji

## Problem bazowy — H1

Pierwszy pomiar stanowiskowy trwał około 220 s i objął 69 068 ramek oraz 65 966 wiadomości logicznych. Bufory podglądu miały pojemność 250 000 ramek i 100 000 wiadomości.

Wyniki:

- working set: około 116,8 MB → 281,5 MB,
- wzrost pamięci: około 45 MB/min,
- `status()`: około 0,055 ms → 3,126 ms,
- `frames_since()`: około 0,023 ms → 3,774 ms,
- `messages_since()`: około 0,037 ms → 4,047 ms.

Przyczyną było wielokrotne kopiowanie coraz większych buforów podglądu podczas odświeżania GUI. Pełny zapis sesji nie był źródłem problemu.

## Eksperyment H2

Ograniczono wyłącznie bufory prezentacyjne Live do:

```text
20 000 ramek
5 000 wiadomości logicznych
```

Pomiar trwał około 243 s i objął 76 344 ramki oraz 72 907 wiadomości logicznych.

Wyniki:

- working set: około 114,6 MB → 132,6 MB,
- po zapełnieniu buforów wzrost pamięci spadł do około 0,4–0,5 MB/min,
- mediana `status()`: około 0,623 ms,
- mediana `frames_since()`: około 1,314 ms,
- mediana `messages_since()`: około 0,344 ms,
- rytm GUI: około 96–97 ms,
- brak `snapshot.truncated`.

## Końcowe potwierdzenie H3

Test trwał około 902,8 s z aktywnym pełnym zapisem sesji.

Zakres:

- 301 436 ramek CAN,
- 288 622 wiadomości logicznych,
- średnio około 333 ramek/s,
- średnio około 319 wiadomości/s,
- aktywne filtry Live,
- około 37 s pauzy widoku,
- pełny zapis na dysk.

Wyniki:

- working set: około 152,5 MB → 168,1 MB,
- wzrost przez ostatnie 5 minut: około 0,24 MB/min,
- mediana `status()`: około 0,434 ms,
- mediana `frames_since()`: około 1,142 ms,
- mediana `messages_since()`: około 0,321 ms,
- rytm GUI: mediana około 91,5 ms.

Po długiej pauzie wystąpiło jedno `message_snapshot.truncated`, ponieważ w czasie pauzy powstało więcej niż 5 000 wiadomości. Ograniczenie dotyczy wyłącznie podglądu GUI. Pełna sesja na dysku pozostała kompletna.

## Rozwiązanie produkcyjne

Pozostają:

- `BoundedLiveCaptureWidget`,
- limit 20 000 ramek podglądu,
- limit 5 000 wiadomości logicznych podglądu,
- niezmieniony pełny zapis surowych ramek i wiadomości,
- test pojemności podglądu,
- test rzeczywistej ścieżki filtrowania nowych ramek podczas aktywnego Capture,
- narzędzie `tools/diagnose_live_filters.py` do kontroli zapisanych presetów i decyzji filtra.

Usunięto po zakończeniu pomiarów:

- `InstrumentedLiveCaptureController`,
- zmienne `CRT_LIVE_PERF` i `CRT_LIVE_PERF_INTERVAL_S`,
- generator raportów JSONL,
- skrypt `tools/run_stage_h.ps1`,
- testy dotyczące wyłącznie tymczasowej instrumentacji.

## Granice zachowane

Etap H nie zmienił:

- `CaptureService`,
- Kvasera i lifecycle CANlib,
- kolejności odbioru lub zapisu ramek,
- formatów sesji,
- logiki pełnego zapisu,
- sprzętowej kolejki odbiorczej.

## Wniosek

Produkcjny podgląd 20 000 / 5 000 usuwa progresywny wzrost kosztu snapshotów i stabilizuje pamięć przy długim Capture. Etap H został zakończony.
