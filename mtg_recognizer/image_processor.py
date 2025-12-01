"""
Bildverarbeitungsmodul für MTG Kartenerkennung
"""

import cv2
import numpy as np
from PIL import Image
from typing import Tuple, Optional, List
import io


class ImageProcessor:
    """Verarbeitet und bereitet Kartenbilder für die Erkennung vor"""
    
    # Standard MTG Karten-Seitenverhältnis (ca. 63mm x 88mm)
    CARD_ASPECT_RATIO = 63 / 88  # ~0.716
    CARD_ASPECT_TOLERANCE = 0.15
    
    def __init__(self):
        self.target_width = 480
        self.target_height = int(self.target_width / self.CARD_ASPECT_RATIO)
    
    def load_image(self, image_path: str) -> Optional[np.ndarray]:
        """
        Lädt ein Bild von Datei
        
        Args:
            image_path: Pfad zur Bilddatei
        
        Returns:
            OpenCV Bild (BGR) oder None
        """
        try:
            image = cv2.imread(image_path)
            if image is None:
                # Versuche mit PIL zu laden (für mehr Formate)
                pil_image = Image.open(image_path)
                image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            return image
        except Exception as e:
            print(f"Fehler beim Laden des Bildes: {e}")
            return None
    
    def load_image_from_bytes(self, image_bytes: bytes) -> Optional[np.ndarray]:
        """
        Lädt ein Bild aus Bytes
        
        Args:
            image_bytes: Bilddaten als Bytes
        
        Returns:
            OpenCV Bild (BGR) oder None
        """
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return image
        except Exception as e:
            print(f"Fehler beim Laden des Bildes aus Bytes: {e}")
            return None
    
    def preprocess_for_ocr(self, image: np.ndarray) -> np.ndarray:
        """
        Bereitet Bild für OCR vor
        
        Args:
            image: Eingabebild (BGR)
        
        Returns:
            Vorverarbeitetes Bild für OCR
        """
        # In Graustufen konvertieren
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Rauschen reduzieren
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        
        # Kontrast erhöhen mit CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)
        
        # Binarisierung mit adaptivem Threshold
        binary = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        return binary
    
    def extract_card_region(self, image: np.ndarray) -> Tuple[Optional[np.ndarray], float]:
        """
        Extrahiert die Kartenregion aus einem Bild
        
        Args:
            image: Eingabebild mit Karte
        
        Returns:
            Tuple aus (extrahierte Kartenregion, Konfidenz)
        """
        # In Graustufen konvertieren
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Kanten erkennen
        edges = cv2.Canny(gray, 50, 150)
        
        # Konturen finden
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None, 0.0
        
        # Nach größter Kontur mit passendem Seitenverhältnis suchen
        best_card = None
        best_confidence = 0.0
        image_area = image.shape[0] * image.shape[1]
        
        for contour in contours:
            # Approximiere die Kontur
            epsilon = 0.02 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            
            # Prüfe ob es ein Rechteck ist (4 Ecken)
            if len(approx) == 4:
                # Berechne Bounding Box
                x, y, w, h = cv2.boundingRect(approx)
                aspect_ratio = w / h if h > 0 else 0
                area = w * h
                
                # Prüfe Seitenverhältnis
                if abs(aspect_ratio - self.CARD_ASPECT_RATIO) < self.CARD_ASPECT_TOLERANCE:
                    # Konfidenz basierend auf Größe
                    area_ratio = area / image_area
                    if 0.1 < area_ratio < 0.95:  # Karte sollte 10-95% des Bildes sein
                        confidence = min(area_ratio * 2, 1.0)
                        if confidence > best_confidence:
                            best_confidence = confidence
                            best_card = self._warp_perspective(image, approx)
        
        # Fallback: Gesamtes Bild verwenden
        if best_card is None:
            return self.resize_to_standard(image), 0.5
        
        return best_card, best_confidence
    
    def _warp_perspective(self, image: np.ndarray, corners: np.ndarray) -> np.ndarray:
        """
        Entzerrt die Karte basierend auf den Eckpunkten
        
        Args:
            image: Originalbild
            corners: 4 Eckpunkte der Karte
        
        Returns:
            Entzerrtes Kartenbild
        """
        # Sortiere Ecken: oben-links, oben-rechts, unten-rechts, unten-links
        corners = corners.reshape(4, 2)
        rect = np.zeros((4, 2), dtype="float32")
        
        s = corners.sum(axis=1)
        rect[0] = corners[np.argmin(s)]  # oben-links
        rect[2] = corners[np.argmax(s)]  # unten-rechts
        
        diff = np.diff(corners, axis=1)
        rect[1] = corners[np.argmin(diff)]  # oben-rechts
        rect[3] = corners[np.argmax(diff)]  # unten-links
        
        # Zielgröße
        dst = np.array([
            [0, 0],
            [self.target_width - 1, 0],
            [self.target_width - 1, self.target_height - 1],
            [0, self.target_height - 1]
        ], dtype="float32")
        
        # Perspektivtransformation
        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(image, M, (self.target_width, self.target_height))
        
        return warped
    
    def resize_to_standard(self, image: np.ndarray) -> np.ndarray:
        """
        Skaliert Bild auf Standardgröße
        
        Args:
            image: Eingabebild
        
        Returns:
            Skaliertes Bild
        """
        return cv2.resize(image, (self.target_width, self.target_height))
    
    def extract_title_region(self, card_image: np.ndarray) -> np.ndarray:
        """
        Extrahiert die Titelregion einer MTG Karte
        
        Args:
            card_image: Normalisiertes Kartenbild
        
        Returns:
            Titelregion für OCR
        """
        height, width = card_image.shape[:2]
        
        # Titelbereich: obere ~8% der Karte, mit Rand
        title_top = int(height * 0.045)
        title_bottom = int(height * 0.095)
        title_left = int(width * 0.05)
        title_right = int(width * 0.75)  # Manakosten ausschließen
        
        title_region = card_image[title_top:title_bottom, title_left:title_right]
        
        # Vergrößern für bessere OCR
        scale = 3
        title_region = cv2.resize(title_region, None, fx=scale, fy=scale, 
                                  interpolation=cv2.INTER_CUBIC)
        
        return title_region
    
    def extract_set_symbol_region(self, card_image: np.ndarray) -> np.ndarray:
        """
        Extrahiert die Set-Symbol-Region
        
        Args:
            card_image: Normalisiertes Kartenbild
        
        Returns:
            Set-Symbol-Region
        """
        height, width = card_image.shape[:2]
        
        # Set-Symbol: rechts in der Mitte der Karte (Typenzeile)
        symbol_top = int(height * 0.545)
        symbol_bottom = int(height * 0.59)
        symbol_left = int(width * 0.85)
        symbol_right = int(width * 0.97)
        
        symbol_region = card_image[symbol_top:symbol_bottom, symbol_left:symbol_right]
        
        return symbol_region
    
    def extract_collector_number_region(self, card_image: np.ndarray) -> np.ndarray:
        """
        Extrahiert die Sammlernummer-Region
        
        Args:
            card_image: Normalisiertes Kartenbild
        
        Returns:
            Region mit Sammlernummer für OCR
        """
        height, width = card_image.shape[:2]
        
        # Sammlernummer: unten links
        number_top = int(height * 0.945)
        number_bottom = int(height * 0.985)
        number_left = int(width * 0.05)
        number_right = int(width * 0.35)
        
        number_region = card_image[number_top:number_bottom, number_left:number_right]
        
        # Vergrößern für bessere OCR
        scale = 3
        number_region = cv2.resize(number_region, None, fx=scale, fy=scale,
                                   interpolation=cv2.INTER_CUBIC)
        
        return number_region
    
    def extract_art_region(self, card_image: np.ndarray) -> np.ndarray:
        """
        Extrahiert die Artwork-Region
        
        Args:
            card_image: Normalisiertes Kartenbild
        
        Returns:
            Artwork-Region
        """
        height, width = card_image.shape[:2]
        
        # Artwork-Bereich
        art_top = int(height * 0.105)
        art_bottom = int(height * 0.535)
        art_left = int(width * 0.065)
        art_right = int(width * 0.935)
        
        art_region = card_image[art_top:art_bottom, art_left:art_right]
        
        return art_region
    
    def compute_image_hash(self, image: np.ndarray) -> str:
        """
        Berechnet einen perzeptuellen Hash für Bildvergleich
        
        Args:
            image: Eingabebild
        
        Returns:
            Hash als Hex-String
        """
        # Auf 8x8 verkleinern
        small = cv2.resize(image, (8, 8))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if len(small.shape) == 3 else small
        
        # Durchschnitt berechnen
        avg = gray.mean()
        
        # Hash erstellen
        hash_bits = (gray > avg).flatten()
        hash_int = sum([2**i for i, v in enumerate(hash_bits) if v])
        
        return format(hash_int, '016x')
    
    def compare_images(self, image1: np.ndarray, image2: np.ndarray) -> float:
        """
        Vergleicht zwei Bilder und gibt Ähnlichkeit zurück
        
        Args:
            image1: Erstes Bild
            image2: Zweites Bild
        
        Returns:
            Ähnlichkeit (0.0 - 1.0)
        """
        # Auf gleiche Größe bringen
        size = (256, 256)
        img1_resized = cv2.resize(image1, size)
        img2_resized = cv2.resize(image2, size)
        
        # In Graustufen konvertieren
        if len(img1_resized.shape) == 3:
            img1_gray = cv2.cvtColor(img1_resized, cv2.COLOR_BGR2GRAY)
        else:
            img1_gray = img1_resized
            
        if len(img2_resized.shape) == 3:
            img2_gray = cv2.cvtColor(img2_resized, cv2.COLOR_BGR2GRAY)
        else:
            img2_gray = img2_resized
        
        # Strukturelle Ähnlichkeit (vereinfacht)
        diff = cv2.absdiff(img1_gray, img2_gray)
        similarity = 1.0 - (np.mean(diff) / 255.0)
        
        return similarity
    
    def enhance_for_matching(self, image: np.ndarray) -> np.ndarray:
        """
        Verbessert Bild für Kartenabgleich
        
        Args:
            image: Eingabebild
        
        Returns:
            Verbessertes Bild
        """
        # Farbkorrektur
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        
        # CLAHE auf L-Kanal
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        
        enhanced = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        
        # Leichte Schärfung
        kernel = np.array([[-1, -1, -1],
                          [-1,  9, -1],
                          [-1, -1, -1]])
        enhanced = cv2.filter2D(enhanced, -1, kernel)
        
        return enhanced
