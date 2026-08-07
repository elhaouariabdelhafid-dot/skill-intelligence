# EvaSmart — Frontend

Interface React connectée à l'API FastAPI du projet.

## Prérequis

- Node.js 18 ou plus (`node -v` pour vérifier)
- L'API doit tourner : `uvicorn api.main:app --port 8010`

## Installation

```bash
cd ~/skill-intelligence/frontend-web
npm install
npm run dev
```

Ouvrir http://localhost:5173

## Configuration

L'adresse de l'API est dans `.env` :

```
VITE_API_BASE=http://localhost:8010
```

Elle est aussi modifiable depuis la page de connexion (bouton « API »).

## Comptes

Les mêmes que le backend (admin@cmh.ma / Admin@2026, etc.).
Les boutons « Connexion » de la page de login remplissent le formulaire.
