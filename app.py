"""
MTG Card Scanner – Streamlit app
Upload a Magic: The Gathering card photo, auto-detect the card name & set via OCR,
and fetch official details from Scryfall.
"""

from io import BytesIO
import re
from typing import Dict, List, Optional, Tuple

import requests
import streamlit as st
from PIL import Image

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
OCR_ENDPOINT = "https://api.ocr.space/parse/image"
SCRYFALL_CARDS_NAMED = "https://api.scryfall.com/cards/named"
SCRYFALL_SETS = "https://api.scryfall.com/sets"

MAX_UPLOAD_BYTES = 1024 * 1024  # 1 MB limit for OCR.Space free tier
MAX_NAME_CANDIDATES = 5
SET_CODE_REGEX = re.compile(r"\b([A-Z0-9]{2,5})\b")

# ──────────────────────────────────────────────────────────────────────────────
# Image helpers
# ──────────────────────────────────────────────────────────────────────────────

def compress_image(image: Image.Image, max_bytes: int = MAX_UPLOAD_BYTES) -> Tuple[bytes, int]:
    """
    Compress/downscale an image to fit within *max_bytes*.
    Returns (jpeg_bytes, final_size).
    Raises ValueError if compression fails after exhausting options.
    """
    img = image.convert("RGB") if image.mode not in ("RGB", "L") else image.convert("RGB")
    width, height = img.size
    quality = 90

    while True:
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        size = buf.tell()
        if size <= max_bytes:
            return buf.getvalue(), size

        # Lower quality first
        if quality > 50:
            quality -= 10
            continue

        # Then shrink dimensions
        new_w, new_h = int(width * 0.8), int(height * 0.8)
        if min(new_w, new_h) < 200:
            raise ValueError("Cannot compress image below 1 MB without excessive quality loss.")
        width, height = new_w, new_h
        img = img.resize((width, height), Image.LANCZOS)
        quality = 85


# ──────────────────────────────────────────────────────────────────────────────
# OCR helpers
# ──────────────────────────────────────────────────────────────────────────────

