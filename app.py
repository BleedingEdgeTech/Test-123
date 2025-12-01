import re
from typing import Dict, List, Optional, Tuple

import requests
import streamlit as st
from PIL import Image

OCR_ENDPOINT = "https://api.ocr.space/parse/image"
SCRYFALL_NAMED_ENDPOINT = "https://api.scryfall.com/cards/named"
MAX_CANDIDATES = 5

def _clean_line(line: str) -> str:
    # OCR noise filter keeps only letters, spaces, dashes, and apostrophes
    return re.sub(r"[^A-Za-z' -]", "", line).strip()

def extract_name_candidates(raw_text: str, max_candidates: int = MAX_CANDIDATES) -> List[str]:
    candidates: List[str] = []
    for line in raw_text.splitlines():
        cleaned = _clean_line(line)
        if not cleaned:
            continue
        word_count = len(cleaned.split())
        if word_count == 0 or word_count > 4:
            continue
        if cleaned.lower() in (c.lower() for c in candidates):
            continue
        candidates.append(cleaned)
        if len(candidates) >= max_candidates:
            break
    return candidates

def call_ocr_space(image_bytes: bytes, api_key: str) -> Tuple[str, Optional[str]]:
    if not api_key:
        return "", "OCR.Space API key is required to run the scanner."
    files = {"file": ("upload.png", image_bytes)}
    data = {
        "language": "eng",
        "isOverlayRequired": False,
        "scale": True,
    }
    headers = {"apikey": api_key}
    try:
        response = requests.post(OCR_ENDPOINT, files=files, data=data, headers=headers, timeout=45)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        return "", f"OCR request failed: {exc}"

    if payload.get("IsErroredOnProcessing"):
        message = payload.get("ErrorMessage") or payload.get("ErrorDetails") or "Unknown OCR error"
        return "", f"OCR error: {message}"

    parsed_results = payload.get("ParsedResults") or []
    if not parsed_results:
        return "", "No text detected in the uploaded image."

    combined_text = "\n".join(res.get("ParsedText", "") for res in parsed_results)
    return combined_text.strip(), None

@st.cache_data(show_spinner=False)
def fetch_card_by_name(card_name: str) -> Tuple[Optional[Dict], Optional[str]]:
    params = {"fuzzy": card_name}
    try:
        response = requests.get(SCRYFALL_NAMED_ENDPOINT, params=params, timeout=15)
    except requests.RequestException as exc:
        return None, f"Scryfall request failed: {exc}"

    if response.status_code != 200:
        detail = response.json().get("details") if response.headers.get("content-type", "").startswith("application/json") else response.text
        return None, f"Scryfall error ({response.status_code}): {detail}"

    return response.json(), None

def card_image_url(card: Dict) -> Optional[str]:
    if "image_uris" in card:
        return card["image_uris"].get("normal") or card["image_uris"].get("large")
    faces = card.get("card_faces") or []
    if faces:
        first_face = faces[0]
        uris = first_face.get("image_uris") or {}
        return uris.get("normal") or uris.get("large")
    return None

def render_card_details(card: Dict) -> None:
    col_image, col_meta = st.columns((1, 1))
    img_url = card_image_url(card)
    if img_url:
        col_image.image(img_url, caption=card.get("name", "Unknown card"))
    else:
        col_image.info("No preview image available for this card variant.")

    oracle_text = card.get("oracle_text")
    if not oracle_text and card.get("card_faces"):
        oracle_text = "\n---\n".join(face.get("oracle_text", "") for face in card["card_faces"])

    col_meta.markdown(
        f"**Name:** {card.get('name', '—')}\n\n"
        f"**Mana Cost:** {card.get('mana_cost', '—')}\n\n"
        f"**Type Line:** {card.get('type_line', '—')}\n\n"
        f"**Set:** {card.get('set_name', '—')} ({card.get('set').upper() if card.get('set') else '—'})\n\n"
        f"**Rarity:** {card.get('rarity', '—').title() if card.get('rarity') else '—'}"
    )

    if oracle_text:
        st.subheader("Oracle Text")
        st.write(oracle_text)

    prices = card.get("prices") or {}
    legalities = card.get("legalities") or {}
    with st.expander("Prices & Legalities", expanded=False):
        st.markdown(
            "\n".join(
                [
                    f"- **USD:** {prices.get('usd') or 'n/a'}",
                    f"- **USD Foil:** {prices.get('usd_foil') or 'n/a'}",
                    f"- **EUR:** {prices.get('eur') or 'n/a'}",
                    f"- **TIX:** {prices.get('tix') or 'n/a'}",
                ]
            )
        )
        st.markdown("**Formats**")
        legal_text = ", ".join(f"{fmt.title()}: {status}" for fmt, status in legalities.items()) or "No data"
        st.write(legal_text)

def main() -> None:
    st.set_page_config(page_title="MTG Card Scanner", page_icon="🪄", layout="wide")
    st.title("MTG Card Scanner")
    st.write(
        "Upload a Magic: The Gathering card photo, let OCR extract the title, and fetch the official details from Scryfall."
    )

    with st.sidebar:
        st.header("Setup")
        st.write(
            "Grab a free OCR.Space API key at [ocr.space/ocrapi](https://ocr.space/ocrapi). Each scan uses one API call."
        )
        api_key = st.text_input("OCR.Space API Key", type="password", help="Stored only in your browser session.")
        st.divider()
        st.markdown(
            "**Tips**\n\n"
            "- Use well-lit, in-focus shots.\n"
            "- Crop close to the title line for better OCR accuracy.\n"
            "- If OCR misses the name, type it manually before fetching."
        )

    uploaded = st.file_uploader("Upload a card photo", type=["png", "jpg", "jpeg", "webp"])
    ocr_text = ""
    candidates: List[str] = []

    if uploaded:
        image = Image.open(uploaded)
        st.image(image, caption="Uploaded image", width=450)
        image_bytes = uploaded.getvalue()

        with st.spinner("Running OCR..."):
            ocr_text, ocr_error = call_ocr_space(image_bytes, api_key)

        if ocr_error:
            st.error(ocr_error)
        else:
            st.subheader("Detected Text")
            st.text_area("OCR Output", value=ocr_text, height=150)
            candidates = extract_name_candidates(ocr_text)
            if candidates:
                st.success(f"Suggested card names: {', '.join(candidates)}")
            else:
                st.info("Could not confidently extract a card title. Try typing it manually.")
    else:
        st.info("Upload a card image to start scanning.")

    with st.form("card-search"):
        selected_candidate = st.selectbox(
            "Candidate names", options=candidates or ["No automatic suggestions"], index=0, disabled=not candidates
        )
        manual_name = st.text_input(
            "Card name override",
            value=selected_candidate if candidates else "",
            help="Use this when OCR suggestions are incomplete or incorrect.",
        )
        submitted = st.form_submit_button("Fetch card details")

    search_name = (manual_name or selected_candidate).strip()
    if submitted:
        if not search_name or search_name == "No automatic suggestions":
            st.warning("Please enter a card name before fetching.")
        else:
            with st.spinner(f"Fetching {search_name} from Scryfall..."):
                card, error = fetch_card_by_name(search_name)
            if error:
                st.error(error)
            elif card:
                render_card_details(card)

if __name__ == "__main__":
    main()
