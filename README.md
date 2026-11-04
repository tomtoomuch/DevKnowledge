# DevKnowledge

Assistant personnel de gestion des connaissances, conçu pour fonctionner localement : Gateway Express, KMS FastAPI et MongoDB 8, orchestrés avec Docker Compose.

## État du projet (4 novembre 2026)

Le KMS propose le CRUD générique `/api/v1/knowledges`, avec validation, pagination, filtres et suppression logique. **Le CRUD générique est livré, mais la phase de stabilisation n'a pas encore été exécutée.** Le frontend Angular, l'authentification/RBAC, les huit spécialisations et le RAG sont des étapes ultérieures.

La Gateway ne relaie **pas encore** les routes CRUD : le KMS reste accessible directement sur `127.0.0.1:8000` en développement. Aucune protection d'accès applicative n'est encore en place ; ne pas exposer l'API sur une interface publique.

- [Point d'avancement au 4 novembre 2026](docs/iterations/point-avancement-2026-11-04.md)
- [Plan de stabilisation — itération 2](docs/iterations/iteration-2-stabilisation.md)
- [Feuille de route](docs/roadmap.md)
- [Documentation du CRUD et lancement](docs/architecture/kms-knowledge-crud.md)
- [Rapport historique de validation de l'itération 1](docs/iterations/iteration-1-kms-crud.md)
- [Index Obsidian](docs/index.md)

Le MLD v0.2 décrit **56 tables logiques candidates**, et non 56 tables/collections déployées. La première implémentation métier persiste les connaissances dans `knowledge_items`.

## Lancement local

À la racine, avec une configuration `.env` locale existante et valide :

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

La Gateway écoute par défaut sur `127.0.0.1:3000`, le KMS sur `127.0.0.1:8000` ; MongoDB n'est pas publié sur l'hôte. OpenAPI : [Swagger UI du KMS](http://127.0.0.1:8000/docs).

**Installation neuve :** la configuration `.env.example` et le provisionnement du compte applicatif MongoDB nécessitent une stabilisation (notamment `MONGODB_APP_USER` vs `MONGODB_APP_USERNAME`). Ne pas supposer qu'une copie directe de ce fichier permet déjà un démarrage vierge sans intervention. Préserver les volumes existants et ne pas utiliser `down --volumes` sur le Compose de développement.

## Tests

Les commandes ci-dessous sont disponibles dans le dépôt. Les résultats chiffrés du 2 novembre sont **historiques**, non une certification de l'état courant :

```bash
# Gateway
cd backend/api-gateway
npm ci
npm test
cd ../..

# KMS sans MongoDB réel
cd backend/knowledge-service
python -m pip install -r requirements.txt
python -m pytest -m "not integration"
cd ../..
```

Suite KMS complète sur MongoDB **jetable et isolé** :

```bash
docker compose -p devknowledge-kms-crud-test -f backend/knowledge-service/tests/compose.integration.yaml up --build --abort-on-container-exit --exit-code-from kms-tests kms-tests
docker compose -p devknowledge-kms-crud-test -f backend/knowledge-service/tests/compose.integration.yaml down --volumes
```

Le nettoyage par `down --volumes` est strictement réservé au projet Compose de test `devknowledge-kms-crud-test`. Pour davantage de détails et les objectifs du prochain jalon : [plan de stabilisation](docs/iterations/iteration-2-stabilisation.md).
