# Handoff — Comparison Visualization Stage 2D2

Data: 2026-07-27

## Aktualny stan

Stage 2D2 — trwała oś transakcji UDS — został zaimplementowany i przeszedł walidację GitHub-hosted.

Gałąź:

`agent/comparison-visualization-stage2d2-uds-timeline`

Draft PR:

`#56 Add synchronized UDS transaction timeline`

Zwalidowany funkcjonalny checkpoint:

`3d27e845209a3f3276277cb5ad4e4628df409cea`

Etap nie został scalony i PR pozostaje draftem.

## Co dostarcza Stage 2D2

Nowa karta `Oś UDS` łączy:

- trwałe wyrównanie Stage 2B,
- zachowane transakcje Stage 2C2,

bez ponownego skanowania surowych sesji.

Widok pokazuje:

- request,
- pierwszą odpowiedź,
- `0x78 ResponsePending`,
- odpowiedź końcową,
- timeout i koniec logu,
- latencję jako długość odcinka,
- klasyfikację kolejności względem sesji bazowej,
- tabelę brakujących, dodatkowych i przesuniętych transakcji.

Obsługiwane filtry:

- sesja,
- SID,
- status,
- DID,
- NRC,
- tekst i payload.

Nawigacja prowadzi do dokładnych ramek request, first response i final response przez `source_row`.

## Aktualizacja Help Center

Dodano obowiązkowy artykuł:

`Trwała oś transakcji UDS`

Identyfikator:

`uds-timeline`

Pomoc opisuje lokalizację, źródła, kolory, filtry, porównanie sekwencji, bounded evidence i nawigację do dowodów.

Stage 2D2 nie może zostać końcowo zaakceptowany bez ręcznego sprawdzenia również tego artykułu.

## Uruchomienie na Windows

```powershell
Set-Location C:\CAN\can-research-tool

git fetch origin

git switch agent/comparison-visualization-stage2d2-uds-timeline 2>$null
if ($LASTEXITCODE -ne 0) {
    git switch --track -c agent/comparison-visualization-stage2d2-uds-timeline origin/agent/comparison-visualization-stage2d2-uds-timeline
}

git pull --ff-only
git status -sb
git rev-parse HEAD

python -m gui.main
```

## Test ręczny

### Przygotowanie źródeł

Użyj tego samego projektu i zestawu porównawczego, dla którego działały Stage 2B oraz Stage 2C2.

1. Otwórz `Porównaj`.
2. Wybierz zestaw porównawczy.
3. Kliknij `Analizuj wybrany zestaw…`.
4. W karcie `Oś czasu` sprawdź, czy istnieje zapisane wyrównanie.
5. W karcie `Latencja UDS` sprawdź, czy istnieją transakcje dla właściwych kluczy request/response.

Jeżeli źródła nie istnieją:

- zbuduj i zapisz oś Stage 2B,
- uruchom analizę `Latencja UDS` z właściwymi CAN ID.

### Karta `Oś UDS`

1. Otwórz kartę `Oś UDS`.
2. Poczekaj na automatyczne wczytanie albo kliknij `Wczytaj trwałą oś UDS`.
3. Sprawdź komunikat zawierający:
   - liczbę zachowanych transakcji,
   - identyfikator wyrównania,
   - identyfikator artefaktu UDS,
   - informację `bez skanowania sesji`.
4. Potwierdź osobny pas dla każdej sesji.
5. Potwierdź pionową linię `t = 0`.

### Interpretacja transakcji

Sprawdź przykłady:

- zielony odcinek — odpowiedź pozytywna,
- czerwony — odpowiedź negatywna,
- przerywany pomarańczowy — timeout,
- fioletowy punkt — `0x78`,
- pomarańczowa ramka — transakcja dodatkowa,
- żółta ramka — transakcja przesunięta.

Jeżeli logi nie zawierają któregoś statusu, jego brak na wykresie jest prawidłowy.

### Filtry

Sprawdź kolejno:

- jedną sesję,
- pojedynczy SID,
- status `Negatywna` albo `Timeout`,
- DID, np. `F190`,
- NRC, np. `31`,
- wyszukiwanie fragmentu payloadu.

Po każdym filtrze tabela i wykres powinny pokazywać ten sam podzbiór.

Tabela różnic sekwencji nie powinna zmieniać klasyfikacji tylko dlatego, że zastosowano filtr prezentacji.

### Nawigacja do dowodów

Zaznacz transakcję i sprawdź:

1. `Otwórz żądanie`,
2. `Otwórz pierwszą odpowiedź`,
3. `Otwórz odpowiedź końcową`.

Dla transakcji z `0x78` pierwsza i końcowa odpowiedź powinny prowadzić do różnych ramek.

### Help Center

1. Naciśnij `F1`.
2. Wyszukaj:

`os uds brakujace transakcje`

3. Otwórz artykuł `Trwała oś transakcji UDS`.
4. Potwierdź, że opis odpowiada rzeczywistemu widokowi i wymienia:
   - Stage 2B,
   - Stage 2C2,
   - `0x78`,
   - kolory i ramki,
   - filtry,
   - `source_row`,
   - `evidence_truncated`.

## Kryterium zatwierdzenia

Ręczne potwierdzenie powinno obejmować przepływ:

`zapisane wyrównanie + artefakt UDS → Oś UDS bez skanowania → pasy sesji → statusy i 0x78 → filtry → różnice sekwencji → dokładne ramki request/first/final → zgodny artykuł Help`

## Następny rekomendowany etap

Po ręcznym zatwierdzeniu Stage 2D2 rekomendowany jest:

## Comparison Visualization Stage 2E1 — automatyczna klasyfikacja regresji przepływów UDS

Proponowany zakres:

- trwałe podsumowanie różnic przepływu protokołu,
- klasyfikacja regresji: brak odpowiedzi, nowy NRC, timeout, dodatkowa usługa, zmiana kolejności, wzrost latencji,
- poziom istotności i uzasadnienie klasyfikacji,
- filtrowanie według SID, DID i Routine ID,
- nawigacja do obu porównywanych dowodów,
- osobny artykuł Help Center w tym samym etapie.

Nie rozpoczynać Stage 2E1 przed ręcznym zatwierdzeniem Stage 2D2 albo wyraźną decyzją właściciela.
