# DevKnowledge

Assistant personnel de gestion des connaissances, conçu pour fonctionner localement : Gateway Express, KMS FastAPI et MongoDB 8, orchestrés avec Docker Compose.

## État du projet (9 novembre 2026)

Le KMS propose le CRUD générique `/api/v1/knowledges`, avec validation, pagination, filtres et suppression logique. **Bootstrap MongoDB, configuration Gateway et readiness sont validés localement ; la CI est définie et les dépendances Python sont verrouillées.** Le frontend Angular, l'authentification/RBAC, les huit spécialisations et le RAG sont des étapes ultérieures.

La Gateway relaie les routes CRUD sur `127.0.0.1:3000/api/v1/knowledges`. Le KMS est interne au réseau Compose par défaut ; son port de diagnostic est optionnel. Aucune protection d'accès applicative n'est encore en place ; ne pas exposer l'API sur une interface publique.

- [Validation du 9 novembre 2026 et limites restantes](docs/iterations/validation-stabilisation-2026-11-09.md)
- [CI GitHub Actions](https://github.com/tomtoomuch/DevKnowledge/actions/workflows/ci.yml)
- [Relais Gateway → KMS : contrat, limites et diagnostic](docs/architecture/gateway-kms.md)
- [Point d'avancement historique au 4 novembre 2026](docs/iterations/point-avancement-2026-11-04.md)
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

La Gateway écoute par défaut sur `127.0.0.1:3000` ; le KMS et MongoDB ne sont pas publiés sur l'hôte. Pour Swagger ou le diagnostic direct, utiliser `docker compose -f compose.yaml -f compose.debug.yaml up -d --build`, puis [Swagger UI du KMS](http://127.0.0.1:8000/docs).

**Installation neuve :** `.env.example` et `compose.yaml` sont alignés ; le compte MongoDB applicatif limité est initialisé sur un volume vierge. **Le démarrage réel et le redémarrage ont été validés sur un projet isolé.** Ne pas écraser un `.env` existant : le bootstrap ne se rejoue pas sur un volume déjà initialisé. Voir le [guide de provisionnement et test isolé](docs/operations/mongodb-bootstrap.md). Ne jamais supprimer les volumes de développement par inadvertance.

## Tests

Le relais Gateway possède une suite dédiée ; la CI exécute aussi les 113 tests unitaires KMS, les 117 tests KMS avec MongoDB et les scénarios de bootstrap, CRUD via Gateway et panne/reprise. Depuis un environnement Python virtuel pour les commandes KMS :

```bash
# Gateway
cd backend/api-gateway
npm ci
npm test
cd ../..

# KMS sans MongoDB réel
cd backend/knowledge-service
python -m pip install --require-hashes -r requirements-test.txt
python -m pytest -m "not integration"
cd ../..
```

Suite KMS complète sur MongoDB **jetable et isolé** :

```bash
docker compose -p devknowledge-kms-crud-test -f backend/knowledge-service/tests/compose.integration.yaml up --build --abort-on-container-exit --exit-code-from kms-tests kms-tests
docker compose -p devknowledge-kms-crud-test -f backend/knowledge-service/tests/compose.integration.yaml down --volumes
```

Le nettoyage par `down --volumes` est strictement réservé au projet Compose de test `devknowledge-kms-crud-test`. Pour davantage de détails et les objectifs du prochain jalon : [plan de stabilisation](docs/iterations/iteration-2-stabilisation.md).

Validation du Compose réel avec stockage jetable, port Gateway personnalisé,
redémarrage, panne MongoDB et reprise (Docker démarré, Compose 2.24.4 minimum) :

```bash
python scripts/check_stabilization.py
```

Le script supprime uniquement le projet de test qu'il crée et écrit son rapport
dans `test-results/stabilization.json`.
