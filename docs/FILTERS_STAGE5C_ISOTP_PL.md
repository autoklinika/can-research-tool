# Etap 5C — filtry ISO-TP

## Kontrakt

Warstwa ISO-TP buduje zwykłe drzewa `FilterPreset`, które są oceniane przez istniejący `FilterCompiler`. Nie istnieje osobny kompilator ISO-TP i nie ma wpływu na zapis surowych ramek.

Dostępne kryteria:

- transport `isotp`,
- adresowanie 11-bit albo normal-fixed 29-bit,
- wiadomość z jednej albo wielu ramek źródłowych,
- kompletna albo niekompletna rekonstrukcja,
- obecność błędu transportowego,
- CAN ID,
- Source Address i Destination Address,
- zakres deklarowanej i odebranej długości payloadu,
- zakres liczby ramek źródłowych.

Klasyfikacja `single-frame` oznacza wiadomość logiczną zbudowaną z jednej ramki CAN. Osierocona lub uszkodzona ramka ISO-TP również może mieć jedną ramkę źródłową, dlatego prawidłowy Single Frame należy dodatkowo ograniczyć przez `has_error=False` lub `completion=COMPLETE`.

CRT nie utrwala obecnie parametrów Flow Control takich jak Block Size i STmin w `LogicalMessageRecord`. Filtry 5C nie próbują ich rekonstruować ani zgadywać.
