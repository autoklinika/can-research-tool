# Polityka utrzymania Help Center CAN Research Tool

## Status

Dokument obowiązuje od ręcznego zatwierdzenia `CRT Help Center Stage 1`.

Jest to stała reguła procesu rozwoju CAN Research Tool.

## Zasada nadrzędna

Każda nowa funkcja CRT, która została ręcznie zatwierdzona przez właściciela projektu jako działająca i gotowa, musi zostać opisana w Help Center w tym samym etapie prac.

Aktualizacja Pomocy jest częścią implementacji funkcji, a nie opcjonalnym zadaniem dokumentacyjnym wykonywanym później.

## Definicja ukończenia funkcji

Nowej funkcji nie należy uznawać za formalnie zamkniętą, dopóki nie zostały wykonane odpowiednie punkty:

1. kod produkcyjny jest gotowy,
2. testy automatyczne i wymagane testy ręczne zakończyły się poprawnie,
3. właściciel projektu zatwierdził działanie funkcji,
4. Help Center opisuje funkcję z perspektywy użytkownika,
5. opis zawiera ograniczenia, ostrzeżenia i sposób interpretacji wyników, jeżeli są istotne,
6. artykuł zawiera powiązania z odpowiednimi istniejącymi tematami,
7. test katalogu Help został rozszerzony, jeżeli dodano nowy temat lub nowy wymagany obszar,
8. raport etapu i opis PR wskazują, które tematy Pomocy zmieniono,
9. wykonano commit i push zmian,
10. zapisano punkt kontynuacji następnego etapu.

## Kiedy aktualizacja Help jest wymagana

Help należy zaktualizować między innymi wtedy, gdy zmienia się:

- zachowanie interfejsu użytkownika,
- nowa zakładka, okno, menu, przycisk lub skrót,
- przepływ tworzenia, otwierania, zapisywania albo importowania danych,
- sposób rejestracji lub przeglądania sesji,
- filtrowanie, wyszukiwanie, grupowanie lub sortowanie,
- dekodowanie DBC, ISO-TP, UDS albo innych protokołów,
- analiza, metryka, wykres, artefakt lub eksport,
- nawigacja do ramek źródłowych i dowodów,
- format komunikatów, ostrzeżeń lub błędów istotnych dla użytkownika,
- ograniczenie wydajnościowe, bounded model lub semantyka próbkowania,
- wymagania sprzętowe, Kvaser, CANlib albo sposób konfiguracji CAN,
- bezpieczeństwo danych, kopie zapasowe lub przenoszenie projektu.

## Minimalna zawartość opisu funkcji

Artykuł albo aktualizacja istniejącego artykułu powinna wyjaśniać:

- do czego funkcja służy,
- gdzie znajduje się w programie,
- jak ją uruchomić krok po kroku,
- jakie dane wejściowe są wymagane,
- jak czytać wynik,
- jakie są znane ograniczenia,
- czy wynik jest pełny, bounded, próbkowany albo oparty na trwałym artefakcie,
- jak przejść do dowodu źródłowego,
- co zrobić, gdy funkcja nie zwraca wyników albo zgłasza błąd.

## Decyzja `nie dotyczy`

Zmiana może nie wymagać aktualizacji treści Help tylko wtedy, gdy jest wyłącznie:

- refaktoryzacją bez zmiany zachowania użytkowego,
- zmianą testów,
- poprawką workflow CI,
- zmianą dokumentacji deweloperskiej,
- wewnętrzną optymalizacją bez wpływu na wynik, ograniczenia lub interfejs.

W takim przypadku opis PR musi zawierać jawne uzasadnienie:

`Help Center: nie dotyczy — brak zmiany zachowania użytkowego.`

Nie wolno używać `nie dotyczy`, gdy zmiana wpływa na sposób użycia funkcji, interpretację wyniku, ograniczenia albo bezpieczeństwo danych.

## Wymagania dla pull requestu

Każdy PR dostarczający nową funkcję albo zmianę funkcji powinien wskazywać:

- które artykuły Help dodano lub zmieniono,
- czy dodano nowe słowa kluczowe wyszukiwarki,
- czy zmieniono powiązane tematy,
- jakie testy Help wykonano,
- czy przeprowadzono ręczny test treści i nawigacji,
- albo uzasadnienie `Help Center: nie dotyczy`.

## Wymagania testowe

Aktualizacja Help powinna być objęta co najmniej:

- testem spójności identyfikatorów i linków,
- testem obecności nowego wymaganego tematu lub treści,
- testem wyszukiwania po naturalnych frazach użytkownika,
- produkcyjnym smoke GUI, gdy zmienia się mechanika zakładki Help.

Nie trzeba rozszerzać smoke GUI przy każdej zmianie tekstu, jeżeli mechanika widoku pozostaje bez zmian i test katalogu potwierdza nową treść.

## Checkpoint etapu

Przy końcu każdego większego etapu raport i handoff muszą zawierać sekcję:

`Aktualizacja Help Center`

Sekcja ma wskazywać:

- dodane lub zmienione tematy,
- najważniejsze nowe frazy wyszukiwania,
- wynik testów Help,
- wynik testu ręcznego,
- ewentualne świadome braki przeniesione do kolejnego etapu.

## Odpowiedzialność

Podczas planowania i implementowania nowych etapów należy od początku uwzględniać aktualizację `app/help_catalog.py` i testów Help. Nie należy odkładać całej dokumentacji do osobnego, późniejszego etapu.

Właściciel projektu zatwierdza funkcję oraz poprawność jej opisu użytkowego. Agent wykonujący implementację odpowiada za przygotowanie treści, testów, commitu, pushu i wpisu w PR.
