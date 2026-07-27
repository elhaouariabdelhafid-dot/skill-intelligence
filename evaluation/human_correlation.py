"""Phase 6 — Corrélation humain/IA : le résultat scientifique de la validation.

Compare tes notes humaines aux scores de l'IA sur les mêmes réponses, et calcule :
- Corrélation de Spearman (rho) : les deux classements sont-ils cohérents ?
- Corrélation de Pearson (r) : relation linéaire
- Écart absolu moyen (MAE) : de combien l'IA s'écarte-t-elle en moyenne ?
- Accord exact et à ±1 : proportion de notes identiques ou proches

INTERPRÉTATION :
- Spearman > 0.7 : forte corrélation, l'IA note "comme l'humain" -> validation réussie
- 0.5-0.7 : corrélation modérée, système utilisable avec réserves
- < 0.5 : faible, à améliorer

Note : l'IA note sur 0-4 (continu), l'humain sur 0-4 (entier). On ramène l'IA
à la même échelle pour l'écart absolu.

Usage :
    python evaluation/human_correlation.py
    python evaluation/human_correlation.py --annotator Aya
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

RATINGS_DIR = Path(__file__).parent / "human_ratings"


def load_ratings(annotator: str) -> list[dict]:
    p = RATINGS_DIR / f"ratings_{annotator}.json"
    if not p.exists():
        raise SystemExit(f"Aucune note trouvée pour '{annotator}'. "
                         f"Lance d'abord human_rating.py")
    data = json.loads(p.read_text())
    return list(data.values())


def analyze(annotator: str):
    from scipy.stats import spearmanr, pearsonr
    import numpy as np

    ratings = load_ratings(annotator)
    if len(ratings) < 3:
        raise SystemExit(f"Trop peu de notes ({len(ratings)}). Note-en au moins 5.")

    human = np.array([r["human_score"] for r in ratings], dtype=float)
    ia = np.array([r["ia_score"] for r in ratings], dtype=float)

    rho, p_rho = spearmanr(human, ia)
    r, p_r = pearsonr(human, ia)
    mae = float(np.mean(np.abs(human - ia)))
    exact = float(np.mean(np.round(ia) == human))
    within1 = float(np.mean(np.abs(np.round(ia) - human) <= 1))

    print(f"\n{'='*60}")
    print(f"VALIDATION HUMAIN / IA — annotateur : {annotator}")
    print(f"{'='*60}")
    print(f"Échantillon : {len(ratings)} réponses\n")

    print("CORRÉLATIONS :")
    print(f"  Spearman (rho)  : {rho:.3f}   (p={p_rho:.3f})")
    print(f"  Pearson (r)     : {r:.3f}   (p={p_r:.3f})")
    print(f"\nÉCARTS :")
    print(f"  Écart absolu moyen (MAE) : {mae:.2f} points sur 4")
    print(f"  Accord exact             : {exact*100:.0f}%")
    print(f"  Accord à ±1 point        : {within1*100:.0f}%")

    print(f"\nINTERPRÉTATION :")
    if rho >= 0.7:
        print("  ✓ Forte corrélation — l'IA note de façon cohérente avec l'humain.")
        print("    La validation confirme la crédibilité du système.")
    elif rho >= 0.5:
        print("  ~ Corrélation modérée — système utilisable, à affiner.")
    else:
        print("  ✗ Corrélation faible — l'évaluation IA diverge de l'humain.")
        print("    Piste : revoir les rubriques ou le modèle juge.")

    # Tableau détaillé
    print(f"\n{'─'*60}")
    print(f"{'Candidat':<12}{'Service':<16}{'Humain':>8}{'IA':>8}{'Écart':>8}")
    print(f"{'─'*60}")
    for rating in sorted(ratings, key=lambda x: x["user"]):
        h = rating["human_score"]
        a = rating["ia_score"]
        print(f"{rating['user'][:11]:<12}{rating['service'][:15]:<16}"
              f"{h:>8}{a:>8.1f}{abs(h-a):>8.1f}")

    # Sauvegarde du résultat
    result = {"annotator": annotator, "n": len(ratings),
              "spearman": round(rho, 3), "pearson": round(r, 3),
              "mae": round(mae, 2), "exact_agreement": round(exact, 3),
              "within_1": round(within1, 3)}
    out = RATINGS_DIR / f"validation_{annotator}.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\nRésultat sauvegardé : {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotator", default="hafid")
    args = parser.parse_args()
    analyze(args.annotator)
