# MTG Card Recognition Software

Ein Python-basiertes Kartenerkennungssystem für Magic: The Gathering Karten.

## Features

- **Kartenerkennung**: Erkennt MTG-Karten aus Fotos/Scans
- **Versionsidentifikation**: Identifiziert die korrekte Edition (Set) der Karte
- **Scryfall API Integration**: Nutzt die offizielle MTG-Datenbank
- **OCR**: Liest Kartennamen mittels Texterkennung
- **Bild-Hashing**: Vergleicht Kartenbilder für präzise Identifikation

## Installation

1. **Tesseract OCR installieren**:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install tesseract-ocr
   
   # macOS
   brew install tesseract
   
   # Windows: Download von https://github.com/UB-Mannheim/tesseract/wiki
   ```

2. **Python-Abhängigkeiten installieren**:
   ```bash
   pip install -r requirements.txt
   ```

## Verwendung

### Einzelne Karte erkennen
```python
from mtg_recognizer import MTGCardRecognizer

recognizer = MTGCardRecognizer()
result = recognizer.recognize_card("path/to/card_image.jpg")

print(f"Karte: {result['name']}")
print(f"Set: {result['set_name']}")
print(f"Konfidenz: {result['confidence']}%")
```

### CLI-Nutzung
```bash
python main.py --image path/to/card.jpg
python main.py --webcam  # Live-Erkennung via Webcam
```

## Projektstruktur

```
mtg-card-recognition/
├── main.py                 # Haupteinstiegspunkt
├── mtg_recognizer/
│   ├── __init__.py
│   ├── recognizer.py       # Haupterkennungslogik
│   ├── image_processor.py  # Bildvorverarbeitung
│   ├── ocr_engine.py       # OCR für Kartennamen
│   ├── scryfall_api.py     # Scryfall API Client
│   └── card_matcher.py     # Kartenabgleich & Versionserkennung
├── requirements.txt
└── README.md
```

## API

Die Software nutzt die [Scryfall API](https://scryfall.com/docs/api) für:
- Kartensuche nach Name
- Abruf aller Versionen einer Karte
- Bildvergleich zur Versionserkennung

## Lizenz

MIT License
