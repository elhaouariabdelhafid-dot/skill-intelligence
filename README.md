# AI Skill Intelligence Platform — PFA CMH

Plateforme d'évaluation des compétences Cloud AWS par **RAG hybride + agents LLM**.
Le système ingère la documentation AWS, génère des questions d'évaluation,
évalue les réponses via trois agents spécialisés, puis produit des profils de
compétences, des recommandations de formation et un graphe de dépendances
pédagogiques. Interface bilingue français / anglais.

---

## Architecture

```
Documentation AWS → Ingestion → Qdrant (RAG hybride)
                                     ↓
                          Génération de questions (filtrées)
                                     ↓
     Réponses candidates → Agents LangGraph → PostgreSQL
     (Grader · Reasoner · Critic + veto)      ↓
                          Profils · Recommandations · Ontologie (Neo4j)
                                     ↓
                          Tableau de bord (Streamlit)
```

---

## Stack technique

| Domaine | Technologie |
|---|---|
| Orchestration agents | LangGraph |
| Base vectorielle | Qdrant (25 490 fragments) |
| Embeddings | FastEmbed ONNX — `paraphrase-multilingual-MiniLM-L12-v2` (multilingue, 384 dim) |
| Recherche | BM25 + dense (fusion RRF) + reranking cross-encoder |
| Modèles LLM | Groq (Llama 3.3 70B / 3.1 8B) · Ollama local (Qwen 2.5) |
| Base relationnelle | PostgreSQL |
| Base graphe | Neo4j |
| Évaluation RAG | RAGAS |
| Validation | SciPy (corrélation humain/IA) |
| Interface | Streamlit |
| Infrastructure | Docker Compose (6 conteneurs) |

---

## Installation (WSL Ubuntu)

```bash
bash scripts/create_files.sh   # arborescence
bash scripts/init.sh           # venv, dépendances, Docker, corpus AWS, Ollama
source .venv/bin/activate
```

Vérifier que le corpus est indexé :
```bash
curl -s http://localhost:6333/collections/aws_docs | grep -o '"points_count":[0-9]*'
# → doit afficher "points_count":25490
```

---

## Démarrage rapide (session type)

```bash
cd ~/skill-intelligence
source .venv/bin/activate
docker start ski-qdrant ski-postgres ski-neo4j
sed -i 's/^LLM_PROVIDER=.*/LLM_PROVIDER=ollama/' .env   # LLM local, sans quota
docker start ski-ollama
streamlit run frontend/app.py                            # → http://localhost:8501
```

---

## Les phases

### Phase 1 — Ingestion & RAG naïf
```bash
python ingestion/loaders.py                 # stats du corpus
python ingestion/chunking.py                # → data/processed/chunks.jsonl
python ingestion/indexer.py --rebuild       # → Qdrant
python retrieval/query_naive.py "What is a VPC security group?"
```

### Phase 2 — RAG avancé & mesure
```bash
python retrieval/hybrid.py "gp2 vs gp3 volumes"
python retrieval/reranker.py "How does IAM evaluate policies?"
python evaluation/ragas_eval.py --system v2      # ou --compare (naïf vs v2)
```
Le système est **bilingue** : les questions peuvent être posées en français.
```bash
python retrieval/reranker.py "Comment fonctionne un groupe de sécurité VPC ?"
```

### Phase 3 — Génération synthétique
```bash
python generation/question_gen.py --n 30       # → questions_candidates.jsonl
python generation/filters.py --report          # → questions_accepted.jsonl
```
Filtres en cascade : structure (F1), déduplication (F2), ancrage thématique (F3),
auto-critique LLM (F4). Cible : taux de rejet < 30 %.

### Phase 4 — Évaluation multi-agents
```bash
python agents/test_evaluation.py --quality good   # réponse correcte → score élevé
python agents/test_evaluation.py --quality bad    # hallucination → veto, score bas
```
Trois agents (Grader, Reasoner, Critic) orchestrés par LangGraph, agrégation
pondérée avec veto anti-hallucination.

### Phase 5 — Profils & recommandations
```bash
python import_forms.py --csv reponses.csv --name-column "NOM:"   # évalue des réponses réelles
python skills/profile.py --user 4                # profil de compétences
python skills/recommendations.py --user 4        # plan de formation ciblé
```

### Phase 6 — Validation humain/IA
```bash
python evaluation/human_rating.py         # notation humaine à l'aveugle
python evaluation/human_correlation.py    # corrélation Spearman humain/IA
```

### Phase 7 — Tableau de bord & ontologie
```bash
python skills/ontology.py --build         # graphe de compétences Neo4j
python skills/ontology.py --project 4     # projette un profil + prérequis faibles
streamlit run frontend/app.py             # tableau de bord (3 vues)
```

---

## Interfaces web

| Service | Adresse | Contenu |
|---|---|---|
| Tableau de bord | http://localhost:8501 | Profils, recommandations |
| Neo4j | http://localhost:7474 | Graphe de compétences (`neo4j` / `password123`) |
| Qdrant | http://localhost:6333/dashboard | Base vectorielle |
| Langfuse | http://localhost:3000 | Traçabilité des appels LLM |

---

## Structure du projet

```
agents/       Agents d'évaluation (Grader, Reasoner, Critic) + graphe LangGraph
api/          Points d'entrée API
core/         Utilitaires transverses
data/         Corpus, chunks, questions générées
db/           Modèles et session PostgreSQL
evaluation/   RAGAS + validation humain/IA
frontend/     Tableau de bord Streamlit
generation/   Génération et filtrage de questions
ingestion/    Chargement, découpe, embeddings, indexation
llm/          Couche d'accès unifiée aux modèles (Groq, Ollama...)
notebooks/    Exploration
retrieval/    Recherche dense, hybride, reranking
scripts/      Scripts d'initialisation
skills/       Profils, recommandations, ontologie
archive/      Patchs et paquets d'installation (historique)
```

---

## Résultats clés

- **RAG** : context_recall 0.94 (v2, juge Llama 3.3 70B), au-dessus du seuil visé
- **Génération** : 90 % de questions acceptées (9,5 % de rejet)
- **Évaluation** : discrimination nette bonne réponse (3.45/4) vs hallucinée (0.45/4)
- **Bilinguisme** : validé de bout en bout (retrieval, génération, évaluation)

---

## Documents

`Rapport_Synthese_PFA.pdf` · `Architecture_Globale.pdf` · `Demonstration_Parcours.pdf`
· `Guide_Demarrage_WSL.pdf`
