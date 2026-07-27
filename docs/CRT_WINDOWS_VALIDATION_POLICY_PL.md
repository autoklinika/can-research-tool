# Polityka walidacji CAN Research Tool — wyłącznie Windows

Data obowiązywania: 2026-07-27

## 1. Platforma docelowa

CAN Research Tool jest aplikacją docelową dla systemu Windows.

Wszystkie testy aplikacji, GUI, integracji, instalacji, zachowania użytkowego i regresji środowiskowych muszą być wykonywane na Windows.

## 2. GitHub Actions

Podstawową platformą automatycznej walidacji jest:

`windows-latest`

Workflowy CRT nie mogą używać Ubuntu, macOS ani macierzy wieloplatformowej do walidacji aplikacji.

Testy czysto algorytmiczne również uruchamiamy na Windows, aby checkpoint etapu odpowiadał rzeczywistemu środowisku produktu.

## 3. Windows self-hosted

Runner self-hosted Windows jest przeznaczony wyłącznie do testów wymagających zasobów niedostępnych na GitHub-hosted, w szczególności:

- fizycznego Kvasera,
- CANlib,
- interfejsu CAN,
- rzeczywistego ECU lub stanowiska testowego,
- urządzeń peryferyjnych zależnych od lokalnego środowiska.

Etapy pasywnej analizy, GUI i pracy na zapisanych sesjach nie mogą być blokowane przez brak self-hosted runnera, jeżeli pełny zakres przechodzi na `windows-latest`.

## 4. Test ręczny

Każda nowa lub zmieniona funkcja widoczna dla użytkownika wymaga ręcznego sprawdzenia na rzeczywistym Windows użytkownika.

W raporcie należy rozróżnić:

- walidację automatyczną Windows,
- test ręczny Windows,
- test sprzętowy Windows self-hosted, jeżeli był wymagany.

## 5. Checkpoint etapu

Etap może otrzymać funkcjonalny checkpoint, gdy:

1. wymagane testy rdzenia zakończyły się sukcesem na Windows,
2. wymagane smoki GUI zakończyły się sukcesem na Windows,
3. właściwe regresje Windows zakończyły się sukcesem,
4. funkcja użytkowa została ręcznie potwierdzona na Windows albo raport wyraźnie wskazuje, czego nie można było jeszcze sprawdzić,
5. Help Center został zaktualizowany zgodnie z `docs/CRT_HELP_MAINTENANCE_POLICY_PL.md` albo zapisano uzasadnienie `Help Center: nie dotyczy`.

## 6. Raportowanie

Nie należy przedstawiać wyników Ubuntu ani innych systemów jako:

- wymaganego checkpointu CRT,
- dowodu gotowości aplikacji,
- kryterium merge,
- zamiennika testu na Windows.

Historyczne przebiegi innych systemów mogą pozostać w logach GitHuba, ale są nieautorytatywne dla dalszego rozwoju CRT.

## 7. Nowe workflowy

Każdy nowy workflow musi domyślnie używać:

```yaml
runs-on: windows-latest
```

Macierz systemów operacyjnych wymaga osobnej, wyraźnej decyzji właściciela projektu.

## 8. Zakaz automatycznego rozszerzania platform

Nie wolno dodawać Linuxa, Ubuntu, macOS ani innych platform „dla pewności”, „dla przenośności” lub jako dodatkowego testu bez wcześniejszej zgody właściciela projektu.
