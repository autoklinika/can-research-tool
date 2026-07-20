# CRT — przekazanie UI Stage 1 do walidacji

## Stan

- gałąź: `agent/ui-engineering-shell-stage1`
- baza: `main` po scaleniu PR #21
- zakres: wyłącznie powłoka GUI typu engineering IDE

## Zmiany do sprawdzenia ręcznego

1. Górny toolbar jest kompaktowy i nie zabiera nadmiernej wysokości.
2. Activity Bar po lewej ma szerokość 46 px i działa przez ikony oraz tooltipy.
3. Explorer pokazuje tylko funkcje rzeczywiście dostępne w aplikacji.
4. Docki Projekt, Inspektor i Output można przesuwać, odpinać, zamykać i ponownie otwierać.
5. Skróty `Ctrl+B`, `Ctrl+Shift+I` i `Ctrl+J` sterują odpowiednimi panelami.
6. `Widok → Resetuj układ okna` przywraca układ domyślny.
7. Układ docków i geometria okna są odtwarzane po ponownym uruchomieniu.
8. Status projektu, bitrate, trybu i Capture jest czytelny.
9. Przegląd projektu pokazuje ostatnie sesje i zwartą konfigurację projektu.
10. Live Capture, zapisane sesje, Dekodery i Filtry otwierają się jak wcześniej.

## Kontrakty

Nie wolno w tym etapie zmieniać `CaptureService`, Kvasera, CANlib, formatu sesji,
kolejności zapisu ramek ani semantyki filtrów.
