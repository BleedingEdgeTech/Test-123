"""
Scryfall API Client für MTG Karteninformationen
"""

import requests
import time
from typing import Optional, List, Dict, Any
from urllib.parse import quote


class ScryfallAPI:
    """Client für die Scryfall MTG API"""
    
    BASE_URL = "https://api.scryfall.com"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MTGCardRecognizer/1.0",
            "Accept": "application/json"
        })
        self._last_request_time = 0
        self._rate_limit_delay = 0.1  # 100ms zwischen Requests (Scryfall Limit)
    
    def _rate_limit(self):
        """Implementiert Rate Limiting für die API"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()
    
    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Führt einen GET-Request durch"""
        self._rate_limit()
        try:
            response = self.session.get(f"{self.BASE_URL}{endpoint}", params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"API Fehler: {e}")
            return None
    
    def search_cards(self, query: str, unique: str = "cards") -> List[Dict]:
        """
        Sucht nach Karten basierend auf einer Suchanfrage
        
        Args:
            query: Suchbegriff (z.B. Kartenname)
            unique: "cards", "art", oder "prints" für verschiedene Ergebnistypen
        
        Returns:
            Liste von Kartendaten
        """
        cards = []
        params = {"q": query, "unique": unique}
        
        data = self._get("/cards/search", params)
        if not data:
            return cards
        
        cards.extend(data.get("data", []))
        
        # Paginierung
        while data and data.get("has_more"):
            next_page = data.get("next_page")
            if next_page:
                self._rate_limit()
                try:
                    response = self.session.get(next_page)
                    response.raise_for_status()
                    data = response.json()
                    cards.extend(data.get("data", []))
                except:
                    break
            else:
                break
        
        return cards
    
    def get_card_by_name(self, name: str, fuzzy: bool = True) -> Optional[Dict]:
        """
        Findet eine Karte nach Namen
        
        Args:
            name: Kartenname
            fuzzy: Wenn True, wird unscharfe Suche verwendet
        
        Returns:
            Kartendaten oder None
        """
        endpoint = "/cards/named"
        param_key = "fuzzy" if fuzzy else "exact"
        return self._get(endpoint, {param_key: name})
    
    def get_all_prints(self, card_name: str) -> List[Dict]:
        """
        Holt alle Druckversionen einer Karte
        
        Args:
            card_name: Name der Karte
        
        Returns:
            Liste aller Versionen der Karte
        """
        # Erst die Karte finden
        card = self.get_card_by_name(card_name)
        if not card:
            return []
        
        # Alle Prints suchen
        prints_uri = card.get("prints_search_uri")
        if prints_uri:
            self._rate_limit()
            try:
                response = self.session.get(prints_uri)
                response.raise_for_status()
                data = response.json()
                return data.get("data", [])
            except:
                pass
        
        # Fallback: Manuelle Suche
        oracle_id = card.get("oracle_id")
        if oracle_id:
            return self.search_cards(f"oracleid:{oracle_id}", unique="prints")
        
        return [card]
    
    def get_card_image_url(self, card: Dict, size: str = "normal") -> Optional[str]:
        """
        Extrahiert die Bild-URL aus Kartendaten
        
        Args:
            card: Kartendaten von Scryfall
            size: "small", "normal", "large", "png", "art_crop", "border_crop"
        
        Returns:
            Bild-URL oder None
        """
        image_uris = card.get("image_uris", {})
        if image_uris:
            return image_uris.get(size)
        
        # Für doppelseitige Karten
        card_faces = card.get("card_faces", [])
        if card_faces and card_faces[0].get("image_uris"):
            return card_faces[0]["image_uris"].get(size)
        
        return None
    
    def download_card_image(self, card: Dict, size: str = "normal") -> Optional[bytes]:
        """
        Lädt das Kartenbild herunter
        
        Args:
            card: Kartendaten
            size: Bildgröße
        
        Returns:
            Bilddaten als Bytes oder None
        """
        url = self.get_card_image_url(card, size)
        if not url:
            return None
        
        self._rate_limit()
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.content
        except:
            return None
    
    def get_set_info(self, set_code: str) -> Optional[Dict]:
        """
        Holt Informationen über ein Set
        
        Args:
            set_code: 3-4 Buchstaben Set-Code (z.B. "LEA", "MH2")
        
        Returns:
            Set-Informationen
        """
        return self._get(f"/sets/{set_code}")
    
    def autocomplete(self, query: str) -> List[str]:
        """
        Autovervollständigung für Kartennamen
        
        Args:
            query: Teilweiser Kartenname
        
        Returns:
            Liste möglicher Kartennamen
        """
        data = self._get("/cards/autocomplete", {"q": query})
        if data:
            return data.get("data", [])
        return []
    
    def identify_card_version(self, name: str, set_code: Optional[str] = None, 
                             collector_number: Optional[str] = None) -> Optional[Dict]:
        """
        Identifiziert eine spezifische Kartenversion
        
        Args:
            name: Kartenname
            set_code: Set-Code (optional)
            collector_number: Sammlernummer (optional)
        
        Returns:
            Kartendaten der spezifischen Version
        """
        if set_code and collector_number:
            return self._get(f"/cards/{set_code}/{collector_number}")
        
        if set_code:
            cards = self.search_cards(f'"{name}" set:{set_code}')
            return cards[0] if cards else None
        
        return self.get_card_by_name(name)
