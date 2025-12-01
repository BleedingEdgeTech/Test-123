#!/usr/bin/env python3
"""
MTG Card Recognition - Kommandozeilen-Interface

Verwendung:
    python main.py --image path/to/card.jpg
    python main.py --webcam
    python main.py --name "Lightning Bolt"
    python main.py --batch folder/with/cards/
"""

import argparse
import sys
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="MTG Kartenerkennung - Erkennt Magic: The Gathering Karten und identifiziert Versionen"
    )
    
    # Eingabe-Optionen
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--image", "-i",
        type=str,
        help="Pfad zum Kartenbild"
    )
    input_group.add_argument(
        "--webcam", "-w",
        action="store_true",
        help="Webcam für Live-Erkennung verwenden"
    )
    input_group.add_argument(
        "--name", "-n",
        type=str,
        help="Kartenname für Versionssuche"
    )
    input_group.add_argument(
        "--batch", "-b",
        type=str,
        help="Ordner mit Kartenbildern für Batch-Verarbeitung"
    )
    
    # Optionen
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="OCR deaktivieren"
    )
    parser.add_argument(
        "--all-versions",
        action="store_true",
        help="Alle verfügbaren Versionen anzeigen"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Ausgabe als JSON"
    )
    parser.add_argument(
        "--tesseract-path",
        type=str,
        help="Pfad zur Tesseract-Executable"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Ausführliche Ausgabe"
    )
    
    args = parser.parse_args()
    
    # Importe erst nach Argument-Parsing (schnellerer Start bei --help)
    try:
        from mtg_recognizer import MTGCardRecognizer
    except ImportError as e:
        print(f"Fehler beim Import: {e}")
        print("Bitte installiere die Abhängigkeiten: pip install -r requirements.txt")
        sys.exit(1)
    
    # Recognizer initialisieren
    try:
        recognizer = MTGCardRecognizer(tesseract_path=args.tesseract_path)
    except Exception as e:
        print(f"Fehler bei der Initialisierung: {e}")
        sys.exit(1)
    
    # Verarbeitung basierend auf Eingabemodus
    if args.image:
        result = process_image(recognizer, args)
    elif args.webcam:
        result = process_webcam(recognizer, args)
    elif args.name:
        result = process_name(recognizer, args)
    elif args.batch:
        result = process_batch(recognizer, args)
    else:
        parser.print_help()
        sys.exit(1)
    
    # Ausgabe
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_result(result, verbose=args.verbose)


def process_image(recognizer, args):
    """Verarbeitet ein einzelnes Bild"""
    image_path = Path(args.image)
    
    if not image_path.exists():
        return {"success": False, "error": f"Datei nicht gefunden: {args.image}"}
    
    print(f"Analysiere: {image_path.name}...")
    
    result = recognizer.recognize_card(
        str(image_path),
        use_ocr=not args.no_ocr
    )
    
    if args.all_versions and result.get("success") and result.get("name"):
        result["all_versions"] = recognizer.get_all_versions(result["name"])
    
    return result


def process_webcam(recognizer, args):
    """Verarbeitet Webcam-Eingabe"""
    print("Starte Webcam-Erkennung...")
    
    result = recognizer.recognize_from_webcam()
    
    if args.all_versions and result.get("success") and result.get("name"):
        result["all_versions"] = recognizer.get_all_versions(result["name"])
    
    return result


def process_name(recognizer, args):
    """Verarbeitet Namenssuche"""
    print(f"Suche nach: {args.name}...")
    
    if args.all_versions:
        versions = recognizer.get_all_versions(args.name)
        return {
            "success": bool(versions),
            "name": args.name,
            "total_versions": len(versions),
            "versions": versions
        }
    else:
        return recognizer.recognize_from_name(args.name)


def process_batch(recognizer, args):
    """Verarbeitet mehrere Bilder"""
    batch_path = Path(args.batch)
    
    if not batch_path.exists() or not batch_path.is_dir():
        return {"success": False, "error": f"Ordner nicht gefunden: {args.batch}"}
    
    # Unterstützte Bildformate
    extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
    image_files = [
        f for f in batch_path.iterdir()
        if f.suffix.lower() in extensions
    ]
    
    if not image_files:
        return {"success": False, "error": "Keine Bilddateien gefunden"}
    
    print(f"Verarbeite {len(image_files)} Bilder...")
    
    results = recognizer.batch_recognize(
        [str(f) for f in image_files],
        use_ocr=not args.no_ocr
    )
    
    # Zusammenfassung
    successful = sum(1 for r in results if r.get("success"))
    
    return {
        "success": True,
        "total": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results
    }


def print_result(result, verbose=False):
    """Formatierte Konsolenausgabe"""
    print("\n" + "="*50)
    
    if not result.get("success"):
        print(f"❌ Fehler: {result.get('error', 'Unbekannter Fehler')}")
        return
    
    # Batch-Ergebnis
    if "results" in result:
        print(f"📦 Batch-Verarbeitung abgeschlossen")
        print(f"   Gesamt: {result['total']}")
        print(f"   Erfolgreich: {result['successful']}")
        print(f"   Fehlgeschlagen: {result['failed']}")
        
        if verbose:
            print("\nDetails:")
            for i, r in enumerate(result["results"], 1):
                status = "✓" if r.get("success") else "✗"
                name = r.get("name", "Unbekannt")
                set_name = r.get("set_name", "")
                print(f"  {i}. {status} {name} ({set_name})")
        return
    
    # Versions-Liste
    if "versions" in result:
        print(f"📚 Alle Versionen von: {result['name']}")
        print(f"   Gefunden: {result['total_versions']} Versionen\n")
        
        for i, v in enumerate(result["versions"][:20], 1):
            rarity_symbol = {"common": "●", "uncommon": "◆", "rare": "★", "mythic": "✦"}.get(v.get("rarity"), "○")
            print(f"  {i:2}. {rarity_symbol} {v['set_name']} ({v['set_code'].upper()}) #{v['collector_number']}")
            if verbose and v.get("prices"):
                usd = v["prices"].get("usd", "N/A")
                print(f"      Preis: ${usd}")
        
        if result["total_versions"] > 20:
            print(f"\n  ... und {result['total_versions'] - 20} weitere Versionen")
        return
    
    # Einzelergebnis
    print(f"✅ Karte erkannt!")
    print(f"\n   Name:       {result.get('name', 'Unbekannt')}")
    print(f"   Set:        {result.get('set_name', 'Unbekannt')} ({result.get('set_code', '???').upper()})")
    print(f"   Nummer:     #{result.get('collector_number', 'N/A')}")
    print(f"   Seltenheit: {result.get('rarity', 'N/A').capitalize()}")
    print(f"   Konfidenz:  {result.get('confidence', 0)*100:.1f}%")
    
    if verbose:
        print(f"\n   Scryfall:   {result.get('scryfall_uri', 'N/A')}")
        print(f"   Bild:       {result.get('image_url', 'N/A')}")
        
        if result.get("prices"):
            print(f"\n   Preise:")
            for currency, price in result["prices"].items():
                if price:
                    print(f"      {currency.upper()}: {price}")
        
        if result.get("all_matches"):
            print(f"\n   Alternative Versionen:")
            for m in result["all_matches"][:5]:
                print(f"      - {m['set_name']} ({m['set_code'].upper()}) - Score: {m['score']*100:.1f}%")
    
    print("="*50)


if __name__ == "__main__":
    main()
