"""Exporte les questions acceptées vers un format prêt pour Google Forms.

Produit deux fichiers :
- questions_forms.txt : les questions formatées, à copier dans Google Forms
- questions_mapping.csv : la correspondance question_id <-> texte, pour réimporter
  les réponses ensuite dans le système.

Usage :
    python export_forms.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ACCEPTED = Path("data/processed/questions_accepted.jsonl")
OUT_TXT = Path("data/processed/questions_forms.txt")
OUT_MAP = Path("data/processed/questions_mapping.csv")


def main():
    questions = [json.loads(l) for l in ACCEPTED.open() if l.strip()]
    print(f"{len(questions)} questions chargées")

    # Fichier texte lisible pour copier dans Google Forms
    with OUT_TXT.open("w", encoding="utf-8") as f:
        f.write("QUESTIONS POUR GOOGLE FORMS\n")
        f.write("=" * 60 + "\n\n")
        f.write("INSTRUCTIONS :\n")
        f.write("1. Crée un Google Forms (forms.google.com)\n")
        f.write("2. Ajoute d'abord un champ 'Nom' (réponse courte)\n")
        f.write("3. Pour chaque question ci-dessous : ajoute une question de\n")
        f.write("   type 'Paragraphe' (réponse longue), colle l'intitulé.\n")
        f.write("4. Le numéro [Q-xxxx] sert à relier les réponses au système :\n")
        f.write("   mets-le au début du titre de chaque question dans Forms.\n\n")
        f.write("=" * 60 + "\n\n")

        for i, q in enumerate(questions, 1):
            f.write(f"--- Question {i} ---\n")
            f.write(f"[{q['question_id']}] ({q['service']} / {q['difficulty']})\n")
            f.write(f"{q['question']}\n\n")

    # CSV de correspondance pour réimporter les réponses
    with OUT_MAP.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["question_id", "service", "difficulty", "bloom_level",
                         "skill", "question"])
        for q in questions:
            writer.writerow([q["question_id"], q["service"], q["difficulty"],
                             q["bloom_level"], q["skill"], q["question"]])

    print(f"Écrit : {OUT_TXT}")
    print(f"Écrit : {OUT_MAP}")
    print("\nOuvre questions_forms.txt et suis les instructions.")


if __name__ == "__main__":
    main()
