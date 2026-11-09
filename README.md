# DevKnowledge

Assistant personnel de gestion des connaissances, conçu pour fonctionner localement : Gateway Express, KMS FastAPI et MongoDB 8, orchestrés avec Docker Compose.

## État du projet (9 novembre 2026)

Le KMS propose le CRUD générique `/api/v1/knowledges` (validation, pagination, filtres, suppression logique). **Bootstrap MongoDB, Gateway, readiness et exécution hors ligne après préparation sont vérifiés en CI.** Le frontend Angular inclut la bibliothèque et, dans l'itération 5 proposée, une authentification locale/RBAC avec une administration de comptes limitée à la consultation et la création. Le premier lot de spécialisations métier (huit modèles avec `details` embarqués) est en cours de validation dans la PR #8 ; les relations métiers, les sources et le RAG restent à développer.

**PATCH et DELETE exigent désormais `If-Match` avec la révision lue** (428 sans précondition, 412 si elle est dépassée). Les GET individuels renvoient l’ETag correspondant.

La Gateway relaie les routes CRUD et d'authentification sur `127.0.0.1:3000/api/v1`. Le KMS est interne au réseau Compose par défaut ; son port de diagnostic est optionnel. Le prototype utilise des sessions locales et des permissions vérifiées par le KMS. Il reste strictement privé et ne doit pas être exposé à Internet.

