# Structure du projet — EvaSmart / skill-intelligence

Plateforme d'évaluation automatisée : pipeline NLP → RAG → agents multiples → scoring.

## Arborescence cible

```
skill-intelligence/
│
├── README.md              Présentation, installation, lancement
├── STRUCTURE.md           Ce document
├── CLAUDE.md              Contexte projet pour l'assistant
├── Makefile               Commandes courantes (make up, make eval…)
├── docker-compose.yml     Services : MySQL, Neo4j, Qdrant, Ollama, Langfuse
├── requirements.txt       Dépendances Python
├── .env.example           Modèle de configuration (le .env réel n'est pas versionné)
├── config.py              Chargement centralisé de la configuration
│
├── api/                   ── COUCHE HTTP (FastAPI)
│   ├── main.py                point d'entrée de l'application
│   ├── access_api.py          gestion des accès + access_models.py
│   ├── requests_api.py        demandes d'accès + requests_models.py
│   ├── sessions_api.py        sessions d'évaluation + sessions_models.py
│   ├── settings_api.py        paramètres + settings_models.py
│   ├── config_api.py          exposition de la configuration
│   ├── onboarding.py          parcours d'inscription
│   └── reset_api.py           réinitialisation de mot de passe
│
├── auth/                  ── AUTHENTIFICATION
│   ├── auth_api.py            routes login / register
│   ├── auth_models.py         schémas Pydantic
│   ├── security.py            bcrypt, JWT
│   └── seed_users.py          création des comptes initiaux
│
├── db/                    ── PERSISTANCE
│   ├── models.py              modèles SQLAlchemy
│   └── session.py             moteur et session
│
├── ingestion/             ── ÉTAPE 1 : construction du corpus
│   ├── loaders.py             lecture des documents sources
│   ├── chunking.py            découpage en passages
│   ├── embeddings.py          vectorisation
│   └── indexer.py             indexation vectorielle
│
├── retrieval/             ── ÉTAPE 2 : recherche
│   ├── query_naive.py         recherche dense simple (baseline)
│   ├── hybrid.py              recherche hybride BM25 + dense
│   └── reranker.py            reclassement des passages
│
├── generation/            ── ÉTAPE 3 : génération de questions
│   ├── question_gen.py        génération à partir du corpus
│   ├── filters.py             filtrage qualité
│   └── schemas.py             structures de données
│
├── agents/                ── ÉTAPE 4 : évaluation multi-agents (LangGraph)
│   ├── graph.py               orchestration du graphe
│   ├── state.py               état partagé entre agents
│   ├── grader.py              notation
│   ├── critic.py              critique de la réponse
│   ├── reasoner.py            analyse du raisonnement
│   ├── coverage.py            couverture des points clés
│   ├── failures.py            détection des erreurs types
│   └── aggregator.py          agrégation du score final
│
├── skills/                ── ÉTAPE 5 : profil de compétences
│   ├── ontology.py            ontologie des compétences (Neo4j)
│   ├── profile.py             construction du profil apprenant
│   ├── recommendations.py     recommandations personnalisées
│   └── simulate.py            simulation de progression
│
├── llm/                   ── ACCÈS AUX MODÈLES
│   └── client.py              client unifié (Ollama / Groq / Cerebras)
│
├── core/                  Utilitaires transverses
│
├── evaluation/            ── VALIDATION SCIENTIFIQUE
│   ├── golden_dataset.json    jeu de référence complet
│   ├── golden_small.json      sous-ensemble rapide
│   ├── ragas_eval.py          métriques RAGAS
│   ├── human_rating.py        collecte des notes humaines
│   ├── human_correlation.py   corrélation humain / système
│   ├── human_ratings/         notes brutes (non versionné)
│   └── results/               sorties d'évaluation (non versionné)
│
├── frontend-web/          ── INTERFACE UTILISATEUR (React + Vite)
│   ├── src/App.jsx            application principale
│   ├── src/main.jsx           point d'entrée
│   ├── src/styles.css         styles
│   └── public/                logos et favicon
│
├── dashboard/             ── TABLEAU DE BORD RH (Streamlit)
│   └── app.py                 3 vues : équipe, profil individuel, détail
│
├── scripts/               ── UTILITAIRES (exécutés manuellement)
│   ├── init.sh                initialisation de l'environnement
│   ├── init_db.sql            schéma de base
│   ├── download_corpus.sh     téléchargement du corpus
│   ├── import_forms.py        import des réponses de formulaire
│   ├── export_forms.py        export des questions vers formulaire
│   ├── clean_evals.py         nettoyage des évaluations
│   ├── inspect_evals.py       inspection des résultats
│   ├── link_profiles.py       association profils / sessions
│   └── measure_variance.py    mesure de variance des agents
│
├── tests/                 ── TESTS (test_*.py et test_*.sh)
│
├── data/                  ── DONNÉES (non versionné)
│   ├── raw/                   corpus source (AWS docs, whitepapers)
│   ├── processed/             chunks, index BM25, questions générées
│   ├── reference/             guides d'examen, questions d'exemple
│   ├── exports/               sujets d'examen générés (PDF)
│   └── forms/                 réponses collectées (CSV)
│
├── logs/                  Journaux d'exécution (non versionné)
├── notebooks/             Exploration Jupyter
├── volumes/               Volumes Docker persistants (6,8 Go — non versionné)
│
└── archive/               ── HISTORIQUE (non versionné)
    ├── packages/              26 archives .zip de livraisons successives
    ├── backups/               fichiers .bak / .bakN
    ├── before_fix/            versions antérieures des agents
    ├── patches/               correctifs ponctuels appliqués
    └── legacy/                code remplacé, conservé pour référence
```

## Les deux interfaces

Le projet expose **deux** interfaces distinctes — ne pas les confondre :

| Dossier | Technologie | Public | Lancement |
|---|---|---|---|
| `frontend-web/` | React + Vite | Étudiants, enseignants, admins | `make web` |
| `dashboard/` | Streamlit | RH / pilotage (vue Phase 7) | `make dashboard` |

## Chaîne de traitement

```
documents  →  ingestion  →  retrieval  →  generation  →  agents  →  skills
  (raw)       (chunks +      (passages     (questions)   (scoring)  (profil +
              vecteurs)      pertinents)                            reco)
                                              ↓
                                          evaluation
                                     (RAGAS + corrélation humaine)
```

## Conventions

- **Un dossier = une étape du pipeline.** Un nouveau composant rejoint l'étape correspondante, pas la racine.
- **La racine ne contient que de la configuration.** Pas de script, de log, de CSV ni d'archive.
- **Pas de fichier `.bak`.** L'historique de version est assuré par git ; les anciennes versions vivent dans `archive/`.
- **Les tests vivent dans `tests/`**, jamais dans `scripts/` ni à côté du code applicatif.
- **Les données lourdes ne sont pas versionnées** (`data/`, `volumes/`, `logs/`, `archive/`).

## Amélioration ultérieure possible

Regrouper les paquets Python applicatifs (`api`, `auth`, `db`, `agents`, `ingestion`,
`retrieval`, `generation`, `skills`, `llm`, `core`) sous un dossier `backend/` unique.
Cela clarifierait la séparation backend / frontend, mais **impose de réécrire tous les
imports** (`from agents.graph import …` → `from backend.agents.graph import …`) ainsi que
les chemins dans `docker-compose.yml` et le `Makefile`. À réserver à une période sans
échéance proche.
