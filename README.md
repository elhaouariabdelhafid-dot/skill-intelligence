# AI Skill Intelligence Platform — PFA CMH

Évaluation des compétences Cloud AWS par RAG + agents LLM.

## Installation (WSL Ubuntu)
```bash
bash scripts/create_files.sh   # arborescence
bash scripts/init.sh           # venv, deps, Docker, corpus AWS, Ollama
source .venv/bin/activate
```

## Phase 1 — RAG naïf
```bash
python ingestion/loaders.py                 # stats du corpus
python ingestion/chunking.py                # -> data/processed/chunks.jsonl
python ingestion/indexer.py                 # -> Qdrant
python retrieval/query_naive.py "What is a VPC security group?"
```

## Phase 2 — RAG avancé + mesure
```bash
python retrieval/hybrid.py "gp2 vs gp3 volumes"          # compare dense/BM25/RRF
python retrieval/reranker.py "How does IAM evaluate policies?"
# compléter evaluation/golden_dataset.json (10 items minimum)
python evaluation/ragas_eval.py --compare                 # tableau naïf vs v2
```

## Phase 3 — Génération synthétique
```bash
python generation/question_gen.py --n 200      # -> questions_candidates.jsonl
python generation/filters.py --report          # -> questions_accepted.jsonl
cat data/processed/filtering_report.json
```

Cible : taux de rejet < 30 %.

## Documents
Architecture_Globale.pdf · Pipeline_Projet.pdf · Cahier_Des_Charges.pdf · Architecture_Technique.pdf
