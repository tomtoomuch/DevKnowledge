# DevKnowledge

Assistant personnel de gestion des connaissances, conçu pour fonctionner localement : Gateway Express, KMS FastAPI et MongoDB 8, orchestrés avec Docker Compose.

## État du projet (9 novembre 2026)

Le KMS propose le CRUD générique `/api/v1/knowledges` (validation, pagination, filtres, suppression logique). **Bootstrap MongoDB, Gateway, readiness et exécution hors ligne après préparation sont vérifiés en CI.** Le frontend Angular inclut la bibliothèque et, dans l'itération 5 proposée, une authentification locale/RBAC avec une administration de comptes limitée à la consultation et la création. Les huit spécialisations métier (sous-documents `details`) sont fusionnées dans `chat` via la PR #8. Le premier lot de classification par **tags** est proposé dans la PR #9 ; les technologies, les sources, les liens entre connaissances et le RAG restent à développer.

**PATCH et DELETE exigent désormais `If-Match` avec la révision lue** (428 sans précondition, 412 si elle est dépassée). Les GET individuels renvoient l’ETag correspondant.

**Le Gateway Express est l'unique point d'entrée de toutes les requêtes extérieures, y compris les pages Angular et les ressources statiques.** L'URL locale `http://127.0.0.1:4200` publie le port du **Gateway**, pas celui du frontend Nginx. Le Gateway sert le frontend via son relais interne sur `dmz` et fait transiter `/api/v1/*` vers KMS sur `internal`. Il authentifie et autorise les appels métier. Angular/Nginx, KMS, MongoDB et Collector ne publient aucun port. Le projet n'est pas destiné à être exposé à Internet.

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

L'interface Angular est accessible via **le Gateway Express** sur http://127.0.0.1:4200
après le lancement Compose (`FRONTEND_PORT` configure le port hôte du Gateway).
Le Gateway relaie les pages et fichiers JavaScript/CSS vers Nginx **interne** ;
les API `/api/v1/*` sont relayées par le Gateway vers le KMS. Nginx refuse
tout accès à `/api/` pour éviter un second chemin applicatif.

La liste, la recherche textuelle et les filtres type/statut/favoris
s'exécutent côté serveur, avant pagination. La
consultation, la création, la modification conditionnelle avec ETag/If-Match
et la suppression logique sont prises en charge. L'interface persiste les champs génériques et les détails spécialisés des huit types. La PR #9 ajoute la création, le rattachement et le filtrage des tags.

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

## Itération 7 — classification par tags (PR #9, en cours)

- `POST /api/v1/tags` : créer un tag réutilisable (libellé unique après normalisation Unicode et comparaison insensible à la casse).
- `GET /api/v1/tags` : consulter les tags avec pagination ; `GET /api/v1/tags/{uuid}` : consulter un tag.
- `tag_ids` sur `POST /api/v1/knowledges` et `PATCH /api/v1/knowledges/{uuid}` : rattacher jusqu'à 30 tags existants, avec validation des UUID et de leur existence. La modification reste soumise à `If-Match`.
- `GET /api/v1/knowledges?tag_id={uuid}` : filtrer avant pagination, combinable aux autres filtres.
- Le frontend sous `frontend/ui-app/` permet la création d'un tag, sa sélection dans la fiche, la consultation des tags liés et le filtrage.

La collection physique `tags` est distincte ; la relation logique `knowledge_tags` est stockée comme tableau `tag_ids` dans chaque document `knowledge_items` pour garantir des écritures conditionnelles atomiques sur MongoDB autonome. Le catalogue des tags est volontairement **immuable** dans cette première version : pas de renommage ni de suppression, afin d'éviter toute référence orpheline. L'interface charge jusqu'à 100 tags ; une interface de recherche/pagination avancée est à prévoir.

Voir [itération 7 — tags et limites](docs/iterations/iteration-7-tags.md).

## Itération 7B — Technologies et versions (PR #10, dépendante de #9)

Le lot B implémente `technologies` et `technology_versions` comme collections
MongoDB de référence immuables, avec UUID, unicité des noms et versions par
technologie, catégorie facultative et date de publication facultative.

