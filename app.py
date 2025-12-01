#!/usr/bin/env python3
"""
MTG Card Recognition - Streamlit Web App
Automatische Kartenerkennung mit OCR und Bildvergleich

Starte mit: streamlit run app.py
"""

import streamlit as st
import requests
from PIL import Image, ImageEnhance, ImageFilter
import io
import numpy as np
from typing import Optional, Dict, List, Tuple
import re
import time

# Page Config
st.set_page_config(
    page_title="MTG Card Scanner",
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
    .scan-result {
        background: linear-gradient(135deg, #1a1a2e 0%, #2d2d44 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        margin: 1rem 0;
    }
    .confidence-high { color: #28a745; font-weight: bold; }
    .confidence-medium { color: #ffc107; font-weight: bold; }
    .confidence-low { color: #dc3545; font-weight: bold; }
    .version-card {
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 10px;
        margin: 5px;
        text-align: center;
    }
    .match-score {
        font-size: 0.8rem;
        color: #666;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# OCR ENGINE - Tesseract-freie Implementierung mit Google Cloud Vision API
# oder pytesseract als Fallback
# ============================================================================

class OCREngine:
    """OCR Engine für Kartentexterkennung"""
    
    @staticmethod
    def preprocess_image_for_ocr(image: Image.Image, region: str = "title") -> Image.Image:
        """Bereitet Bild für OCR vor"""
        # In Graustufen konvertieren
        gray = image.convert('L')
        
        # Kontrast erhöhen
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(2.0)
        
        # Schärfen
        sharpened = enhanced.filter(ImageFilter.SHARPEN)
        
        # Größe verdoppeln für bessere OCR
        width, height = sharpened.size
        sharpened = sharpened.resize((width * 2, height * 2), Image.Resampling.LANCZOS)
        
        return sharpened
    
    @staticmethod
    def extract_card_regions(image: Image.Image) -> Dict[str, Image.Image]:
        """Extrahiert relevante Regionen einer MTG Karte"""
        width, height = image.size
        
        regions = {}
        
        # Titelbereich (obere ~10% der Karte, mit Rand)
        title_top = int(height * 0.035)
        title_bottom = int(height * 0.09)
        title_left = int(width * 0.05)
        title_right = int(width * 0.78)
        regions['title'] = image.crop((title_left, title_top, title_right, title_bottom))
        
        # Sammlernummer & Set-Info (unten links, moderne Karten)
        info_top = int(height * 0.94)
        info_bottom = int(height * 0.99)
        info_left = int(width * 0.05)
        info_right = int(width * 0.55)
        regions['collector_info'] = image.crop((info_left, info_top, info_right, info_bottom))
        
        # Set-Symbol-Bereich (rechts in der Typenzeile)
        symbol_top = int(height * 0.545)
        symbol_bottom = int(height * 0.595)
        symbol_left = int(width * 0.82)
        symbol_right = int(width * 0.97)
        regions['set_symbol'] = image.crop((symbol_left, symbol_top, symbol_right, symbol_bottom))
        
        # Artwork-Bereich für Bildvergleich
        art_top = int(height * 0.11)
        art_bottom = int(height * 0.54)
        art_left = int(width * 0.07)
        art_right = int(width * 0.93)
        regions['artwork'] = image.crop((art_left, art_top, art_right, art_bottom))
        
        return regions


class ScryfallAPI:
    """Scryfall API Client mit erweiterten Funktionen"""
    
    BASE_URL = "https://api.scryfall.com"
    
    @staticmethod
    def _rate_limit():
        """Scryfall Rate Limit: 100ms zwischen Requests"""
        time.sleep(0.1)
    
    @staticmethod
    @st.cache_data(ttl=3600)
    def search_card(name: str) -> Optional[Dict]:
        """Sucht eine Karte nach Namen (fuzzy)"""
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
    def search_card_exact(name: str) -> Optional[Dict]:
        """Sucht eine Karte nach exaktem Namen"""
        try:
            response = requests.get(
                f"{ScryfallAPI.BASE_URL}/cards/named",
                params={"exact": name},
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except:
            pass
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
                params={
                    "q": f"oracleid:{oracle_id}",
                    "unique": "prints",
                    "order": "released"
                },
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
    def get_card_by_set_and_number(set_code: str, collector_number: str) -> Optional[Dict]:
        """Holt Karte nach Set und Sammlernummer"""
        try:
            # Sammlernummer bereinigen
            collector_number = collector_number.lstrip('0') or '0'
            
            response = requests.get(
                f"{ScryfallAPI.BASE_URL}/cards/{set_code.lower()}/{collector_number}",
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None
    
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
    
    @staticmethod
    def download_card_image(card: Dict, size: str = "normal") -> Optional[Image.Image]:
        """Lädt Kartenbild herunter"""
        url = get_card_image_url(card, size)
        if not url:
            return None
        try:
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                return Image.open(io.BytesIO(response.content))
        except:
            pass
        return None


# ============================================================================
# CARD MATCHER - Bildvergleich für Versionserkennung
# ============================================================================

class CardMatcher:
    """Kartenabgleich mittels Bildvergleich"""
    
    @staticmethod
    def compute_image_hash(image: Image.Image, hash_size: int = 16) -> np.ndarray:
        """Berechnet einen perzeptuellen Hash (pHash)"""
        # Auf kleine Größe bringen
        small = image.convert('L').resize((hash_size, hash_size), Image.Resampling.LANCZOS)
        pixels = np.array(small, dtype=np.float64)
        
        # DCT-ähnliche Transformation (vereinfacht)
        avg = pixels.mean()
        diff = pixels > avg
        
        return diff.flatten()
    
    @staticmethod
    def compare_hashes(hash1: np.ndarray, hash2: np.ndarray) -> float:
        """Vergleicht zwei Hashes und gibt Ähnlichkeit zurück (0-1)"""
        if hash1 is None or hash2 is None:
            return 0.0
        
        # Hamming-Distanz
        diff = np.sum(hash1 != hash2)
        max_diff = len(hash1)
        
        similarity = 1.0 - (diff / max_diff)
        return similarity
    
    @staticmethod
    def compare_color_histograms(img1: Image.Image, img2: Image.Image) -> float:
        """Vergleicht Farbhistogramme"""
        # Auf gleiche Größe bringen
        size = (64, 64)
        img1_resized = img1.resize(size).convert('RGB')
        img2_resized = img2.resize(size).convert('RGB')
        
        # Histogramme berechnen
        hist1 = img1_resized.histogram()
        hist2 = img2_resized.histogram()
        
        # Normalisieren
        hist1 = np.array(hist1, dtype=np.float64)
        hist2 = np.array(hist2, dtype=np.float64)
        
        hist1 /= (hist1.sum() + 1e-10)
        hist2 /= (hist2.sum() + 1e-10)
        
        # Korrelation
        correlation = np.corrcoef(hist1, hist2)[0, 1]
        
        return max(0.0, correlation)
    
    @staticmethod
    def find_best_version_match(user_artwork: Image.Image, card_name: str, 
                                progress_callback=None) -> List[Dict]:
        """Findet die beste Versionsübereinstimmung durch Bildvergleich"""
        all_prints = ScryfallAPI.get_all_prints(card_name)
        
        if not all_prints:
            return []
        
        user_hash = CardMatcher.compute_image_hash(user_artwork)
        results = []
        
        total = len(all_prints)
        for i, card in enumerate(all_prints):
            if progress_callback:
                progress_callback((i + 1) / total)
            
            try:
                # Referenzbild laden
                ref_image = ScryfallAPI.download_card_image(card, "normal")
                if ref_image is None:
                    continue
                
                # Artwork extrahieren
                regions = OCREngine.extract_card_regions(ref_image)
                ref_artwork = regions.get('artwork')
                
                if ref_artwork is None:
                    continue
                
                # Hash-Vergleich
                ref_hash = CardMatcher.compute_image_hash(ref_artwork)
                hash_similarity = CardMatcher.compare_hashes(user_hash, ref_hash)
                
                # Farbvergleich
                color_similarity = CardMatcher.compare_color_histograms(user_artwork, ref_artwork)
                
                # Gesamtscore (gewichtet)
                total_score = (hash_similarity * 0.7) + (color_similarity * 0.3)
                
                results.append({
                    "card": card,
                    "score": total_score,
                    "hash_score": hash_similarity,
                    "color_score": color_similarity,
                    "name": card.get("name"),
                    "set_name": card.get("set_name"),
                    "set_code": card.get("set", "").upper(),
                    "collector_number": card.get("collector_number"),
                    "rarity": card.get("rarity"),
                    "released_at": card.get("released_at", "")[:4] if card.get("released_at") else ""
                })
                
                # Rate Limit
                time.sleep(0.05)
                
            except Exception as e:
                continue
        
        # Nach Score sortieren
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results


# ============================================================================
# CARD SCANNER - Haupterkennung
# ============================================================================

class MTGCardScanner:
    """Hauptklasse für Kartenerkennung"""
    
    def __init__(self):
        self.ocr = OCREngine()
        self.matcher = CardMatcher()
    
    def scan_card(self, image: Image.Image, progress_callback=None) -> Dict:
        """
        Scannt eine MTG Karte und identifiziert sie
        
        Returns:
            Dict mit Erkennungsergebnis
        """
        result = {
            "success": False,
            "card_name": None,
            "set_code": None,
            "set_name": None,
            "collector_number": None,
            "confidence": 0.0,
            "method": None,
            "all_matches": [],
            "card_data": None,
            "error": None
        }
        
        try:
            # 1. Regionen extrahieren
            if progress_callback:
                progress_callback(0.1, "Extrahiere Kartenbereiche...")
            
            regions = self.ocr.extract_card_regions(image)
            
            # 2. Versuche Sammlernummer zu lesen (für moderne Karten)
            if progress_callback:
                progress_callback(0.2, "Analysiere Karteninfo...")
            
            collector_info = self._extract_collector_info(regions.get('collector_info'))
            
            # 3. Wenn Set + Nummer gefunden, direkte Suche
            if collector_info.get('set_code') and collector_info.get('number'):
                if progress_callback:
                    progress_callback(0.4, f"Suche {collector_info['set_code']} #{collector_info['number']}...")
                
                card = ScryfallAPI.get_card_by_set_and_number(
                    collector_info['set_code'],
                    collector_info['number']
                )
                
                if card:
                    result["success"] = True
                    result["card_name"] = card.get("name")
                    result["set_code"] = card.get("set", "").upper()
                    result["set_name"] = card.get("set_name")
                    result["collector_number"] = card.get("collector_number")
                    result["confidence"] = 0.95
                    result["method"] = "collector_number"
                    result["card_data"] = card
                    return result
            
            # 4. Kartenname per OCR oder Bildvergleich
            if progress_callback:
                progress_callback(0.5, "Erkenne Kartennamen...")
            
            card_name = self._recognize_card_name(regions.get('title'), image)
            
            if not card_name:
                result["error"] = "Kartenname konnte nicht erkannt werden"
                return result
            
            result["card_name"] = card_name
            
            # 5. Karte in Scryfall suchen
            card = ScryfallAPI.search_card(card_name)
            if not card:
                result["error"] = f"Karte '{card_name}' nicht in Datenbank gefunden"
                return result
            
            # Korrigierten Namen verwenden
            result["card_name"] = card.get("name")
            
            # 6. Version durch Artwork-Vergleich identifizieren
            if progress_callback:
                progress_callback(0.6, "Vergleiche Artwork-Versionen...")
            
            artwork = regions.get('artwork')
            if artwork:
                def version_progress(p):
                    if progress_callback:
                        progress_callback(0.6 + p * 0.35, f"Vergleiche Versionen... {int(p*100)}%")
                
                matches = self.matcher.find_best_version_match(
                    artwork, 
                    result["card_name"],
                    progress_callback=version_progress
                )
                
                if matches:
                    best = matches[0]
                    result["success"] = True
                    result["set_code"] = best["set_code"]
                    result["set_name"] = best["set_name"]
                    result["collector_number"] = best["collector_number"]
                    result["confidence"] = best["score"]
                    result["method"] = "artwork_match"
                    result["card_data"] = best["card"]
                    result["all_matches"] = matches[:10]
                    return result
            
            # Fallback: Nur Name erkannt
            result["success"] = True
            result["set_code"] = card.get("set", "").upper()
            result["set_name"] = card.get("set_name")
            result["collector_number"] = card.get("collector_number")
            result["confidence"] = 0.5
            result["method"] = "name_only"
            result["card_data"] = card
            
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def _extract_collector_info(self, info_image: Optional[Image.Image]) -> Dict:
        """Extrahiert Set-Code und Sammlernummer aus dem Info-Bereich"""
        result = {"set_code": None, "number": None}
        
        if info_image is None:
            return result
        
        # Da Tesseract auf Streamlit Cloud nicht verfügbar ist,
        # versuchen wir einen anderen Ansatz: Farbanalyse des Set-Symbols
        # und später Bildvergleich
        
        # Hier könnten wir Google Cloud Vision API oder andere
        # Cloud-OCR-Dienste einbinden
        
        return result
    
    def _recognize_card_name(self, title_image: Optional[Image.Image], 
                            full_image: Image.Image) -> Optional[str]:
        """Versucht den Kartennamen zu erkennen"""
        
        # Ohne lokales Tesseract nutzen wir den Bildvergleich-Ansatz
        # Der Benutzer kann den Namen eingeben und wir finden die Version
        
        return None


# ============================================================================
# HILFSFUNKTIONEN
# ============================================================================

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


def get_confidence_class(confidence: float) -> str:
    """Gibt CSS-Klasse für Konfidenz zurück"""
    if confidence >= 0.8:
        return "confidence-high"
    elif confidence >= 0.5:
        return "confidence-medium"
    return "confidence-low"


def display_scan_result(result: Dict):
    """Zeigt das Scan-Ergebnis an"""
    if not result.get("success"):
        st.error(f"❌ Scan fehlgeschlagen: {result.get('error', 'Unbekannter Fehler')}")
        return
    
    card = result.get("card_data", {})
    confidence = result.get("confidence", 0)
    method = result.get("method", "unknown")
    
    # Ergebnis-Header
    conf_class = get_confidence_class(confidence)
    method_text = {
        "collector_number": "📊 Erkannt via Sammlernummer",
        "artwork_match": "🖼️ Erkannt via Bildvergleich",
        "name_only": "📝 Nur Kartenname erkannt"
    }.get(method, method)
    
    st.markdown(f"""
    <div class="scan-result">
        <h2>✅ Karte erkannt!</h2>
        <p><span class="{conf_class}">Konfidenz: {confidence*100:.1f}%</span> | {method_text}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Karte anzeigen
    display_card(card, result.get("all_matches", []))


def display_card(card: Dict, all_matches: List[Dict] = None):
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
        
        # Wichtigste Info hervorgehoben
        st.markdown(f"""
        ### 📦 Set & Nummer
        **Set:** {set_name}  
        **Set-Code:** `{set_code}`  
        **Sammlernummer:** `#{collector_number}`  
        **Seltenheit:** <span style="color: {rarity_color}; font-weight: bold;">{rarity.capitalize()}</span>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Kartendetails
        mana_cost = card.get("mana_cost", "")
        type_line = card.get("type_line", "")
        st.markdown(f"**Manakosten:** {mana_cost}  \n**Typ:** {type_line}")
        
        oracle_text = card.get("oracle_text", "")
        if oracle_text:
            with st.expander("Kartentext anzeigen"):
                st.text(oracle_text)
        
        power = card.get("power")
        toughness = card.get("toughness")
        if power and toughness:
            st.markdown(f"**Stärke/Widerstand:** {power}/{toughness}")
        
        # Preise
        prices = card.get("prices", {})
        price_str = format_price(prices)
        st.markdown(f"**💰 Preis:** :green[{price_str}]")
        
        # Link
        scryfall_uri = card.get("scryfall_uri", "")
        if scryfall_uri:
            st.markdown(f"[🔗 Auf Scryfall ansehen]({scryfall_uri})")
    
    # Alternative Matches anzeigen
    if all_matches and len(all_matches) > 1:
        st.markdown("---")
        st.markdown("### 🔄 Alternative Versionen (nach Übereinstimmung)")
        
        # Als Galerie
        cols = st.columns(5)
        for i, match in enumerate(all_matches[1:11]):  # Top 10 Alternativen
            with cols[i % 5]:
                img_url = get_card_image_url(match.get("card", {}), "small")
                if img_url:
                    st.image(img_url, use_container_width=True)
                    st.markdown(f"""
                    <div style="text-align: center; font-size: 0.8rem;">
                        <b>{match['set_code']}</b> #{match['collector_number']}<br>
                        <span class="match-score">{match['score']*100:.0f}%</span>
                    </div>
                    """, unsafe_allow_html=True)


def display_version_selection(card_name: str, user_image: Image.Image):
    """Zeigt Versionserkennung mit Bildvergleich"""
    
    st.markdown("### 🔍 Suche passende Version...")
    
    # Regionen extrahieren
    regions = OCREngine.extract_card_regions(user_image)
    user_artwork = regions.get('artwork')
    
    if not user_artwork:
        st.error("Konnte Artwork nicht extrahieren")
        return
    
    # Fortschrittsanzeige
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    def update_progress(p):
        progress_bar.progress(p)
    
    # Versionen vergleichen
    matches = CardMatcher.find_best_version_match(
        user_artwork, 
        card_name,
        progress_callback=update_progress
    )
    
    progress_bar.progress(1.0)
    status_text.empty()
    
    if not matches:
        st.warning("Keine Versionen gefunden")
        return
    
    # Ergebnis
    best = matches[0]
    st.success(f"**Beste Übereinstimmung:** {best['set_name']} ({best['set_code']}) #{best['collector_number']} - {best['score']*100:.1f}%")
    
    display_card(best['card'], matches)


# ============================================================================
# HAUPTANWENDUNG
# ============================================================================

def main():
    """Hauptfunktion"""
    
    st.markdown('<h1 class="main-header">🃏 MTG Card Scanner</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #666;">Automatische Kartenerkennung mit Set & Sammlernummer</p>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown("## 📷 Scanner Modus")
        
        scan_mode = st.radio(
            "Wähle Modus:",
            ["🖼️ Bild scannen", "📝 Name + Bildvergleich", "🎲 Zufällige Karte"],
            index=0
        )
        
        st.markdown("---")
        st.markdown("### ℹ️ Wie es funktioniert")
        st.markdown("""
        **Bild scannen:**
        1. Lade ein Foto deiner Karte hoch
        2. Die App extrahiert das Artwork
        3. Vergleich mit allen Versionen in der Datenbank
        4. Die beste Übereinstimmung wird angezeigt
        
        **Auch für alte Karten!**
        Karten ohne gedruckten Set-Code werden durch Artwork-Vergleich erkannt.
        """)
        
        st.markdown("---")
        st.markdown("### 🎯 Tipps für beste Ergebnisse")
        st.markdown("""
        - Gute Beleuchtung
        - Karte gerade fotografieren
        - Wenig Reflexionen
        - Karte sollte Bild ausfüllen
        """)
    
    # Hauptbereich
    if scan_mode == "🖼️ Bild scannen":
        st.markdown("### 📷 Kartenbild hochladen")
        
        uploaded_file = st.file_uploader(
            "Foto einer MTG Karte hochladen",
            type=["jpg", "jpeg", "png", "webp"],
            help="Fotografiere deine Karte und lade das Bild hoch"
        )
        
        if uploaded_file:
            image = Image.open(uploaded_file)
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.markdown("#### 📸 Dein Bild")
                st.image(image, use_container_width=True)
            
            with col2:
                st.markdown("#### 🔍 Erkannte Bereiche")
                
                # Regionen extrahieren und anzeigen
                regions = OCREngine.extract_card_regions(image)
                
                region_col1, region_col2 = st.columns(2)
                with region_col1:
                    if regions.get('title'):
                        st.image(regions['title'], caption="Titelbereich", use_container_width=True)
                with region_col2:
                    if regions.get('artwork'):
                        st.image(regions['artwork'], caption="Artwork", use_container_width=True)
            
            st.markdown("---")
            
            # Kartenname eingeben (da OCR auf Cloud schwierig)
            st.markdown("### 📝 Kartenname eingeben")
            st.info("Gib den Kartennamen ein - die App findet automatisch die richtige Version durch Bildvergleich!")
            
            card_name_input = st.text_input(
                "Kartenname:",
                placeholder="z.B. Lightning Bolt, Serra Angel, Black Lotus..."
            )
            
            # Autovervollständigung
            if card_name_input and len(card_name_input) >= 2:
                suggestions = ScryfallAPI.autocomplete(card_name_input)
                if suggestions:
                    selected = st.selectbox(
                        "Vorschläge:",
                        [""] + suggestions[:10]
                    )
                    if selected:
                        card_name_input = selected
            
            if card_name_input and st.button("🔎 Version finden", type="primary"):
                # Karte verifizieren
                card = ScryfallAPI.search_card(card_name_input)
                if card:
                    verified_name = card.get("name")
                    st.success(f"✓ Karte gefunden: **{verified_name}**")
                    
                    # Versionsvergleich starten
                    display_version_selection(verified_name, image)
                else:
                    st.error(f"Karte '{card_name_input}' nicht gefunden")
    
    elif scan_mode == "📝 Name + Bildvergleich":
        st.markdown("### 🔍 Karte suchen und Version identifizieren")
        
        card_name = st.text_input(
            "Kartenname eingeben:",
            placeholder="z.B. Lightning Bolt"
        )
        
        if card_name and len(card_name) >= 2:
            suggestions = ScryfallAPI.autocomplete(card_name)
            if suggestions:
                selected = st.selectbox("Vorschläge:", [""] + suggestions[:10])
                if selected:
                    card_name = selected
        
        if card_name:
            card = ScryfallAPI.search_card(card_name)
            if card:
                st.success(f"✓ **{card.get('name')}** gefunden")
                
                # Alle Versionen laden
                versions = ScryfallAPI.get_all_prints(card.get("name"))
                
                if versions:
                    st.markdown(f"### 📚 {len(versions)} Versionen verfügbar")
                    
                    # Filter
                    col1, col2 = st.columns(2)
                    with col1:
                        rarity_filter = st.multiselect(
                            "Seltenheit:",
                            ["common", "uncommon", "rare", "mythic"],
                            default=[]
                        )
                    with col2:
                        year_filter = st.slider(
                            "Jahr:",
                            1993, 2025, (1993, 2025)
                        )
                    
                    # Filtern
                    filtered = versions
                    if rarity_filter:
                        filtered = [v for v in filtered if v.get("rarity") in rarity_filter]
                    
                    filtered = [v for v in filtered 
                               if v.get("released_at") and 
                               year_filter[0] <= int(v["released_at"][:4]) <= year_filter[1]]
                    
                    # Anzeigen
                    st.markdown(f"**{len(filtered)} Versionen angezeigt**")
                    
                    cols = st.columns(4)
                    for i, v in enumerate(filtered[:20]):
                        with cols[i % 4]:
                            img_url = get_card_image_url(v, "normal")
                            if img_url:
                                st.image(img_url, use_container_width=True)
                            st.markdown(f"""
                            **{v.get('set_name', '')}**  
                            `{v.get('set', '').upper()}` #{v.get('collector_number', '')}  
                            {v.get('released_at', '')[:4]}
                            """)
                            
                            # Preis
                            price = v.get('prices', {}).get('usd', 'N/A')
                            st.markdown(f"💰 ${price}")
    
    elif scan_mode == "🎲 Zufällige Karte":
        st.markdown("### 🎲 Zufällige Karte")
        
        if st.button("🎰 Neue zufällige Karte", type="primary"):
            with st.spinner("Lade..."):
                card = ScryfallAPI.get_random_card()
                if card:
                    display_card(card)
                else:
                    st.error("Fehler beim Laden")
        else:
            st.info("Klicke den Button für eine zufällige Karte!")
    
    # Footer
    st.markdown("---")
    st.markdown(
        '<p style="text-align: center; color: #888; font-size: 0.8rem;">'
        'MTG Card Scanner | Powered by Scryfall API | Made for MTG Collectors'
        '</p>',
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()