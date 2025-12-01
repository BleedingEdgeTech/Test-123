"""
OCR Engine für MTG Kartentexterkennung
"""

import cv2
import numpy as np
import re
from typing import Optional, Tuple
try:
    import pytesseract
except ImportError:
    pytesseract = None


class OCREngine:
    """OCR-basierte Texterkennung für MTG Karten"""
    
    def __init__(self, tesseract_path: Optional[str] = None):
        """
        Initialisiert die OCR Engine
        
        Args:
            tesseract_path: Optionaler Pfad zur Tesseract-Executable
        """
        if pytesseract is None:
            raise ImportError(
                "pytesseract ist nicht installiert. "
                "Installiere es mit: pip install pytesseract"
            )
        
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        
        # Tesseract-Konfiguration für MTG Kartennamen
        self.config_title = '--oem 3 --psm 7 -c tessedit_char_whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ,\'\\"-"'
        self.config_number = '--oem 3 --psm 7 -c tessedit_char_whitelist="0123456789/"'
        self.config_general = '--oem 3 --psm 6'
    
    def _preprocess_for_ocr(self, image: np.ndarray, mode: str = "title") -> np.ndarray:
        """
        Bereitet Bild für OCR vor
        
        Args:
            image: Eingabebild
            mode: "title", "number", oder "general"
        
        Returns:
            Vorverarbeitetes Bild
        """
        # In Graustufen konvertieren
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
        
        # Vergrößern falls zu klein
        height = gray.shape[0]
        if height < 50:
            scale = 50 / height
            gray = cv2.resize(gray, None, fx=scale, fy=scale, 
                            interpolation=cv2.INTER_CUBIC)
        
        # Rauschen reduzieren
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        
        # Kontrast erhöhen
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)
        
        if mode == "title":
            # Für Titel: Adaptiver Threshold
            binary = cv2.adaptiveThreshold(
                enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 15, 5
            )
        elif mode == "number":
            # Für Nummern: Otsu's Threshold
            _, binary = cv2.threshold(
                enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
        else:
            # Allgemein
            binary = cv2.adaptiveThreshold(
                enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 11, 2
            )
        
        # Rand hinzufügen
        binary = cv2.copyMakeBorder(
            binary, 10, 10, 10, 10, 
            cv2.BORDER_CONSTANT, value=255
        )
        
        return binary
    
    def read_card_title(self, title_image: np.ndarray) -> Tuple[str, float]:
        """
        Liest den Kartennamen aus dem Titelbereich
        
        Args:
            title_image: Bild des Titelbereichs
        
        Returns:
            Tuple aus (erkannter Text, Konfidenz)
        """
        processed = self._preprocess_for_ocr(title_image, mode="title")
        
        try:
            # OCR durchführen
            data = pytesseract.image_to_data(
                processed, config=self.config_title, 
                output_type=pytesseract.Output.DICT
            )
            
            # Text und Konfidenz extrahieren
            words = []
            confidences = []
            
            for i, conf in enumerate(data['conf']):
                if int(conf) > 0:
                    word = data['text'][i].strip()
                    if word:
                        words.append(word)
                        confidences.append(int(conf))
            
            if not words:
                return "", 0.0
            
            text = " ".join(words)
            avg_confidence = sum(confidences) / len(confidences) / 100.0
            
            # Text bereinigen
            text = self._clean_card_name(text)
            
            return text, avg_confidence
            
        except Exception as e:
            print(f"OCR Fehler: {e}")
            return "", 0.0
    
    def read_collector_number(self, number_image: np.ndarray) -> Tuple[str, float]:
        """
        Liest die Sammlernummer
        
        Args:
            number_image: Bild des Nummernbereichs
        
        Returns:
            Tuple aus (Sammlernummer, Konfidenz)
        """
        processed = self._preprocess_for_ocr(number_image, mode="number")
        
        try:
            data = pytesseract.image_to_data(
                processed, config=self.config_number,
                output_type=pytesseract.Output.DICT
            )
            
            text = ""
            confidence = 0.0
            
            for i, conf in enumerate(data['conf']):
                if int(conf) > 0:
                    word = data['text'][i].strip()
                    if word:
                        text += word
                        confidence = max(confidence, int(conf) / 100.0)
            
            # Sammlernummer extrahieren (Format: XXX/YYY oder nur XXX)
            match = re.search(r'(\d+)(?:/(\d+))?', text)
            if match:
                collector_number = match.group(1)
                if match.group(2):
                    collector_number += "/" + match.group(2)
                return collector_number, confidence
            
            return text, confidence
            
        except Exception as e:
            print(f"OCR Fehler bei Sammlernummer: {e}")
            return "", 0.0
    
    def read_set_info(self, info_image: np.ndarray) -> Tuple[str, float]:
        """
        Liest Set-Informationen (z.B. Set-Code)
        
        Args:
            info_image: Bild des Info-Bereichs
        
        Returns:
            Tuple aus (erkannter Text, Konfidenz)
        """
        processed = self._preprocess_for_ocr(info_image, mode="general")
        
        try:
            text = pytesseract.image_to_string(
                processed, config=self.config_general
            ).strip()
            
            # Set-Code extrahieren (3-4 Großbuchstaben)
            match = re.search(r'[A-Z]{3,4}', text)
            if match:
                return match.group(), 0.8
            
            return text, 0.5
            
        except Exception as e:
            print(f"OCR Fehler bei Set-Info: {e}")
            return "", 0.0
    
    def _clean_card_name(self, text: str) -> str:
        """
        Bereinigt erkannten Kartennamen
        
        Args:
            text: Roher OCR-Text
        
        Returns:
            Bereinigter Kartenname
        """
        # Entferne unerwünschte Zeichen
        text = re.sub(r'[^a-zA-Z0-9\s,\'\"-]', '', text)
        
        # Mehrfache Leerzeichen entfernen
        text = re.sub(r'\s+', ' ', text)
        
        # Trimmen
        text = text.strip()
        
        # Häufige OCR-Fehler korrigieren
        corrections = {
            '0': 'O',  # Null zu O
            '1': 'l',  # Eins zu l (in Namen)
            '|': 'l',  # Pipe zu l
        }
        
        # Wörter mit korrekter Großschreibung
        words = text.split()
        corrected_words = []
        
        for word in words:
            # Erstes Zeichen groß, Rest klein (Standard für Namen)
            if word:
                corrected_word = word[0].upper() + word[1:].lower() if len(word) > 1 else word.upper()
                corrected_words.append(corrected_word)
        
        return " ".join(corrected_words)
    
    def extract_all_text(self, card_image: np.ndarray) -> dict:
        """
        Extrahiert alle Textinformationen von einer Karte
        
        Args:
            card_image: Vollständiges Kartenbild
        
        Returns:
            Dictionary mit allen erkannten Texten
        """
        from .image_processor import ImageProcessor
        processor = ImageProcessor()
        
        results = {
            "title": {"text": "", "confidence": 0.0},
            "collector_number": {"text": "", "confidence": 0.0}
        }
        
        # Titel extrahieren
        title_region = processor.extract_title_region(card_image)
        title, title_conf = self.read_card_title(title_region)
        results["title"]["text"] = title
        results["title"]["confidence"] = title_conf
        
        # Sammlernummer extrahieren
        number_region = processor.extract_collector_number_region(card_image)
        number, number_conf = self.read_collector_number(number_region)
        results["collector_number"]["text"] = number
        results["collector_number"]["confidence"] = number_conf
        
        return results
    
    def is_tesseract_available(self) -> bool:
        """
        Prüft ob Tesseract verfügbar ist
        
        Returns:
            True wenn Tesseract funktioniert
        """
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False