Les relations `knowledge_technologies` et `knowledge_technology_versions` du
MLD v0.2 sont physiquement stockées dans les tableaux `technology_ids` et
`technology_version_ids` des documents `knowledge_items`. Le KMS vérifie
l'existence des références et refuse la combinaison d'un lien générique avec un
lien de version du **même** produit. Les mises à jour restent atomiques et
conditionnées par `If-Match`. Le frontend sous `frontend/ui-app/` permet de
créer, choisir, afficher et filtrer les références.

Les API `GET/POST /api/v1/technologies` et `GET/POST /api/v1/technology-versions`
exposent des catalogues paginés (consultation individuelle par UUID). Les
requêtes `GET /api/v1/knowledges` acceptent aussi `technology_id` (association
générique) et `technology_version_id` (association à une version précise).
Ces filtres sont distincts, combinables et appliqués avant pagination.

Voir [spécification et limites du lot B](docs/iterations/iteration-7b-technologies.md).

## Lancement local

À la racine, avec une configuration `.env` locale existante et valide :

```bash
# Vérifie que les Dockerfiles et leurs contextes existent réellement.
python scripts/check_dockerfiles.py --compose compose.yaml --env-file .env
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml up -d --build
docker compose -f compose.yaml ps
```

Le dépôt est composé de quatre images applicatives, chacune avec son
`Dockerfile` : `frontend/ui-app/Dockerfile`, `backend/api-gateway/Dockerfile`,
`backend/knowledge-service/Dockerfile` et
`backend/collector/Dockerfile`. **Il n'existe pas de
Dockerfile à la racine : utiliser Docker Compose, et non
`docker build .`.** Le script de vérification examine les chemins
effectivement calculés par Compose avant toute construction.

Seul **le Gateway** publie le port hôte `127.0.0.1:4200` (réacheminé vers son port interne `3000`). Frontend/Nginx, KMS, MongoDB et Collector restent strictement internes à Docker. Le KMS ne publie pas Swagger directement ; effectuer les diagnostics via `docker compose exec api-kms`. Voir [la séparation DMZ/interne](docs/architecture/gateway-kms.md).

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

L'interface Angular présente ensuite un écran de connexion locale. La Gateway et le KMS
vérifient les permissions à chaque requête ; les rôles intégrés sont ADMIN,
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

## Monitoring et isolation réseau

La branche `chat` comprend le service **Collector** avec sondes frontend,
Gateway, KMS et MongoDB (via la readiness KMS), la collecte GPU NVIDIA
facultative, ainsi que des composants de présentation Angular indépendants.

```text
Navigateur --> Gateway Express --dmz--> Frontend/Nginx (pages et assets)
                       |
                       +--internal--> KMS/MongoDB/Collector (API)
```

Le réseau `dmz` est un bridge Docker géré par Compose ; le réseau
`internal` est isolé (`internal: true`). Seul le Gateway publie un
port lié à localhost. Les APIs des microservices rejettent les pairs
non autorisés grâce à des contrôles d'adresses IP internes, solution
provisoire en attendant l'authentification cryptographique interservices.

Voir [monitoring](docs/operations/monitoring.md) et
[authentification et ports](docs/operations/auth-gateway.md).

## Itération 9 — CRUD utilisateurs et stockage (PR #12)

La PR #12 ajoute un CRUD complet des comptes locaux sous `/api/v1/users`
(lecture individuelle, pagination, mise à jour des rôles et du statut,
réinitialisation du mot de passe, suppression logique). Les écritures
exigent `If-Match`, invalident les anciennes sessions et protègent
l'administrateur courant et le dernier ADMIN actif.

Le volume historique `mongodb:/data/db` est conservé ; un second volume
nommé `mongodb-configdb` est introduit pour rendre explicite le montage
`/data/configdb`. Aucun volume métier n'est effacé ni remplacé.
L'outil `scripts/persistence_check.py` inspecte les volumes en lecture seule.

**Invariant réseau :** toutes les communications entrantes, y compris vers
Angular, passent obligatoirement par Express Gateway. Cette PR déplace le
seul port publié vers la Gateway, sans changer l'URL locale 4200.

Voir [CRUD et recette](docs/iterations/iteration-9-user-crud.md),
[persistance](docs/operations/volume-persistence.md) et
[architecture Gateway](docs/architecture/gateway-kms.md).
