"""Ontologie de compétences AWS dans Neo4j.

POURQUOI un graphe de compétences : les compétences AWS ne sont pas indépendantes.
Comprendre les Security Groups suppose de connaître VPC ; concevoir une archi
Well-Architected suppose des bases dans plusieurs domaines. Un graphe capture ces
DÉPENDANCES, ce qu'une simple liste de scores ne peut pas faire.

CE QUE ÇA APPORTE : des recommandations plus intelligentes. Au lieu de "tu es
faible en X", on peut dire "tu es faible en X, et X dépend de Y (que tu ne
maîtrises pas non plus) — commence par Y".

Structure :
  (Domain)   ex: Security, Networking, Compute, Storage
  (Skill)    ex: IAM, VPC, EC2, S3, RDS, Lambda, Well-Architected
  (User)     les collaborateurs
Relations :
  (Skill)-[:PART_OF]->(Domain)
  (Skill)-[:REQUIRES]->(Skill)          dépendance pédagogique
  (User)-[:HAS_LEVEL {score}]->(Skill)  niveau mesuré
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

from neo4j import GraphDatabase


def get_driver():
    """Connexion Neo4j. URI et identifiants viennent de .env."""
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password))


# ---- Définition de l'ontologie AWS (le "savoir métier") ----

DOMAINS = ["Security", "Networking", "Compute", "Storage", "Architecture"]

# skill -> (domaine, [prérequis])
SKILLS = {
    "IAM":              ("Security",     []),
    "VPC":              ("Networking",   []),
    "Security Groups":  ("Networking",   ["VPC"]),
    "EC2":              ("Compute",      ["VPC", "IAM"]),
    "Lambda":           ("Compute",      ["IAM"]),
    "S3":               ("Storage",      ["IAM"]),
    "RDS":              ("Storage",      ["VPC", "IAM"]),
    "Well-Architected": ("Architecture", ["IAM", "VPC", "EC2", "S3"]),
}


def build_ontology():
    """Construit (ou reconstruit) le graphe de compétences AWS."""
    driver = get_driver()
    with driver.session() as s:
        # Repartir propre
        s.run("MATCH (n) DETACH DELETE n")

        # Domaines
        for d in DOMAINS:
            s.run("CREATE (:Domain {name: $name})", name=d)

        # Compétences + rattachement au domaine
        for skill, (domain, _) in SKILLS.items():
            s.run("""
                MATCH (d:Domain {name: $domain})
                CREATE (sk:Skill {name: $skill})-[:PART_OF]->(d)
            """, skill=skill, domain=domain)

        # Dépendances (prérequis)
        for skill, (_, prereqs) in SKILLS.items():
            for pre in prereqs:
                s.run("""
                    MATCH (a:Skill {name: $skill}), (b:Skill {name: $pre})
                    CREATE (a)-[:REQUIRES]->(b)
                """, skill=skill, pre=pre)

    driver.close()
    n_skills = len(SKILLS)
    n_deps = sum(len(p) for _, p in SKILLS.values())
    print(f"Ontologie construite : {len(DOMAINS)} domaines, {n_skills} compétences, "
          f"{n_deps} dépendances.")


def project_user(user_id: int, profile: dict):
    """Projette le profil d'un collaborateur sur le graphe (relations HAS_LEVEL)."""
    driver = get_driver()
    with driver.session() as s:
        # Créer/mettre à jour le nœud User
        s.run("MERGE (u:User {id: $id}) SET u.name = $name",
              id=user_id, name=profile.get("name", f"User {user_id}"))
        # Retirer les anciens niveaux
        s.run("MATCH (u:User {id: $id})-[r:HAS_LEVEL]->() DELETE r", id=user_id)
        # Projeter les scores par service (nos Skills portent les noms de services)
        for service, score in profile.get("services", {}).items():
            s.run("""
                MATCH (u:User {id: $id})
                MATCH (sk:Skill {name: $skill})
                CREATE (u)-[:HAS_LEVEL {score: $score}]->(sk)
            """, id=user_id, skill=service, score=score)
    driver.close()


def weak_prerequisites(user_id: int, threshold: float = 60.0) -> list[dict]:
    """Pour un collaborateur, trouve les compétences faibles ET leurs prérequis
    également faibles — l'apport clé du graphe.

    Retourne, pour chaque compétence faible, les prérequis à revoir en priorité
    (car il faut les maîtriser AVANT)."""
    driver = get_driver()
    results = []
    with driver.session() as s:
        rows = s.run("""
            MATCH (u:User {id: $id})-[r1:HAS_LEVEL]->(weak:Skill)
            WHERE r1.score < $th
            OPTIONAL MATCH (weak)-[:REQUIRES]->(pre:Skill)<-[r2:HAS_LEVEL]-(u)
            WHERE r2.score < $th
            RETURN weak.name AS skill, r1.score AS score,
                   collect({name: pre.name, score: r2.score}) AS weak_prereqs
            ORDER BY r1.score
        """, id=user_id, th=threshold)
        for r in rows:
            prereqs = [p for p in r["weak_prereqs"] if p["name"] is not None]
            results.append({
                "skill": r["skill"], "score": r["score"],
                "weak_prerequisites": prereqs,
            })
    driver.close()
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true", help="Construire l'ontologie")
    parser.add_argument("--project", type=int, metavar="USER_ID",
                        help="Projeter le profil d'un utilisateur")
    args = parser.parse_args()

    if args.build:
        build_ontology()
    if args.project:
        from skills.profile import compute_profile
        from db.models import User, get_session
        sess = get_session()
        u = sess.query(User).filter(User.id == args.project).first()
        name = u.name if u else f"User {args.project}"
        sess.close()
        prof = compute_profile(args.project)
        prof["name"] = name
        project_user(args.project, prof)
        print(f"Profil de {name} projeté sur le graphe.")
        print("\nCompétences faibles et prérequis à revoir en priorité :")
        for item in weak_prerequisites(args.project):
            print(f"\n  {item['skill']} ({item['score']}%)")
            if item["weak_prerequisites"]:
                for pre in item["weak_prerequisites"]:
                    print(f"    ⚠ prérequis faible : {pre['name']} ({pre['score']}%)")
                    print(f"      → à réviser AVANT {item['skill']}")
            else:
                print(f"    (pas de prérequis faible — peut être travaillé directement)")
