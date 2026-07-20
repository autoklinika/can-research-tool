# Global Filter Engine v2 — Etap 6A

## Cel

Etap 6A rozszerza filtry statyczne CRT bez wprowadzania warunków zależnych od historii. Ten sam preset ma później działać identycznie w Live Capture, zapisanej sesji, analizie i eksporcie.

Filtry pozostają wyłącznie warstwą prezentacji. Nie mogą ograniczać odbioru CAN, kolejki CANlib ani pełnego zapisu sesji.

## Status

- 6A.1 — fundament wzorców: **zakończony**,
- 6A.2 — kontekst i kompilator v2: **zakończony**,
- 6A.3 — GUI: **zakończony**,
- 6A.4 — Live i zapisane sesje: oczekuje.

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

### 6A.1 — fundament wzorców — zakończony

- `CanIdPattern`,
- `PayloadPattern`,
- parser składni,
- kanonizacja wartości i masek,
- walidacja 29-bitowego CAN ID,
- limit 64 bajtów dla surowej ramki,
- testy exact, wildcard, explicit mask, prefix i contains.

### 6A.2 — integracja domenowa — zakończony

Dodano:

- `StaticCanFrameRecord` z polami kanału, RTR, error frame i payloadu,
- `StaticFilterContext`, który zachowuje dostęp do wszystkich pól v1,
- `StaticFilterCompiler`, który deleguje stare warunki do `FilterCompiler` v1,
- operatory `can_id_pattern`, `payload_exact`, `payload_prefix` i `payload_contains`,
- zwykłe porównania kanału oraz flag logicznych,
- wspólne grupy `AND`, `OR` i `NOT` dla warunków v1 i v2,
- walidację zakresu kanału, DLC, payloadu i składni masek,
- semantykę `UNAVAILABLE` zgodną z v1,
- testy mieszanych presetów v1/v2.

Istniejące presety nadal używają `format_version=1`. Nowa semantyka jest rozpoznawana przez nazwy pól i operatorów; nie wymaga migracji `project.sqlite`.

### 6A.3 — GUI — zakończony

Dodano:

- pola `Kanał`, `RTR`, `Error frame` oraz `Payload / maska`,
- operator maski/wildcardu CAN ID,
- operatory payloadu `dokładnie`, `prefix` i `contains`,
- listę operatorów zależną od wybranego pola,
- bezpieczne wartości domyślne dla nowych warunków,
- opisy składni CAN ID i payloadu bez implementowania semantyki w GUI,
- walidację aktywnych presetów przez `StaticFilterCompiler`,
- test ręcznie zdefiniowanej ramki z kanałem, RTR, error frame i payloadem,
- jawne `UNAVAILABLE` przy próbie testowania warunku surowej ramki jako wiadomości logicznej,
- walidację presetów v2 przy aktywacji globalnym skrótem,
- testy jednostkowe metadanych edytora i smoke GUI.

### 6A.4 — Live i zapisane sesje

- adapter prawdziwej ramki aplikacji do `StaticCanFrameRecord`,
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
