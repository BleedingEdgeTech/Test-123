# MTG Card Scanner

Streamlit app that converts a Magic: The Gathering card photo into structured data by combining OCR.Space for text extraction and the Scryfall API for authoritative card details.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open the printed local URL in your browser.

## Usage

1. Obtain a free OCR key from https://ocr.space/ocrapi and paste it in the Streamlit sidebar.
2. Upload a clear, cropped photo of the card front.
3. Review the detected title suggestions, optionally correct it, then fetch the Scryfall details.

The OCR key stays in your browser session only. All Scryfall lookups are anonymous and rate-limited according to their public API policy.

### Image requirements

- The app automatically recompresses uploads to stay under 1 MB before sending them to OCR.Space.
- If a photo is too large to shrink safely, crop it tighter around the card and try again.

### Automatic set detection

- The OCR pass also scans for the collector-line set code (e.g., `DMU`, `LTR`).
- When a code is found, the app queries the matching printing on Scryfall automatically.
- You can override the detected code in the form if the scan misreads the collector line.