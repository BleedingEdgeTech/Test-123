"""
Haupterkennungsmodul für MTG Karten
"""

import cv2
import numpy as np
from typing import Optional, Dict, List, Union
from pathlib import Path

from .image_processor import ImageProcessor
from .ocr_engine import OCREngine
from .scryfall_api import ScryfallAPI
from .card_matcher import CardMatcher


class MTGCardRecognizer:
    """
    Hauptklasse für die MTG Kartenerkennung
    
    Kombiniert OCR, Bildverarbeitung und API-Abfragen für
    präzise Kartenerkennung und Versionsidentifikation.
    """
    
    def __init__(self, tesseract_path: Optional[str] = None):
        """
        Initialisiert den Erkenner
        
        Args:
            tesseract_path: Optionaler Pfad zur Tesseract-Executable
        """
        self.processor = ImageProcessor()
        self.api = ScryfallAPI()
        self.matcher = CardMatcher(self.api)
        
        try:
            self.ocr = OCREngine(tesseract_path)
            self.ocr_available = self.ocr.is_tesseract_available()
        except ImportError:
            self.ocr = None
            self.ocr_available = False
            print("Warnung: OCR nicht verfügbar. Nur API-basierte Suche möglich.")
    
    def recognize_card(self, image_source: Union[str, np.ndarray, bytes],
                       use_ocr: bool = True,
                       match_version: bool = True) -> Dict:
        """
        Erkennt eine MTG Karte und identifiziert die Version
        
        Args:
            image_source: Bildpfad, numpy Array oder Bytes
            use_ocr: OCR für Namenerkennung verwenden
            match_version: Versuchen die exakte Version zu finden
        
        Returns:
            Dictionary mit Erkennungsergebnis
        """
        result = {
            "success": False,
            "name": None,
            "set_name": None,
            "set_code": None,
            "collector_number": None,
            "confidence": 0.0,
            "all_matches": [],
            "image_url": None,
            "scryfall_uri": None,
            "error": None
        }
        
        # 1. Bild laden
        image = self._load_image(image_source)
        if image is None:
            result["error"] = "Bild konnte nicht geladen werden"
            return result
        
        # 2. Kartenregion extrahieren
        card_image, extraction_confidence = self.processor.extract_card_region(image)
        if card_image is None:
            result["error"] = "Keine Karte im Bild erkannt"
            return result
        
        # 3. Kartenname ermitteln
        card_name = None
        name_confidence = 0.0
        collector_number = None
        
        if use_ocr and self.ocr_available:
            # OCR verwenden
            ocr_result = self.ocr.extract_all_text(card_image)
            
            card_name = ocr_result["title"]["text"]
            name_confidence = ocr_result["title"]["confidence"]
            collector_number = ocr_result["collector_number"]["text"]
            
            # Name mit API verifizieren/korrigieren
            if card_name:
                card_name = self._verify_card_name(card_name)
        
        if not card_name:
            result["error"] = "Kartenname konnte nicht erkannt werden. Bitte manuell eingeben."
            return result
        
        result["name"] = card_name
        
        # 4. Karte in Scryfall suchen
        card_data = self.api.get_card_by_name(card_name)
        if not card_data:
            result["error"] = f"Karte '{card_name}' nicht in Datenbank gefunden"
            return result
        
        # Korrigierten Namen verwenden
        result["name"] = card_data.get("name", card_name)
        
        # 5. Exakte Version identifizieren
        if match_version:
            # Erst mit Sammlernummer versuchen
            if collector_number:
                version = self.matcher.identify_version_from_collector_number(
                    result["name"], collector_number
                )
                if version:
                    self._fill_result(result, version, 0.95)
                    return result
            
            # Bildvergleich für Versionserkennung
            matches = self.matcher.find_best_match(result["name"], card_image)
            
            if matches:
                best_match = matches[0]
                self._fill_result(result, best_match["card"], best_match["score"])
                result["all_matches"] = [
                    {
                        "set_name": m["set_name"],
                        "set_code": m["set_code"],
                        "collector_number": m["collector_number"],
                        "score": m["score"]
                    }
                    for m in matches
                ]
        else:
            # Nur erste gefundene Version
            self._fill_result(result, card_data, 0.7)
        
        # Gesamtkonfidenz berechnen
        result["confidence"] = (
            extraction_confidence * 0.3 +
            name_confidence * 0.3 +
            result["confidence"] * 0.4
        )
        
        result["success"] = True
        return result
    
    def recognize_from_name(self, card_name: str, 
                           image_source: Optional[Union[str, np.ndarray, bytes]] = None) -> Dict:
        """
        Erkennt Kartenversion basierend auf bekanntem Namen
        
        Args:
            card_name: Bekannter Kartenname
            image_source: Optionales Bild für Versionserkennung
        
        Returns:
            Erkennungsergebnis
        """
        result = {
            "success": False,
            "name": card_name,
            "set_name": None,
            "set_code": None,
            "collector_number": None,
            "confidence": 0.0,
            "all_matches": [],
            "image_url": None,
            "scryfall_uri": None,
            "error": None
        }
        
        # Karte in API suchen
        card_data = self.api.get_card_by_name(card_name)
        if not card_data:
            result["error"] = f"Karte '{card_name}' nicht gefunden"
            return result
        
        result["name"] = card_data.get("name", card_name)
        
        if image_source:
            # Bild für Versionserkennung verwenden
            image = self._load_image(image_source)
            if image is not None:
                card_image, _ = self.processor.extract_card_region(image)
                if card_image is not None:
                    matches = self.matcher.find_best_match(result["name"], card_image)
                    if matches:
                        best = matches[0]
                        self._fill_result(result, best["card"], best["score"])
                        result["success"] = True
                        return result
        
        # Alle Versionen auflisten
        all_prints = self.api.get_all_prints(result["name"])
        if all_prints:
            # Erste (neueste) Version verwenden
            self._fill_result(result, all_prints[0], 0.8)
            result["all_matches"] = [
                {
                    "set_name": p.get("set_name"),
                    "set_code": p.get("set"),
                    "collector_number": p.get("collector_number"),
                    "score": 0.5
                }
                for p in all_prints[:10]
            ]
        
        result["success"] = True
        return result
    
    def get_all_versions(self, card_name: str) -> List[Dict]:
        """
        Holt alle verfügbaren Versionen einer Karte
        
        Args:
            card_name: Kartenname
        
        Returns:
            Liste aller Versionen
        """
        all_prints = self.api.get_all_prints(card_name)
        
        versions = []
        for card in all_prints:
            versions.append({
                "name": card.get("name"),
                "set_name": card.get("set_name"),
                "set_code": card.get("set"),
                "collector_number": card.get("collector_number"),
                "rarity": card.get("rarity"),
                "released_at": card.get("released_at"),
                "image_url": self.api.get_card_image_url(card),
                "scryfall_uri": card.get("scryfall_uri"),
                "prices": card.get("prices", {})
            })
        
        return versions
    
    def _load_image(self, source: Union[str, np.ndarray, bytes]) -> Optional[np.ndarray]:
        """Lädt Bild aus verschiedenen Quellen"""
        if isinstance(source, np.ndarray):
            return source
        elif isinstance(source, bytes):
            return self.processor.load_image_from_bytes(source)
        elif isinstance(source, str):
            return self.processor.load_image(source)
        else:
            return None
    
    def _verify_card_name(self, ocr_name: str) -> str:
        """
        Verifiziert und korrigiert den OCR-erkannten Namen
        
        Args:
            ocr_name: OCR-erkannter Name
        
        Returns:
            Verifizierter/korrigierter Name
        """
        # Autovervollständigung verwenden
        suggestions = self.api.autocomplete(ocr_name)
        
        if suggestions:
            # Beste Übereinstimmung finden
            ocr_lower = ocr_name.lower()
            
            for suggestion in suggestions:
                if suggestion.lower() == ocr_lower:
                    return suggestion
            
            # Wenn exakte Übereinstimmung nicht gefunden, erste Suggestion verwenden
            # wenn sie ähnlich genug ist
            if self._string_similarity(ocr_name, suggestions[0]) > 0.7:
                return suggestions[0]
        
        return ocr_name
    
    def _string_similarity(self, s1: str, s2: str) -> float:
        """Berechnet Ähnlichkeit zwischen zwei Strings"""
        s1, s2 = s1.lower(), s2.lower()
        
        if s1 == s2:
            return 1.0
        
        # Levenshtein-basierte Ähnlichkeit (vereinfacht)
        len1, len2 = len(s1), len(s2)
        max_len = max(len1, len2)
        
        if max_len == 0:
            return 1.0
        
        # Gemeinsame Zeichen zählen
        common = sum(1 for c in s1 if c in s2)
        
        return common / max_len
    
    def _fill_result(self, result: Dict, card_data: Dict, confidence: float):
        """Füllt Ergebnis-Dictionary mit Kartendaten"""
        result["name"] = card_data.get("name")
        result["set_name"] = card_data.get("set_name")
        result["set_code"] = card_data.get("set")
        result["collector_number"] = card_data.get("collector_number")
        result["rarity"] = card_data.get("rarity")
        result["confidence"] = confidence
        result["image_url"] = self.api.get_card_image_url(card_data)
        result["scryfall_uri"] = card_data.get("scryfall_uri")
        result["prices"] = card_data.get("prices", {})
    
    def recognize_from_webcam(self, camera_id: int = 0) -> Dict:
        """
        Erkennt Karte von Webcam (interaktiv)
        
        Args:
            camera_id: Kamera-ID (Standard: 0)
        
        Returns:
            Erkennungsergebnis
        """
        cap = cv2.VideoCapture(camera_id)
        
        if not cap.isOpened():
            return {"success": False, "error": "Kamera konnte nicht geöffnet werden"}
        
        print("Webcam aktiv. Drücke 'SPACE' zum Erfassen, 'Q' zum Beenden.")
        
        captured_image = None
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Vorschau anzeigen
            display = frame.copy()
            cv2.putText(display, "SPACE: Erfassen | Q: Beenden", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            cv2.imshow("MTG Card Scanner", display)
            
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord(' '):
                captured_image = frame.copy()
                break
            elif key == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()
        
        if captured_image is not None:
            return self.recognize_card(captured_image)
        
        return {"success": False, "error": "Keine Aufnahme gemacht"}
    
    def batch_recognize(self, image_sources: List[Union[str, np.ndarray, bytes]],
                       use_ocr: bool = True) -> List[Dict]:
        """
        Erkennt mehrere Karten
        
        Args:
            image_sources: Liste von Bildquellen
            use_ocr: OCR verwenden
        
        Returns:
            Liste von Erkennungsergebnissen
        """
        results = []
        
        for i, source in enumerate(image_sources):
            print(f"Verarbeite Karte {i+1}/{len(image_sources)}...")
            result = self.recognize_card(source, use_ocr=use_ocr)
            results.append(result)
        
        return results
