## Cel i zakres

<!-- Opisz problem, rozwiązanie i świadomie wyłączony zakres. -->

## Zachowane kontrakty

- [ ] Nie zmieniono nieświadomie `CaptureService`, Kvasera ani lifecycle CANlib.
- [ ] Nie zmieniono nieświadomie CAN TX/RX.
- [ ] Nie zmieniono nieświadomie formatu sesji, markerów ani kolejności pełnego zapisu surowych ramek.
- [ ] Nie zmieniono nieświadomie schematu indeksów, bounded modelu ani `.crt/project.sqlite`.
- [ ] Każda świadoma zmiana architektoniczna została opisana i zatwierdzona osobno.

## Walidacja

- [ ] Dodano lub zaktualizowano testy rdzenia.
- [ ] Dodano lub zaktualizowano wymagane smoki GUI.
- [ ] Wykonano właściwe workflowy GitHub-hosted.
- [ ] Wykonano test ręczny, jeżeli zmiana dotyczy zachowania użytkowego.
- [ ] Zapisano funkcjonalny checkpoint SHA.

## Aktualizacja Help Center

Każda nowa albo zmieniona funkcja zatwierdzona jako gotowa musi zostać opisana w Help Center w tym samym etapie.

- [ ] Zaktualizowano `app/help_catalog.py` albo dodano uzasadnienie `Help Center: nie dotyczy`.
- [ ] Opis obejmuje lokalizację funkcji, użycie, interpretację wyniku i istotne ograniczenia.
- [ ] Dodano lub zaktualizowano słowa kluczowe wyszukiwarki.
- [ ] Sprawdzono linki do powiązanych tematów.
- [ ] Zaktualizowano `tests/test_help_catalog.py`, jeżeli dodano nowy temat lub wymagany zakres.
- [ ] Testy Help Center zakończyły się sukcesem.
- [ ] Ręcznie sprawdzono treść i nawigację dla nowej funkcji.

### Zmienione tematy Help

<!-- Wymień identyfikatory lub tytuły artykułów. -->

### Help Center: nie dotyczy

<!-- Wypełnij tylko dla refaktoryzacji, testów, CI lub zmian całkowicie niewidocznych dla użytkownika. -->

## Dokumentacja i checkpoint

- [ ] Zaktualizowano raport etapu.
- [ ] Zapisano handoff i dokładny punkt kontynuacji.
- [ ] Wykonano commit i push.
- [ ] PR pozostaje draftem lub został oznaczony jako ready zgodnie z wyraźną decyzją właściciela.
- [ ] Nie wykonano merge bez wyraźnego polecenia właściciela.

Polityka obowiązkowej aktualizacji Pomocy:

`docs/CRT_HELP_MAINTENANCE_POLICY_PL.md`