- [Validation du 9 novembre 2026 et limites restantes](docs/iterations/validation-stabilisation-2026-11-09.md)
- [CI GitHub Actions](https://github.com/tomtoomuch/DevKnowledge/actions/workflows/ci.yml)
- [Exécution hors ligne après préparation des images](docs/operations/offline-runtime.md)
- [Dossier de revue de sortie de stabilisation](docs/iterations/revue-sortie-stabilisation-2026-11-09.md)
- [Sauvegarde et restauration locales](docs/operations/backup-restore.md)
- [Écritures conditionnelles : If-Match obligatoire](docs/architecture/knowledge-concurrency.md)
- [Relais Gateway → KMS : contrat, limites et diagnostic](docs/architecture/gateway-kms.md)
- [Point d'avancement historique au 4 novembre 2026](docs/iterations/point-avancement-2026-11-04.md)
- [Plan de stabilisation — itération 2](docs/iterations/iteration-2-stabilisation.md)
- [Feuille de route](docs/roadmap.md)
- [Documentation du CRUD et lancement](docs/architecture/kms-knowledge-crud.md)
- [Rapport historique de validation de l'itération 1](docs/iterations/iteration-1-kms-crud.md)
- [Index Obsidian](docs/index.md)

Le MLD v0.2 décrit **56 tables logiques candidates**, et non 56 tables/collections déployées. La première implémentation métier persiste les connaissances dans `knowledge_items`.

## Frontend Angular

Le frontend Angular est disponible par défaut sur http://127.0.0.1:4200 après le
lancement Compose, configurable avec FRONTEND_PORT. Son serveur Nginx relaie
les requêtes /api/ exclusivement à la Gateway Express sur le réseau Docker.

La liste, la recherche textuelle et les filtres type/statut/favoris
s'exécutent côté serveur, avant pagination. La
consultation, la création, la modification conditionnelle avec ETag/If-Match
et la suppression logique sont prises en charge. L'interface ne persiste que
les champs génériques, pas les spécialisations prévues au MLD.

Lire le [guide frontend](frontend/ui-app/README.md) avant la première utilisation.

## Itération 4 — recherche globale et favoris

L'API accepte désormais `q` (recherche textuelle littérale, sans tenir compte
de la casse, dans le titre, la description et le contenu) et
`is_favorite` (booléen). Ces filtres se combinent avec les filtres
de type/statut et s'appliquent avant la pagination. Dans Angular, la
recherche et le filtre favoris portent donc sur toute la bibliothèque,
et plus seulement sur les éléments visibles. La recherche actuelle
utilise un parcours regex, pas encore un index plein texte.

Voir [la spécification de l'itération 4](docs/iterations/iteration-4-search.md).

## Itération 6 — champs spécialisés des huit types

Le modèle Pydantic propose désormais un sous-document facultatif `details` adapté à chaque type (`CODE_SNIPPET`, `TERMINAL_COMMAND`, `TECHNICAL_PROCEDURE`, `COURSE_NOTE`, `BUG_FIX`, `DOCUMENTATION_RESOURCE`, `BEST_PRACTICE`, `COMPLIANCE_STANDARD`). Le frontend utilise un formulaire correspondant à la catégorie ; les détails s'enregistrent via les routes CRUD existantes et respectent les droits et la révision `If-Match`.

La collection `knowledge_types` est initialisée au démarrage avec les métadonnées des huit catégories ; la Gateway relaie `GET /api/v1/knowledge-types` aux comptes autorisés. Les détails physiques sont embarqués dans `knowledge_items` afin d'éviter des écritures multi-collections non atomiques ; cela **ne matérialise pas** les huit tables spécialisées relationnelles du MLD. Les anciens enregistrements sans `details` continuent à fonctionner.

Voir [itération 6 — implémentation et limites](docs/iterations/iteration-6-specializations.md).

## Lancement local

À la racine, avec une configuration `.env` locale existante et valide :

```bash
# Vérifie que les Dockerfiles et leurs contextes existent réellement.
python scripts/check_dockerfiles.py --compose compose.yaml --env-file .env
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml up -d --build
docker compose -f compose.yaml ps
```

Le dépôt est composé de trois images applicatives, chacune avec son
`Dockerfile` : `frontend/ui-app/Dockerfile`, `backend/api-gateway/Dockerfile`
et `backend/knowledge-service/Dockerfile`. **Il n'existe pas de
Dockerfile à la racine : utiliser Docker Compose, et non
`docker build .`.** Le script de vérification examine les chemins
effectivement calculés par Compose avant toute construction.

Le frontend écoute par défaut sur `127.0.0.1:4200` ; la Gateway sur `127.0.0.1:3000` ; le KMS et MongoDB ne sont pas publiés sur l'hôte. Pour Swagger ou le diagnostic direct, utiliser `docker compose -f compose.yaml -f compose.debug.yaml up -d --build`, puis [Swagger UI du KMS](http://127.0.0.1:8000/docs).

**Installation neuve :** `.env.example` et `compose.yaml` sont alignés ; le compte MongoDB applicatif limité est initialisé sur un volume vierge. **Le démarrage réel et le redémarrage ont été validés sur un projet isolé.** Ne pas écraser un `.env` existant : le bootstrap ne se rejoue pas sur un volume déjà initialisé. Voir le [guide de provisionnement et test isolé](docs/operations/mongodb-bootstrap.md). Ne jamais supprimer les volumes de développement par inadvertance.

## Tests

Le relais Gateway possède une suite dédiée ; la CI exécute aussi les 123 tests unitaires KMS, les 128 tests KMS avec MongoDB et les scénarios de bootstrap, CRUD via Gateway et panne/reprise. Depuis un environnement Python virtuel pour les commandes KMS :

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

Après cette préparation, `python scripts/check_stabilization.py --offline`
rejoue les contrôles sans build ni téléchargement, vérifie l'isolation réseau
et produit `test-results/stabilization-offline.json`. Cela qualifie l'exécution
du socle préparé ; un build complet hors ligne reste à qualifier.


## Itération 5 — identité locale et autorisations RBAC

Après démarrage avec Docker Compose, créer le premier administrateur dans
le conteneur KMS (une seule fois, sans mot de passe dans les arguments) :

```bash
docker compose exec api-kms python -m app.auth.bootstrap_admin --username admin
```

L'interface Angular présente ensuite un écran de connexion locale. Le KMS
vérifie les permissions à chaque requête ; les rôles intégrés sont ADMIN,
EDITOR et READER. Les mots de passe ne sont pas enregistrés en clair ; les
sessions sont révocables et leur jeton opaque n'est pas stocké en clair.
Voir [la documentation de l'identité](docs/iterations/iteration-5-identite-locale.md).

**Attention :** cette authentification n'autorise pas l'exposition publique
du projet ; les ports restent liés à 127.0.0.1 et la revue de sécurité est
à mener avant une éventuelle publication distante.


### Comptes locaux (itération 5)

Créer le premier administrateur via la CLI du conteneur KMS, puis utiliser
l'écran de connexion Angular. Le rôle ADMIN dispose maintenant d'une vue
**Utilisateurs** pour consulter les rôles et créer un compte local ;
EDITOR et READER ne voient pas cette vue, et le serveur refuse leurs requêtes.
Aucun mécanisme d'inscription publique ou de récupération de mot de passe
n'est exposé. Voir [l'itération 5](docs/iterations/iteration-5-identite-locale.md).
