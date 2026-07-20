# Global Filter Engine v2 — Etap 6A

## Cel

Etap 6A rozszerza filtry statyczne CRT bez wprowadzania warunków zależnych od historii. Ten sam preset ma później działać identycznie w Live Capture, zapisanej sesji, analizie i eksporcie.

Filtry pozostają wyłącznie warstwą prezentacji. Nie mogą ograniczać odbioru CAN, kolejki CANlib ani pełnego zapisu sesji.

## Zakres docelowy

### Surowa ramka CAN

- kanał CAN,
- RTR,
- error frame,
- dokładny CAN ID,
- CAN ID z maską bitową,
- CAN ID z wildcardami,
- dokładny payload,
- prefix payloadu,
- fragment payloadu,
- wildcard bajtu,
- maska bitowa pojedynczego bajtu lub całego wzorca.

### Składnia CAN ID

```text
0x18DAF900
0x18DA??F9
0x18DA00F9/0x1FFF00FF
```

Wildcard `?` albo `*` oznacza dowolny nibble. Forma `value/mask` używa warunku:

```text
(actual_can_id & mask) == value
```

Wartość jest kanonizowana do `value & mask`.

### Składnia payloadu

```text
62 F1 90
62 F1 ??
A0/F0 55
62F1??
```

- `??` albo `**` — dowolny bajt,
- `A0/F0` — dopasowanie tylko bitów zaznaczonych maską,
- tryby: `exact`, `prefix`, `contains`.

## Podział implementacji

### 6A.1 — fundament wzorców

- `CanIdPattern`,
- `PayloadPattern`,
- parser składni,
- kanonizacja wartości i masek,
- walidacja 29-bitowego CAN ID,
- limit 64 bajtów dla surowej ramki,
- testy exact, wildcard, explicit mask, prefix i contains.

### 6A.2 — integracja z FilterCompiler

- nowe pola i operatory formatu presetu,
- rozszerzenie `CanFrameRecord` i `FilterContext`,
- kanał, RTR, error frame i payload,
- kompatybilność istniejących presetów `format_version=1`,
- jednoznaczna semantyka `UNAVAILABLE`.

### 6A.3 — GUI

- pola w katalogu edytora,
- opisy składni i przykłady,
- walidacja przed zapisem,
- czytelne podsumowanie maski/wildcardu,
- test presetu na ręcznie zdefiniowanej ramce.

### 6A.4 — Live i zapisane sesje

- identyczne wyniki dla tego samego materiału,
- filtrowanie przyrostowe podczas Capture,
- pełne przeliczenie zapisanej sesji poza wątkiem GUI,
- brak wpływu na pełny zapis,
- regresje GUI i test stanowiskowy.

## Poza zakresem 6A

Do Etapu 6B należą warunki stateful:

- częstotliwość i okres,
- jitter,
- zmiana względem poprzedniej ramki,
- maska zmienności,
- missing-frame timeout,
- wykrywanie liczników.

Do Etapu 6C należą menu kontekstowe i generowanie presetów przez analizę.

## Kontrakty

1. `CaptureService`, Kvaser i lifecycle CANlib pozostają bez zmian.
2. Surowa ramka jest zapisywana przed oceną filtra.
3. Stare presety pozostają odczytywalne.
4. Nieprawidłowa maska nie może zostać zapisana jako aktywny preset.
5. Filtr payloadu nie może modyfikować payloadu ani dekodowania protokołu.
6. GUI nie implementuje własnej semantyki dopasowania.
