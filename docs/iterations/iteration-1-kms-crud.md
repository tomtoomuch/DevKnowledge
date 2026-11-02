---
title: "Itération 1 — Livraison du CRUD KMS"
date: "2026-11-02"
tags: [devknowledge, kms, livraison, tests]
---

# Itération 1 — Livraison du CRUD KMS

Le CRUD REST générique des connaissances est implémenté sur `feature/kms-knowledge-crud`, à partir de `dev` au commit `4c7d412`. Les cinq opérations sont validées par des tests unitaires sans base, des intégrations sur MongoDB 8 isolé et un parcours HTTP sur un véritable processus Uvicorn dans Docker. Aucune fusion vers `dev` ou `main` n'est effectuée par cette livraison.

Le code et les tests sont regroupés dans le commit `1cd79bb`. La documentation accompagne cette livraison dans un commit distinct.

## Modifications livrées

- Création, consultation, liste filtrée et paginée, modification partielle et suppression logique sous `/api/v1/knowledges`.
- Modèles Pydantic d'entrée et de sortie : huit types autorisés, tailles des champs, champs internes refusés, PATCH limité aux champs fournis et UUID de chemin validés.
- Séparation routes, schemas, services, repositories et DB, avec repository et identité du demandeur injectables.
- Persistance dans `knowledge_items`, UUID v4 générés par le serveur, dates UTC et index chronologique initialisé de manière idempotente.
- Traduction des erreurs MongoDB en 503 sans informations de connexion dans les réponses ou journaux ; conservation des contrôles `/health` et `/health/ready`.
- Tests unitaires et tests d'intégration isolés, documentation du contrat HTTP et parcours de vérification manuelle.

## Audit et choix techniques

Le socle initial possédait déjà FastAPI, `AsyncMongoClient`, les contrôles de santé et une configuration pytest/pytest-cov. Les deux tests de santé initiaux passaient hors sandbox. Le client MongoDB et son cycle de vie sont réutilisés et déplacés dans le module DB : aucune connexion n'est ouverte par requête.

La dépendance Pydantic v2 est désormais explicite. Le minimum PyMongo passe de `4.10` à `4.13` pour l'API asynchrone stable. La dépendance existante `httpx2` est conservée ; la version Starlette installée la privilégie pour ses tests. `pytest-cov`, déclaré mais initialement absent de l'environnement local, a été installé pour les mesures.

Les UUID sont stockés sous forme de chaînes canoniques dans `_id`, avec l'unicité native MongoDB. `knowledge_id` est exposé dans le domaine et en JSON, sans copie redondante dans le document BSON. Les dates utilisent UTC avec fuseau et sont générées à la précision de la milliseconde, cohérente avec BSON ; le client est configuré avec `tz_aware`.

L'index composé `deleted_at ASC, created_at DESC, _id ASC` sert le filtre des documents actifs et le tri déterministe. L'initialisation répétée de cet index a été vérifiée sur MongoDB réel. Les PATCH et suppressions utilisent des opérations atomiques filtrant `deleted_at: null`. Aucun effacement physique n'est exposé.

Le Compose de développement, les ports 3000 et 8000, leurs restrictions à la boucle locale, les secrets et les volumes existants sont préservés. Le Compose ajouté concerne uniquement les tests : MongoDB utilise `tmpfs`, le réseau est interne et aucun port n'est publié. Les bases temporaires portent le préfixe `devknowledge_test_`. Le test HTTP refuse une URL différente de celle du service Compose jetable avant toute écriture.

## Résultats réellement obtenus

| Validation | Résultat | Couverture mesurée |
| --- | --- | --- |
| KMS unitaire, Windows, Python 3.14.4 / pytest 9.2.0 | **113 réussis**, 4 intégrations désélectionnées, **2,60 s** | **259/260 instructions**, affichage pytest-cov **99 %**, ratio **99,62 %** |
| KMS complet, Docker, Python 3.14.10 | **117 réussis** : 113 unitaires et 4 intégrations, **2,62 s**, aucun avertissement | **260/260 instructions, 100 %** |
| Gateway, `npm test` | **2 tests réussis**, 1 suite, **6,755 s** | **100 % pour `app.js`** |
| Cohérence des dépendances, `pip check` | Aucune dépendance cassée | Sans objet |
| Configuration de développement, `docker compose config --quiet` | Réussite | Sans objet |
| Services de développement, avant et après validation | Gateway, KMS et MongoDB tous `healthy` | Sans objet |

Dans la mesure unitaire seule, l'unique instruction non couverte est la construction du repository réel dans `app/api/routes/knowledges.py`, ligne 23 : les tests unitaires injectent un repository de test. Cette instruction est exécutée par les intégrations, d'où la couverture complète dans Docker.

L'environnement Docker validé utilisait FastAPI `0.162.0`, Pydantic `2.14.2`, Starlette `1.10.0`, PyMongo `4.19.0` et HTTPX2 `2.16.0`. L'environnement Windows utilisait notamment Pydantic `2.14.1`. Ces versions sont les versions observées lors de l'exécution, pas une promesse de résolution identique à chaque construction future.

