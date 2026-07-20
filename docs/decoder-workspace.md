# Dekodery projektu

## Lokalizacja w GUI

Pliki DBC są zarządzane w zakładce `Dekodery`, dostępnej z paska aktywności i Explorera projektu. Nie należą do konfiguracji adaptera ani sesji.

## Import

`Importuj DBC…`:

1. wybiera jeden lub wiele plików `*.dbc`,
2. waliduje składnię przez `cantools`,
3. kopiuje pliki do `decoders/dbc`,
4. zapisuje metadane w `.crt/project.sqlite`,
5. domyślnie włącza nowy plik.

Ponowny import identycznego pliku jest rozpoznawany po SHA-256 i nie tworzy duplikatu.

## Aktywność

Kolumna `Aktywny` steruje interpretacją. Wyłączenie:

- nie usuwa DBC,
- nie zmienia surowej sesji,
- nie przepisuje `*.crt.jsonl`,
- natychmiast przeładowuje widok zapisanych sesji,
- obowiązuje od następnego rozpoczęcia Live Capture.

Trwający capture zachowuje zestaw DBC wybrany przy `Start`.

## Kolejność i kolizje

DBC dopasowuje jednocześnie CAN ID oraz typ `STD/EXT`. Gdy kilka aktywnych plików definiuje tę samą parę, pierwszy plik w kolejności projektu ma pierwszeństwo.

DBC nie zastępuje rekonstrukcji transportowej. UDS po ISO-TP i J1939 TP są dekodowane przed warstwą DBC. DBC działa obecnie na logicznych wiadomościach `RAW`.

## Widok wiadomości

Po dopasowaniu tabela pokazuje protokół `DBC` i nazwę wiadomości. Inspektor zawiera:

- nazwę pliku DBC,
- nazwę wiadomości,
- CAN ID i typ ramki,
- długość zadeklarowaną w DBC,
- nadawcę,
- wartości sygnałów,
- jednostki,
- ewentualny błąd dekodowania.
