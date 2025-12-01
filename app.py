#!/usr/bin/env python3
"""
MTG Card Recognition - Streamlit Web App

Starte mit: streamlit run app.py
"""

import streamlit as st
import requests
from PIL import Image
import io
import numpy as np
from typing import Optional, Dict, List

# Page Config
st.set_page_config(
    page_title="MTG Card Recognition",
    page_icon="🃏",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1a1a2e;
        text-align: center;
        margin-bottom: 2rem;
    }
    .card-info {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 1.5rem;
        margin: 1rem 0;
    }
    .price-tag {
        font-size: 1.2rem;
        font-weight: bold;
        color: #28a745;
    }
    .set-badge {
        background-color: #6c757d;
        color: white;
        padding: 0.25rem 0.5rem;
        border-radius: 5px;
        font-size: 0.9rem;
    }
    .rarity-common { color: #1a1a1a; }
    .rarity-uncommon { color: #707883; }
    .rarity-rare { color: #a58e4a; }
    .rarity-mythic { color: #bf4427; }
</style>
""", unsafe_allow_html=True)


class ScryfallAPI:
    """Scryfall API Client"""
    
    BASE_URL = "https://api.scryfall.com"
    
    @staticmethod
    @st.cache_data(ttl=3600)
    def search_card(name: str) -> Optional[Dict]:
        """Sucht eine Karte nach Namen"""
        try:
            response = requests.get(
                f"{ScryfallAPI.BASE_URL}/cards/named",
                params={"fuzzy": name},
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            st.error(f"API Fehler: {e}")
        return None
    
    @staticmethod
    @st.cache_data(ttl=3600)
    def get_all_prints(card_name: str) -> List[Dict]:
        """Holt alle Versionen einer Karte"""
        try:
            card = ScryfallAPI.search_card(card_name)
            if not card:
                return []
            
            oracle_id = card.get("oracle_id")
            if not oracle_id:
                return [card]
            
            response = requests.get(
                f"{ScryfallAPI.BASE_URL}/cards/search",
                params={"q": f"oracleid:{oracle_id}", "unique": "prints", "order": "released"},
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
        except Exception as e:
            st.error(f"API Fehler: {e}")
        return []
    
    @staticmethod
    @st.cache_data(ttl=3600)
    def autocomplete(query: str) -> List[str]:
        """Autovervollständigung für Kartennamen"""
        if len(query) < 2:
            return []
        try:
            response = requests.get(
                f"{ScryfallAPI.BASE_URL}/cards/autocomplete",
                params={"q": query},
                timeout=5
            )
            if response.status_code == 200:
                return response.json().get("data", [])
        except:
            pass
        return []
    
    @staticmethod
    def get_random_card() -> Optional[Dict]:
        """Holt eine zufällige Karte"""
        try:
            response = requests.get(
                f"{ScryfallAPI.BASE_URL}/cards/random",
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None


def get_card_image_url(card: Dict, size: str = "normal") -> Optional[str]:
    """Extrahiert die Bild-URL einer Karte"""
    image_uris = card.get("image_uris", {})
    if image_uris:
        return image_uris.get(size)
    
    card_faces = card.get("card_faces", [])
    if card_faces and card_faces[0].get("image_uris"):
        return card_faces[0]["image_uris"].get(size)
    return None


def format_price(prices: Dict) -> str:
    """Formatiert Preisangaben"""
    usd = prices.get("usd")
    eur = prices.get("eur")
    
    parts = []
    if usd:
        parts.append(f"${usd}")
    if eur:
        parts.append(f"EUR {eur}")
    
    return " / ".join(parts) if parts else "N/A"


def get_rarity_color(rarity: str) -> str:
    """Gibt die Farbe für die Seltenheit zurück"""
    colors = {
        "common": "#1a1a1a",
        "uncommon": "#707883", 
        "rare": "#a58e4a",
        "mythic": "#bf4427",
        "special": "#905d98",
        "bonus": "#905d98"
    }
    return colors.get(rarity, "#1a1a1a")


def display_card(card: Dict, show_all_versions: bool = False):
    """Zeigt eine Karte an"""
    col1, col2 = st.columns([1, 2])
    
    with col1:
        image_url = get_card_image_url(card, "large")
        if image_url:
            st.image(image_url, use_container_width=True)
        else:
            st.warning("Kein Bild verfügbar")
    
    with col2:
        st.markdown(f"## {card.get('name', 'Unbekannt')}")
        
        set_name = card.get("set_name", "Unknown")
        set_code = card.get("set", "???").upper()
        collector_number = card.get("collector_number", "")
        rarity = card.get("rarity", "common")
        rarity_color = get_rarity_color(rarity)
        
        st.markdown(f"""
        **Set:** {set_name} ({set_code}) - **#{collector_number}**  
        **Seltenheit:** <span style="color: {rarity_color}; font-weight: bold;">{rarity.capitalize()}</span>
        """, unsafe_allow_html=True)
        
        mana_cost = card.get("mana_cost", "")
        type_line = card.get("type_line", "")
        st.markdown(f"**Manakosten:** {mana_cost}  \n**Typ:** {type_line}")
        
        oracle_text = card.get("oracle_text", "")
        if oracle_text:
            st.markdown("**Kartentext:**")
            st.text(oracle_text)
        
        power = card.get("power")
        toughness = card.get("toughness")
        if power and toughness:
            st.markdown(f"**Stärke/Widerstand:** {power}/{toughness}")
        
        prices = card.get("prices", {})
        price_str = format_price(prices)
        st.markdown(f"**Preis:** :green[{price_str}]")
        
        scryfall_uri = card.get("scryfall_uri", "")
        if scryfall_uri:
            st.markdown(f"[Auf Scryfall ansehen]({scryfall_uri})")
    
    if show_all_versions:
        st.markdown("---")
        st.markdown("### Alle verfügbaren Versionen")
        
        versions = ScryfallAPI.get_all_prints(card.get("name", ""))
        
        if versions:
            st.write(f"Gefunden: **{len(versions)}** Versionen")
            
            version_data = []
            for v in versions:
                version_data.append({
                    "Set": v.get("set_name", ""),
                    "Code": v.get("set", "").upper(),
                    "#": v.get("collector_number", ""),
                    "Seltenheit": v.get("rarity", "").capitalize(),
                    "Preis (USD)": f"${v.get('prices', {}).get('usd', 'N/A')}",
                    "Jahr": v.get("released_at", "")[:4] if v.get("released_at") else ""
                })
            
            st.dataframe(version_data, use_container_width=True, hide_index=True)
            
            st.markdown("#### Bildergalerie")
            cols = st.columns(5)
            for i, v in enumerate(versions[:15]):
                img_url = get_card_image_url(v, "small")
                if img_url:
                    with cols[i % 5]:
                        st.image(img_url, caption=f"{v.get('set', '').upper()}", use_container_width=True)


def main():
    """Hauptfunktion"""
    
    st.markdown('<h1 class="main-header">MTG Card Recognition</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #666;">Magic: The Gathering Kartenerkennung</p>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.markdown("## Optionen")
        
        search_mode = st.radio(
            "Suchmodus",
            ["Nach Name suchen", "Bild hochladen", "Zufällige Karte"],
            index=0
        )
        
        show_all_versions = st.checkbox("Alle Versionen anzeigen", value=True)
        
        st.markdown("---")
        st.markdown("### Info")
        st.markdown("""
        Diese App nutzt die [Scryfall API](https://scryfall.com/docs/api) 
        für Kartendaten und Bilder.
        
        **Features:**
        - Kartensuche nach Name
        - Alle Versionen einer Karte
        - Preisanzeige (USD/EUR)
        - Hochauflösende Bilder
        """)
    
    if search_mode == "Nach Name suchen":
        st.markdown("### Karte suchen")
        
        search_query = st.text_input(
            "Kartenname eingeben",
            placeholder="z.B. Lightning Bolt, Black Lotus, Counterspell...",
            key="card_search"
        )
        
        if search_query and len(search_query) >= 2:
            suggestions = ScryfallAPI.autocomplete(search_query)
            if suggestions:
                selected = st.selectbox(
                    "Vorschläge:",
                    [""] + suggestions[:10],
                    key="suggestions"
                )
                if selected:
                    search_query = selected
        
        if st.button("Suchen", type="primary") or (search_query and len(search_query) > 2):
            if search_query:
                with st.spinner("Suche Karte..."):
                    card = ScryfallAPI.search_card(search_query)
                    
                    if card:
                        display_card(card, show_all_versions)
                    else:
                        st.error(f"Karte '{search_query}' nicht gefunden.")
    
    elif search_mode == "Bild hochladen":
        st.markdown("### Kartenbild hochladen")
        
        uploaded_file = st.file_uploader(
            "Bild einer MTG Karte hochladen",
            type=["jpg", "jpeg", "png", "webp"],
            help="Lade ein Foto einer MTG Karte hoch"
        )
        
        if uploaded_file:
            image = Image.open(uploaded_file)
            
            col1, col2 = st.columns(2)
            with col1:
                st.image(image, caption="Hochgeladenes Bild", use_container_width=True)
            
            with col2:
                st.markdown("#### Erkennungsergebnis")
                st.info("""
                **Hinweis:** Geben Sie den Kartennamen manuell ein:
                """)
                
                manual_name = st.text_input("Kartenname eingeben:", key="manual_name")
                
                if manual_name and st.button("Karte suchen", key="search_manual"):
                    with st.spinner("Suche..."):
                        card = ScryfallAPI.search_card(manual_name)
                        if card:
                            st.success(f"Gefunden: **{card.get('name')}**")
                            display_card(card, show_all_versions)
                        else:
                            st.error("Karte nicht gefunden")
    
    elif search_mode == "Zufällige Karte":
        st.markdown("### Zufällige Karte")
        
        if st.button("Neue zufällige Karte", type="primary"):
            with st.spinner("Lade zufällige Karte..."):
                card = ScryfallAPI.get_random_card()
                if card:
                    display_card(card, show_all_versions)
                else:
                    st.error("Fehler beim Laden")
        else:
            st.info("Klicke auf den Button um eine zufällige MTG Karte zu sehen!")
    
    st.markdown("---")
    st.markdown(
        '<p style="text-align: center; color: #888; font-size: 0.8rem;">'
        'Made with Streamlit | Powered by Scryfall API'
        '</p>',
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()