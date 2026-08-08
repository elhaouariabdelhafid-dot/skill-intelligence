.PHONY: up down init files index query query-v2 eval-compare gen filter phase3 \
        api web dashboard test test-agents clean

up:              ## Démarrer l'infrastructure
	docker compose up -d qdrant postgres ollama

down:
	docker compose down

init:            ## Phase 0 : environnement complet
	bash scripts/init.sh

files:           ## Recréer l'arborescence
	bash scripts/create_files.sh

index:           ## Phase 1 : chunking + indexation Qdrant
	python ingestion/chunking.py && python ingestion/indexer.py

query:           ## RAG naïf        (make query Q="What is a VPC?")
	python retrieval/query_naive.py $(Q)

query-v2:        ## RAG hybride+rerank
	python retrieval/reranker.py $(Q)

eval-compare:    ## Phase 2 : tableau comparatif RAGAS
	python evaluation/ragas_eval.py --compare

gen:             ## Phase 3 : générer N questions (make gen N=200)
	python generation/question_gen.py --n $(or $(N),20)

filter:          ## Phase 3 : filtrer les candidates
	python generation/filters.py --report

phase3: gen filter  ## Phase 3 complète

api:             ## Lancer l'API FastAPI
	uvicorn api.main:app --reload --port 8000

web:             ## Lancer l'interface React
	cd frontend-web && npm run dev

dashboard:       ## Lancer le tableau de bord Streamlit
	streamlit run dashboard/app.py

test:            ## Tests de régression
	python tests/test_regression.py

test-agents:     ## Test du pipeline multi-agents (make test-agents Q=good)
	python tests/test_evaluation.py --quality $(or $(Q),good)

clean:           ## Supprimer caches Python et fichiers temporaires
	find . -path ./.venv -prune -o -name '__pycache__' -type d -print0 | xargs -0 rm -rf
	find . -path ./.venv -prune -o -name '*.py[co]' -print0 | xargs -0 rm -f
