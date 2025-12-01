from io import BytesIO
import re
from typing import Dict, List, Optional, Tuple

import requests
import streamlit as st
from PIL import Image

OCR_ENDPOINT = "https://api.ocr.space/parse/image"
SCRYFALL_NAMED_ENDPOINT = "https://api.scryfall.com/cards/named"
SCRYFALL_SETS_ENDPOINT = "https://api.scryfall.com/sets"
MAX_CANDIDATES = 5
MAX_UPLOAD_BYTES = 1024 * 1024  # 1 MB cap expected by OCR provider

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

@st.cache_data(show_spinner=False)
def load_set_catalog() -> Dict[str, Dict[str, str]]:
    try:
        response = requests.get(SCRYFALL_SETS_ENDPOINT, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return {}

    data = response.json().get("data", [])
    catalog: Dict[str, Dict[str, str]] = {}
    for entry in data:
        code = entry.get("code")
        if not code:
            continue
        catalog[code.upper()] = {
            "name": entry.get("name", code.upper()),
            "released_at": entry.get("released_at"),
        }
    return catalog

SET_CODE_PATTERN = re.compile(r"\b([A-Z0-9]{2,5})\b")

def extract_set_codes(raw_text: str, valid_codes: Dict[str, Dict[str, str]], max_codes: int = 3) -> List[str]:
    if not raw_text or not valid_codes:
        return []

    lines = [line.upper() for line in raw_text.splitlines() if line.strip()]
    prioritized = [line for line in lines if "/" in line or any(ch.isdigit() for ch in line)]
    scan_lines = prioritized or lines

    detected: List[str] = []
    for line in scan_lines:
        for token in SET_CODE_PATTERN.findall(line):
            if token.isdigit():
                continue
            if token not in valid_codes:
                continue
            if token in detected:
                continue
            detected.append(token)
            if len(detected) >= max_codes:
                return detected
    return detected

def downscale_image_to_limit(image: Image.Image, max_bytes: int = MAX_UPLOAD_BYTES) -> Tuple[Optional[bytes], Optional[int], Optional[str]]:
    working = image
    if working.mode not in ("RGB", "L"):
        working = working.convert("RGB")
    elif working.mode == "L":
        working = working.convert("RGB")

    width, height = working.size
    quality = 90
    while True:
        buffer = BytesIO()
        working.save(buffer, format="JPEG", quality=quality, optimize=True)
        size = buffer.tell()
        if size <= max_bytes:
            buffer.seek(0)
            return buffer.getvalue(), size, None
        if quality > 55:
            quality -= 5
            continue
        new_width = int(width * 0.85)
        new_height = int(height * 0.85)
        if min(new_width, new_height) < 300:
            return None, None, "Unable to shrink image under 1024 KB. Please upload a tighter crop."
        width, height = new_width, new_height
        working = working.resize((width, height), Image.LANCZOS)
        quality = 85

def call_ocr_space(image_bytes: bytes, api_key: str) -> Tuple[str, Optional[str]]:
    if not api_key:
        return "", "OCR.Space API key is required to run the scanner."
    files = {"file": ("upload.jpg", image_bytes)}
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
def fetch_card_by_name(card_name: str, set_code: Optional[str] = None) -> Tuple[Optional[Dict], Optional[str]]:
    attempts = []
    if set_code:
        attempts.append({"fuzzy": card_name, "set": set_code.lower()})
    attempts.append({"fuzzy": card_name})

    last_error: Optional[str] = None
    for params in attempts:
        try:
            response = requests.get(SCRYFALL_NAMED_ENDPOINT, params=params, timeout=15)
        except requests.RequestException as exc:
            last_error = f"Scryfall request failed: {exc}"
            continue

        if response.status_code != 200:
            detail = (
                response.json().get("details")
                if response.headers.get("content-type", "").startswith("application/json")
                else response.text
            )
            last_error = f"Scryfall error ({response.status_code}): {detail}"
            continue

        return response.json(), None

    return None, last_error or "Unknown Scryfall error"

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
    set_candidates: List[str] = []
    detected_set_code: Optional[str] = None
    set_catalog: Dict[str, Dict[str, str]] = {}

    if uploaded:
        image = Image.open(uploaded)
        st.image(image, caption="Uploaded image", width=450)

        with st.spinner("Optimizing image …"):
            optimized_bytes, optimized_size, sizing_error = downscale_image_to_limit(image)

        if sizing_error:
            st.error(sizing_error)
            optimized_bytes = None
        else:
            size_kb = (optimized_size or 0) / 1024
            st.caption(f"Compressed upload: {size_kb:.0f} KB (≤ 1024 KB requirement)")

        if optimized_bytes:
            with st.spinner("Running OCR..."):
                ocr_text, ocr_error = call_ocr_space(optimized_bytes, api_key)
        else:
            ocr_text, ocr_error = "", "Image compression failed."

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

            set_catalog = load_set_catalog()
            set_candidates = extract_set_codes(ocr_text, set_catalog)
            if set_candidates:
                detected_set_code = set_candidates[0]
                readable_sets = ", ".join(
                    f"{code} – {set_catalog.get(code, {}).get('name', 'Unknown')}" for code in set_candidates
                )
                st.success(f"Detected set codes: {readable_sets}")
            else:
                st.info("Set symbol not detected. You can type a set code manually if needed.")
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
        set_override = st.text_input(
            "Set code override",
            value=detected_set_code or "",
            help="Auto-detected from the collector line (e.g., DMU, LTR). Leave blank for the default Scryfall printing.",
        )
        submitted = st.form_submit_button("Fetch card details")

    search_name = (manual_name or selected_candidate).strip()
    chosen_set_code = (set_override or detected_set_code or "").strip().lower()
    if submitted:
        if not search_name or search_name == "No automatic suggestions":
            st.warning("Please enter a card name before fetching.")
        else:
            with st.spinner(f"Fetching {search_name} from Scryfall..."):
                card, error = fetch_card_by_name(search_name, chosen_set_code or None)
            if error:
                st.error(error)
            elif card:
                render_card_details(card)

if __name__ == "__main__":
    main()
