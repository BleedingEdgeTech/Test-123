# MTG Card Scanner

Streamlit-App, die ein Foto einer Magic: The Gathering-Karte analysiert, Name und Set per OCR erkennt und die offiziellen Kartendetails von Scryfall abruft.

## Schnellstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Die App öffnet sich im Browser unter der angezeigten URL.

## Benutzung

1. Kostenlosen OCR-Key von https://ocr.space/ocrapi holen und in der Sidebar eingeben.
2. Ein gut belichtetes, scharfes Foto der Karte hochladen.
3. Namen und Set prüfen/korrigieren, dann auf „Karte abrufen" klicken.

Der API-Key bleibt nur in der Browser-Session gespeichert. Scryfall-Anfragen erfolgen anonym und unterliegen deren Rate-Limit.

## Features

| Feature | Beschreibung |
|---------|--------------|
| **Bildkomprimierung** | Uploads werden automatisch auf ≤ 1 MB JPEG komprimiert. |
| **OCR** | OCR.Space extrahiert den Text; daraus werden Kartennamen-Kandidaten abgeleitet. |
| **Set-Erkennung** | Die App erkennt Set-Codes (z. B. `DMU`, `LTR`) und fragt das passende Printing ab. |
| **Fallback** | Schlägt die Set-spezifische Suche fehl, wird automatisch ein beliebiges Printing geladen. |