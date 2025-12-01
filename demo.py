#!/usr/bin/env python3
"""
Demo-Skript für MTG Card Recognition

Zeigt die grundlegende Verwendung der Bibliothek.
"""

from mtg_recognizer import MTGCardRecognizer, ScryfallAPI


def demo_api_search():
    """Demonstriert die Scryfall API Suche"""
    print("\n" + "="*60)
    print("Demo 1: Scryfall API Suche")
    print("="*60)
    
    api = ScryfallAPI()
    
    # Karte nach Namen suchen
    card_name = "Lightning Bolt"
    print(f"\nSuche nach: '{card_name}'")
    
    card = api.get_card_by_name(card_name)
    if card:
        print(f"  Name: {card.get('name')}")
        print(f"  Mana: {card.get('mana_cost')}")
        print(f"  Typ: {card.get('type_line')}")
        print(f"  Text: {card.get('oracle_text')}")
    
    # Alle Versionen holen
    print(f"\nAlle Drucke von '{card_name}':")
    all_prints = api.get_all_prints(card_name)
    print(f"  Gefunden: {len(all_prints)} Versionen")
    
    for i, p in enumerate(all_prints[:5], 1):
        print(f"  {i}. {p.get('set_name')} ({p.get('set')}) - {p.get('rarity')}")
    
    if len(all_prints) > 5:
        print(f"  ... und {len(all_prints) - 5} weitere")


def demo_autocomplete():
    """Demonstriert die Autovervollständigung"""
    print("\n" + "="*60)
    print("Demo 2: Autovervollständigung")
    print("="*60)
    
    api = ScryfallAPI()
    
    partial = "Black Lot"
    print(f"\nAutovervollständigung für: '{partial}'")
    
    suggestions = api.autocomplete(partial)
    for s in suggestions[:10]:
        print(f"  - {s}")


def demo_recognize_from_name():
    """Demonstriert Erkennung basierend auf Kartennamen"""
    print("\n" + "="*60)
    print("Demo 3: Kartensuche nach Name")
    print("="*60)
    
    recognizer = MTGCardRecognizer()
    
    card_name = "Counterspell"
    print(f"\nSuche Karte: '{card_name}'")
    
    result = recognizer.recognize_from_name(card_name)
    
    if result["success"]:
        print(f"  Name: {result['name']}")
        print(f"  Set: {result['set_name']} ({result['set_code']})")
        print(f"  Nummer: #{result['collector_number']}")
        print(f"  Bild: {result['image_url']}")
    else:
        print(f"  Fehler: {result['error']}")


def demo_get_all_versions():
    """Demonstriert das Abrufen aller Versionen"""
    print("\n" + "="*60)
    print("Demo 4: Alle Versionen einer Karte")
    print("="*60)
    
    recognizer = MTGCardRecognizer()
    
    card_name = "Sol Ring"
    print(f"\nAlle Versionen von: '{card_name}'")
    
    versions = recognizer.get_all_versions(card_name)
    print(f"Gefunden: {len(versions)} Versionen\n")
    
    # Gruppiert nach Seltenheit
    by_rarity = {}
    for v in versions:
        rarity = v.get("rarity", "unknown")
        by_rarity.setdefault(rarity, []).append(v)
    
    for rarity in ["mythic", "rare", "uncommon", "common"]:
        if rarity in by_rarity:
            print(f"\n{rarity.upper()} ({len(by_rarity[rarity])} Stück):")
            for v in by_rarity[rarity][:3]:
                price = v.get("prices", {}).get("usd", "N/A")
                print(f"  - {v['set_name']} ({v['set_code']}) - ${price}")


def demo_image_recognition():
    """Demonstriert die Bilderkennung (erfordert Testbild)"""
    print("\n" + "="*60)
    print("Demo 5: Bilderkennung")
    print("="*60)
    
    print("""
    Um die Bilderkennung zu testen, führe aus:
    
    python main.py --image /pfad/zu/karte.jpg
    
    Oder mit Webcam:
    
    python main.py --webcam
    
    Hinweis: Tesseract OCR muss installiert sein für Texterkennung.
    """)


def main():
    print("\n" + "#"*60)
    print("#  MTG Card Recognition - Demo")
    print("#"*60)
    
    try:
        demo_api_search()
        demo_autocomplete()
        demo_recognize_from_name()
        demo_get_all_versions()
        demo_image_recognition()
        
        print("\n" + "="*60)
        print("Demo abgeschlossen!")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\nFehler bei der Demo: {e}")
        print("Stelle sicher, dass alle Abhängigkeiten installiert sind:")
        print("  pip install -r requirements.txt")


if __name__ == "__main__":
    main()