Les quatre intégrations couvrent le CRUD et la sérialisation dans une vraie base isolée, les filtres et la pagination, le parcours HTTP/ASGI avec repository MongoDB réel, puis le service Uvicorn déployé dans le Compose de test. Elles vérifient notamment la conservation physique du document supprimé, son exclusion des lectures, les UUID, les dates et les index.

L'environnement Compose de test a été nettoyé avec `down --volumes` après validation ; les trois services de développement sont restés `healthy`.

**Aucun test requis n'est resté empêché.** Le sandbox Windows bloque l'initialisation de sockets locales par `asyncio` dans cet environnement ; la suite a donc été exécutée hors sandbox et dans Docker avec succès. Ce blocage ne signifie pas que les tests unitaires nécessitent MongoDB.

## Fichiers modifiés

- `README.md`
- `docs/index.md`
- `backend/knowledge-service/app/main.py`
- `backend/knowledge-service/pytest.ini`
- `backend/knowledge-service/requirements.txt`
- `backend/knowledge-service/tests/test_health.py`

## Fichiers créés

- `backend/knowledge-service/app/api/__init__.py`
- `backend/knowledge-service/app/api/routes/__init__.py`
- `backend/knowledge-service/app/api/routes/knowledges.py`
- `backend/knowledge-service/app/db/__init__.py`
- `backend/knowledge-service/app/db/mongodb.py`
- `backend/knowledge-service/app/repositories/__init__.py`
- `backend/knowledge-service/app/repositories/knowledge_repository.py`
- `backend/knowledge-service/app/schemas/__init__.py`
- `backend/knowledge-service/app/schemas/knowledge.py`
- `backend/knowledge-service/app/services/__init__.py`
- `backend/knowledge-service/app/services/knowledge_service.py`
- `backend/knowledge-service/tests/test_knowledge_repository.py`
- `backend/knowledge-service/tests/test_knowledge_routes.py`
- `backend/knowledge-service/tests/test_knowledge_service.py`
- `backend/knowledge-service/tests/test_mongodb.py`
- `backend/knowledge-service/tests/integration/conftest.py`
- `backend/knowledge-service/tests/integration/test_knowledge_persistence.py`
- `backend/knowledge-service/tests/integration/test_compose_http.py`
- `backend/knowledge-service/tests/compose.integration.yaml`
- `docs/architecture/kms-knowledge-crud.md`
- `docs/iterations/iteration-1-kms-crud.md`

Le fichier Compose de développement n'est pas modifié. Le MLD de référence n'est pas modifié.

## Écarts provisoires par rapport au MLD

| Sujet | Implémentation de l'itération | Suite prévue |
| --- | --- | --- |
| `knowledge_type_id`, FK obligatoire | `knowledge_type` contient un des huit codes validés ; aucun UUID de référentiel fictif | Créer `knowledge_types` puis établir la correspondance par code unique |
| `created_by_user_id`, FK obligatoire | Valeur nullable tant qu'aucune identité vérifiée n'existe ; abstraction `RequesterIdentity` injectable | Injecter l'identité authentifiée et définir le traitement des données historiques sans auteur |
| Suppression | Ajout de `deleted_at`, absent du MLD v0.2 | Conserver la sémantique de suppression logique dans la modélisation physique |
| `status` | Chaîne non vide de 30 caractères maximum, défaut `DRAFT`, sans enum inventée | Définir le cycle de vie métier et ses autorisations ; les valeurs restent ouvertes dans le MLD |

`validated_at` reste en lecture seule, initialement `null` ; un changement de statut n'affirme pas une validation authentifiée. La représentation MongoDB adapte le modèle physique tout en conservant les UUID métier et la sémantique des dates. Aucune table spécialisée n'est créée.

## Vérification manuelle et reproduction

Les commandes de lancement, de tests unitaires, d'intégrations Docker et le parcours manuel sont détaillés dans [[kms-knowledge-crud|KMS — CRUD générique des connaissances]].

Vérifier le contrat sur `http://127.0.0.1:8000/docs` ou `/openapi.json`, puis effectuer une création, une lecture, une liste filtrée, un PATCH partiel et une suppression. La lecture et la seconde suppression doivent ensuite retourner 404, tandis que le document reste présent dans MongoDB avec `deleted_at` renseigné. Un UUID invalide ou un champ d'audit fourni en entrée doit retourner 422.

## Problèmes résiduels et périmètre reporté

Aucun défaut bloquant connu ne reste sur le CRUD validé. La Gateway ne relaie pas encore les routes CRUD ; le service conserve son exposition locale existante et la cible d'entrée unique demeure à implémenter lors d'une itération dédiée. L'incohérence historique entre les variables `HOST`/`PORT` du Compose Gateway et `GATEWAY_HOST`/`GATEWAY_PORT` lus par son code reste sans effet avec les valeurs par défaut actuelles ; elle n'est pas corrigée ici.

Les utilisateurs, RBAC, authentification, spécialisations des huit types, référentiel de types, historique `knowledge_versions`, RAG, compétences RNCP et preuves de certification restent hors périmètre. Les mises à jour concurrentes n'ont pas encore de verrouillage optimiste, et aucune restauration ou purge physique n'est exposée.
