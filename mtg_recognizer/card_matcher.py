"""
Kartenabgleich und Versionserkennung für MTG Karten
"""

import cv2
import numpy as np
from typing import Optional, List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import imagehash
from PIL import Image
import io

from .scryfall_api import ScryfallAPI
from .image_processor import ImageProcessor


class CardMatcher:
    """Matching-Engine für MTG Kartenerkennung und Versionsidentifikation"""
    
    def __init__(self, api: Optional[ScryfallAPI] = None):
        """
        Initialisiert den CardMatcher
        
        Args:
            api: Optionale ScryfallAPI Instanz
        """
        self.api = api or ScryfallAPI()
        self.processor = ImageProcessor()
        self._image_cache = {}
    
    def find_best_match(self, card_name: str, card_image: np.ndarray, 
                       top_k: int = 5) -> List[Dict]:
        """
        Findet die beste Übereinstimmung für eine Karte
        
        Args:
            card_name: Erkannter Kartenname
            card_image: Bild der zu identifizierenden Karte
            top_k: Anzahl der Top-Ergebnisse
        
        Returns:
            Liste der besten Übereinstimmungen mit Scores
        """
        # Alle Versionen der Karte abrufen
        all_prints = self.api.get_all_prints(card_name)
        
        if not all_prints:
            return []
        
        # Artwork-Region extrahieren
        card_art = self.processor.extract_art_region(card_image)
        card_art_hash = self._compute_phash(card_art)
        
        # Scores für alle Versionen berechnen
        results = []
        
        for card in all_prints:
            score = self._calculate_match_score(card, card_image, card_art_hash)
            results.append({
                "card": card,
                "score": score,
                "name": card.get("name", "Unknown"),
                "set_name": card.get("set_name", "Unknown"),
                "set_code": card.get("set", "???"),
                "collector_number": card.get("collector_number", ""),
                "rarity": card.get("rarity", "common"),
                "image_url": self.api.get_card_image_url(card)
            })
        
        # Nach Score sortieren
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results[:top_k]
    
    def _calculate_match_score(self, card_data: Dict, user_image: np.ndarray,
                              user_art_hash) -> float:
        """
        Berechnet den Übereinstimmungsscore zwischen Karte und Bild
        
        Args:
            card_data: Kartendaten von Scryfall
            user_image: Benutzerbild der Karte
            user_art_hash: Hash des Artwork-Bereichs
        
        Returns:
            Score (0.0 - 1.0)
        """
        score_components = []
        
        # 1. Artwork-Hash-Vergleich (wichtigster Faktor)
        art_score = self._compare_artwork(card_data, user_art_hash)
        if art_score is not None:
            score_components.append(("art_hash", art_score, 0.6))
        
        # 2. Farbschema-Vergleich
        color_score = self._compare_colors(card_data, user_image)
        if color_score is not None:
            score_components.append(("color", color_score, 0.2))
        
        # 3. Rahmen-Erkennung (alter/neuer Rahmen, Vollbild, etc.)
        frame_score = self._estimate_frame_match(card_data, user_image)
        score_components.append(("frame", frame_score, 0.2))
        
        # Gewichteter Score
        if not score_components:
            return 0.0
        
        total_weight = sum(w for _, _, w in score_components)
        weighted_score = sum(s * w for _, s, w in score_components) / total_weight
        
        return weighted_score
    
    def _compare_artwork(self, card_data: Dict, user_art_hash) -> Optional[float]:
        """
        Vergleicht Artwork mittels Perceptual Hash
        
        Args:
            card_data: Kartendaten
            user_art_hash: Hash des User-Artworks
        
        Returns:
            Ähnlichkeitsscore oder None
        """
        if user_art_hash is None:
            return None
        
        # Bild von Scryfall laden
        image_url = self.api.get_card_image_url(card_data, size="normal")
        if not image_url:
            return None
        
        # Cache prüfen
        cache_key = image_url
        if cache_key in self._image_cache:
            ref_hash = self._image_cache[cache_key]
        else:
            # Bild herunterladen
            image_bytes = self.api.download_card_image(card_data, size="normal")
            if not image_bytes:
                return None
            
            ref_image = self.processor.load_image_from_bytes(image_bytes)
            if ref_image is None:
                return None
            
            # Artwork extrahieren
            ref_art = self.processor.extract_art_region(ref_image)
            ref_hash = self._compute_phash(ref_art)
            
            # Cachen
            self._image_cache[cache_key] = ref_hash
        
        if ref_hash is None:
            return None
        
        # Hash-Differenz berechnen
        diff = user_art_hash - ref_hash
        
        # Differenz zu Score konvertieren (0 Diff = 1.0 Score)
        max_diff = 64  # Maximale Bit-Differenz
        score = 1.0 - (diff / max_diff)
        
        return max(0.0, score)
    
    def _compute_phash(self, image: np.ndarray):
        """
        Berechnet Perceptual Hash für Bildvergleich
        
        Args:
            image: Eingabebild (OpenCV Format)
        
        Returns:
            ImageHash oder None
        """
        try:
            # OpenCV zu PIL konvertieren
            if len(image.shape) == 3:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image
            
            pil_image = Image.fromarray(image_rgb)
            
            # Perceptual Hash berechnen
            return imagehash.phash(pil_image)
        except Exception as e:
            print(f"Hash-Berechnung fehlgeschlagen: {e}")
            return None
    
    def _compare_colors(self, card_data: Dict, user_image: np.ndarray) -> Optional[float]:
        """
        Vergleicht die Farbverteilung
        
        Args:
            card_data: Kartendaten
            user_image: Benutzerbild
        
        Returns:
            Ähnlichkeitsscore oder None
        """
        # Farbidentität der Karte
        colors = card_data.get("colors", [])
        color_identity = card_data.get("color_identity", colors)
        
        # Dominante Farbe im Rahmenbereich erkennen
        height, width = user_image.shape[:2]
        
        # Rahmenbereich (links und rechts)
        left_border = user_image[:, :int(width*0.05)]
        right_border = user_image[:, int(width*0.95):]
        border = np.vstack([left_border, right_border])
        
        # Durchschnittsfarbe berechnen
        avg_color = np.mean(border, axis=(0, 1))
        
        # MTG Farben zu RGB (vereinfacht)
        mtg_colors = {
            "W": np.array([240, 230, 210]),  # Weiß
            "U": np.array([50, 100, 180]),   # Blau
            "B": np.array([50, 50, 60]),     # Schwarz
            "R": np.array([180, 70, 50]),    # Rot
            "G": np.array([50, 140, 80]),    # Grün
        }
        
        if not color_identity:
            # Farblos/Artefakt
            expected_color = np.array([150, 150, 150])
        elif len(color_identity) == 1:
            expected_color = mtg_colors.get(color_identity[0], np.array([150, 150, 150]))
        else:
            # Mehrfarbig - Gold
            expected_color = np.array([200, 170, 80])
        
        # Farbdifferenz berechnen (BGR zu RGB)
        user_rgb = avg_color[::-1] if len(avg_color) == 3 else avg_color
        diff = np.linalg.norm(user_rgb - expected_color)
        
        # Normalisieren (max Differenz ~441 für volle RGB-Differenz)
        score = 1.0 - min(diff / 200, 1.0)
        
        return score
    
    def _estimate_frame_match(self, card_data: Dict, user_image: np.ndarray) -> float:
        """
        Schätzt die Rahmenübereinstimmung
        
        Args:
            card_data: Kartendaten
            user_image: Benutzerbild
        
        Returns:
            Übereinstimmungsscore
        """
        frame = card_data.get("frame", "2015")
        is_fullart = card_data.get("full_art", False)
        border_color = card_data.get("border_color", "black")
        
        # Einfache Heuristik basierend auf Bildanalyse
        height, width = user_image.shape[:2]
        
        # Rand analysieren
        top_border = user_image[:int(height*0.02), :]
        avg_border = np.mean(top_border)
        
        # Schwarzer Rand?
        has_black_border = avg_border < 50
        
        # Basis-Score
        score = 0.5
        
        # Rand-Farbe prüfen
        if border_color == "black" and has_black_border:
            score += 0.25
        elif border_color == "white" and avg_border > 200:
            score += 0.25
        elif border_color == "borderless":
            score += 0.1
        
        # Rahmen-Stil (vereinfacht)
        if frame in ["2015", "2003"]:
            score += 0.25
        
        return min(score, 1.0)
    
    def identify_version_from_collector_number(self, card_name: str, 
                                               collector_number: str) -> Optional[Dict]:
        """
        Identifiziert eine Kartenversion anhand der Sammlernummer
        
        Args:
            card_name: Kartenname
            collector_number: Erkannte Sammlernummer
        
        Returns:
            Kartendaten oder None
        """
        all_prints = self.api.get_all_prints(card_name)
        
        for card in all_prints:
            if card.get("collector_number") == collector_number:
                return card
        
        # Fuzzy Match für Sammlernummer
        collector_num_clean = collector_number.split("/")[0].lstrip("0")
        
        for card in all_prints:
            card_num = card.get("collector_number", "").split("/")[0].lstrip("0")
            if card_num == collector_num_clean:
                return card
        
        return None
    
    def match_by_set_symbol(self, card_name: str, 
                           set_symbol_image: np.ndarray) -> List[Dict]:
        """
        Versucht die Version anhand des Set-Symbols zu identifizieren
        
        Args:
            card_name: Kartenname
            set_symbol_image: Bild des Set-Symbols
        
        Returns:
            Mögliche Versionen
        """
        # Set-Symbol-Erkennung ist komplex - vereinfachte Implementation
        all_prints = self.api.get_all_prints(card_name)
        
        # Analysiere Symbol-Farbe für Seltenheit
        hsv = cv2.cvtColor(set_symbol_image, cv2.COLOR_BGR2HSV)
        avg_hue = np.mean(hsv[:, :, 0])
        avg_saturation = np.mean(hsv[:, :, 1])
        avg_value = np.mean(hsv[:, :, 2])
        
        # Seltenheit basierend auf Farbe schätzen
        estimated_rarity = "common"
        
        if avg_saturation > 150 and avg_value > 150:
            if 15 < avg_hue < 35:  # Gold/Orange
                estimated_rarity = "rare"
            elif 100 < avg_hue < 130:  # Orange-Rot
                estimated_rarity = "mythic"
            elif avg_saturation < 80:  # Silber
                estimated_rarity = "uncommon"
        
        # Filter nach Seltenheit
        filtered = [c for c in all_prints if c.get("rarity") == estimated_rarity]
        
        return filtered if filtered else all_prints
    
    def batch_identify(self, cards: List[Tuple[str, np.ndarray]], 
                       workers: int = 4) -> List[Dict]:
        """
        Identifiziert mehrere Karten parallel
        
        Args:
            cards: Liste von (name, image) Tupeln
            workers: Anzahl paralleler Worker
        
        Returns:
            Liste von Ergebnissen
        """
        results = []
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self.find_best_match, name, image, 1): (name, image)
                for name, image in cards
            }
            
            for future in as_completed(futures):
                name, _ = futures[future]
                try:
                    matches = future.result()
                    if matches:
                        results.append(matches[0])
                    else:
                        results.append({
                            "name": name,
                            "score": 0.0,
                            "error": "Keine Übereinstimmung gefunden"
                        })
                except Exception as e:
                    results.append({
                        "name": name,
                        "score": 0.0,
                        "error": str(e)
                    })
        
        return results
    
    def clear_cache(self):
        """Leert den Bildcache"""
        self._image_cache.clear()
