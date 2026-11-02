# DevKnowledge

Assistant personnel de gestion des connaissances, exécuté localement : Gateway Express, KMS FastAPI et MongoDB 8, orchestrés avec Docker Compose.

Le KMS propose le CRUD générique `/api/v1/knowledges`, avec validation, pagination, filtres et suppression logique. Le frontend, l'authentification et le RAG sont prévus ultérieurement.

- [Documentation du CRUD et lancement](docs/architecture/kms-knowledge-crud.md)
- [Rapport de validation de l'itération 1](docs/iterations/iteration-1-kms-crud.md)
- [Index documentaire](docs/index.md)

Depuis la racine, avec les variables `.env` existantes :

```powershell
docker compose up -d --build
```

La Gateway écoute sur `127.0.0.1:3000`, le KMS sur `127.0.0.1:8000`. MongoDB reste privé au réseau Compose. OpenAPI : [Swagger UI](http://127.0.0.1:8000/docs). La Gateway ne relaie pas encore les routes CRUD.

Suite complète sur un MongoDB jetable, sans utiliser les données de développement :

```powershell
docker compose -p devknowledge-kms-crud-test -f backend/knowledge-service/tests/compose.integration.yaml up --build --abort-on-container-exit --exit-code-from kms-tests kms-tests
docker compose -p devknowledge-kms-crud-test -f backend/knowledge-service/tests/compose.integration.yaml down --volumes
```