def run_ocr(image_bytes: bytes, api_key: str) -> Tuple[str, Optional[str]]:
    """
    Call OCR.Space and return (extracted_text, error_message).
    """
    if not api_key:
        return "", "Bitte einen OCR.Space API-Key in der Sidebar eingeben."

    try:
        resp = requests.post(
            OCR_ENDPOINT,
            files={"file": ("card.jpg", image_bytes)},
            data={"language": "eng", "scale": True, "isOverlayRequired": False},
            headers={"apikey": api_key},
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        return "", f"OCR-Anfrage fehlgeschlagen: {exc}"

    if payload.get("IsErroredOnProcessing"):
        msg = payload.get("ErrorMessage") or payload.get("ErrorDetails") or "Unbekannter OCR-Fehler"
        return "", f"OCR-Fehler: {msg}"

    results = payload.get("ParsedResults") or []
    text = "\n".join(r.get("ParsedText", "") for r in results).strip()
    if not text:
        return "", "Kein Text im Bild erkannt."
    return text, None


def _clean(line: str) -> str:
    return re.sub(r"[^A-Za-z' -]", "", line).strip()


def extract_card_names(ocr_text: str, limit: int = MAX_NAME_CANDIDATES) -> List[str]:
    """
    Heuristically extract likely card-name candidates from OCR output.
    """
    seen: set[str] = set()
    candidates: List[str] = []
    for raw in ocr_text.splitlines():
        clean = _clean(raw)
        if not clean or len(clean.split()) > 5:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(clean)
        if len(candidates) >= limit:
            break
    return candidates


# ──────────────────────────────────────────────────────────────────────────────
# Set detection
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_set_catalog() -> Dict[str, str]:
    """
    Download the full Scryfall set list and return {CODE: set_name}.
    """
    try:
        resp = requests.get(SCRYFALL_SETS, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except requests.RequestException:
        return {}
    return {s["code"].upper(): s.get("name", s["code"].upper()) for s in data if s.get("code")}


def detect_set_codes(ocr_text: str, catalog: Dict[str, str], limit: int = 3) -> List[str]:
    """
    Find valid set codes inside the OCR text (e.g., DMU, MKM, LTR).
    """
    found: List[str] = []
    for token in SET_CODE_REGEX.findall(ocr_text.upper()):
        if token.isdigit():
            continue
        if token in catalog and token not in found:
            found.append(token)
            if len(found) >= limit:
                break
    return found


# ──────────────────────────────────────────────────────────────────────────────
# Scryfall card fetch
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def fetch_card(name: str, set_code: Optional[str] = None) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Query Scryfall for a card by fuzzy name, optionally limited to a set.
    Falls back to any printing if set-specific lookup fails.
    """
    queries = []
    if set_code:
        queries.append({"fuzzy": name, "set": set_code.lower()})
    queries.append({"fuzzy": name})

    last_err: Optional[str] = None
    for params in queries:
        try:
            resp = requests.get(SCRYFALL_CARDS_NAMED, params=params, timeout=15)
        except requests.RequestException as exc:
            last_err = f"Scryfall-Anfrage fehlgeschlagen: {exc}"
            continue

        if resp.status_code == 200:
            return resp.json(), None

        detail = ""
        if resp.headers.get("content-type", "").startswith("application/json"):
            detail = resp.json().get("details", resp.text)
        else:
            detail = resp.text
        last_err = f"Scryfall ({resp.status_code}): {detail}"

    return None, last_err


def get_card_image_url(card: Dict) -> Optional[str]:
    uris = card.get("image_uris") or {}
    if uris:
        return uris.get("normal") or uris.get("large")
    faces = card.get("card_faces") or []
    if faces:
        face_uris = faces[0].get("image_uris") or {}
        return face_uris.get("normal") or face_uris.get("large")
    return None


# ──────────────────────────────────────────────────────────────────────────────
# UI rendering
# ──────────────────────────────────────────────────────────────────────────────

def render_card(card: Dict) -> None:
    col_img, col_meta = st.columns([1, 1])

    img_url = get_card_image_url(card)
    if img_url:
        col_img.image(img_url, caption=card.get("name", "Karte"), use_container_width=True)
    else:
        col_img.info("Kein Bild verfügbar.")

    oracle = card.get("oracle_text") or ""
    if not oracle and card.get("card_faces"):
        oracle = "\n---\n".join(f.get("oracle_text", "") for f in card["card_faces"])

    col_meta.markdown(
        f"**Name:** {card.get('name', '–')}\n\n"
        f"**Manakosten:** {card.get('mana_cost', '–')}\n\n"
        f"**Typ:** {card.get('type_line', '–')}\n\n"
        f"**Set:** {card.get('set_name', '–')} ({(card.get('set') or '').upper()})\n\n"
        f"**Seltenheit:** {(card.get('rarity') or '–').title()}"
    )

    if oracle:
        st.subheader("Oracle-Text")
        st.write(oracle)

    prices = card.get("prices") or {}
    legalities = card.get("legalities") or {}
    with st.expander("Preise & Legalität"):
        st.markdown(
            f"- **USD:** {prices.get('usd') or 'n/a'}\n"
            f"- **USD Foil:** {prices.get('usd_foil') or 'n/a'}\n"
            f"- **EUR:** {prices.get('eur') or 'n/a'}\n"
            f"- **TIX:** {prices.get('tix') or 'n/a'}"
        )
        st.markdown("**Formate:** " + ", ".join(f"{k.title()}: {v}" for k, v in legalities.items()))


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title="MTG Card Scanner", page_icon="🃏", layout="wide")
    st.title("🃏 MTG Card Scanner")
    st.caption("Lade ein Foto einer Magic-Karte hoch – Name & Set werden automatisch erkannt.")

    # Sidebar – API key & tips
    with st.sidebar:
        st.header("Einstellungen")
        api_key = st.text_input(
            "OCR.Space API-Key",
            type="password",
            help="Kostenlos unter https://ocr.space/ocrapi",
        )
        st.divider()
        st.markdown(
            "**Tipps**\n"
            "- Gutes Licht & scharfes Bild verwenden.\n"
            "- Eng um den Kartentitel zuschneiden verbessert die Erkennung.\n"
            "- Bei Fehlschlägen den Namen manuell eingeben."
        )

    # File upload
    uploaded = st.file_uploader("Kartenbild hochladen", type=["png", "jpg", "jpeg", "webp"])

    ocr_text = ""
    name_candidates: List[str] = []
    set_candidates: List[str] = []
    catalog: Dict[str, str] = {}

    if uploaded:
        image = Image.open(uploaded)
        st.image(image, caption="Hochgeladenes Bild", width=400)

        # Compress
        try:
            img_bytes, img_size = compress_image(image)
            st.caption(f"Komprimiert: {img_size / 1024:.0f} KB (max 1024 KB)")
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

        # OCR
        with st.spinner("OCR läuft …"):
            ocr_text, ocr_err = run_ocr(img_bytes, api_key)

        if ocr_err:
            st.error(ocr_err)
        else:
            with st.expander("Erkannter Text", expanded=False):
                st.text(ocr_text)

            name_candidates = extract_card_names(ocr_text)
            if name_candidates:
                st.success(f"Mögliche Kartennamen: {', '.join(name_candidates)}")
            else:
                st.warning("Kein Kartenname erkannt – bitte manuell eingeben.")

            catalog = fetch_set_catalog()
            set_candidates = detect_set_codes(ocr_text, catalog)
            if set_candidates:
                labels = [f"{c} ({catalog.get(c, '?')})" for c in set_candidates]
                st.success(f"Erkannte Set-Codes: {', '.join(labels)}")
    else:
        st.info("Bitte ein Kartenbild hochladen, um zu starten.")

    # Search form
    with st.form("search"):
        default_name = name_candidates[0] if name_candidates else ""
        name_input = st.text_input("Kartenname", value=default_name)

        default_set = set_candidates[0] if set_candidates else ""
        set_input = st.text_input(
            "Set-Code (optional)",
            value=default_set,
            help="z. B. DMU, MKM, LTR – leer lassen für beliebiges Printing",
        )
        submit = st.form_submit_button("Karte abrufen")

    if submit:
        query_name = name_input.strip()
        query_set = set_input.strip().upper() or None
        if not query_name:
            st.warning("Bitte einen Kartennamen eingeben.")
        else:
            with st.spinner(f"Suche „{query_name}" auf Scryfall …"):
                card, err = fetch_card(query_name, query_set)
            if err:
                st.error(err)
            elif card:
                render_card(card)


if __name__ == "__main__":
    main()
