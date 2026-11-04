# DevKnowledge

Assistant personnel de gestion des connaissances, conçu pour fonctionner localement : Gateway Express, KMS FastAPI et MongoDB 8, orchestrés avec Docker Compose.

## État du projet (4 novembre 2026)

Le KMS propose le CRUD générique `/api/v1/knowledges`, avec validation, pagination, filtres et suppression logique. **Le CRUD générique est livré. La stabilisation est engagée avec STAB-01/02 : correctifs déposés, validations Docker restant à effectuer.** Le frontend Angular, l'authentification/RBAC, les huit spécialisations et le RAG sont des étapes ultérieures.

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

**Installation neuve :** `.env.example` et `compose.yaml` sont désormais alignés ; le compte MongoDB applicatif limité est initialisé sur un volume vierge. **Le démarrage réel reste à tester.** Ne pas écraser un `.env` existant : le bootstrap ne se rejoue pas sur un volume déjà initialisé. Voir le [guide de provisionnement et test isolé](docs/operations/mongodb-bootstrap.md). Ne jamais supprimer les volumes de développement par inadvertance.

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
