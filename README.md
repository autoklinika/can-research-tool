# CAN Research Tool

Prywatne narzędzie inżynierskie do rejestracji, porównywania i analizy komunikacji CAN z wykorzystaniem interfejsów Kvaser.

## Zakres projektu

Projekt jest niezależny od `ecu_platform`, `ecu-display` i przyszłego emulatora. Jego zadaniem jest wspieranie badań nad protokołami ECU oraz urządzeń takich jak EGR, VGT, BPV, NOx i SCR.

Pierwszy etap obejmuje:

- stabilną obsługę Kvaser CANlib na Windows,
- odbiór ramek CAN z timestampami,
- kontrolowane wysyłanie ramek,
- zapis sesji badawczych,
- oznaczanie zdarzeń podczas eksperymentu,
- przygotowanie danych do późniejszej analizy.

## Zasada bezpieczeństwa

Aplikacja powinna uruchamiać się domyślnie bez automatycznego nadawania. Wysyłanie ramek musi być jawnie włączane przez operatora i ograniczone konfiguracją sesji.

## Struktura

```text
src/            kod aplikacji
reference/      sprawdzone materiały referencyjne, nie kod bazowy
docs/           architektura, formaty danych, bezpieczeństwo i roadmapa
tests/          testy jednostkowe oraz małe próbki danych
config/         przykładowe konfiguracje bez danych lokalnych
scripts/        narzędzia pomocnicze
```

Pełne logi CAN, lokalne sesje, biblioteki producenta, pliki DLL i konfiguracje stanowiska nie są przechowywane w Git.

## Status

Repozytorium znajduje się na etapie przygotowania architektury. Działający skrypt Kvasera zostanie dodany wyłącznie jako materiał referencyjny i nie będzie bezpośrednio przerabiany na aplikację docelową.
