"""
MTG Card Recognition Package
"""

from .recognizer import MTGCardRecognizer
from .scryfall_api import ScryfallAPI
from .image_processor import ImageProcessor
from .ocr_engine import OCREngine
from .card_matcher import CardMatcher

__version__ = "1.0.0"
__all__ = [
    "MTGCardRecognizer",
    "ScryfallAPI", 
    "ImageProcessor",
    "OCREngine",
    "CardMatcher"
]
