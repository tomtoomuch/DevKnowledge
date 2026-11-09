---
title: "KMS — CRUD générique des connaissances"
date: "2026-11-02"
tags: [devknowledge, kms, api, mongodb, tests]
---

# KMS — CRUD générique des connaissances

> STAB-08 : PATCH et DELETE exigent maintenant `If-Match`. Voir [[knowledge-concurrency]] avant d’utiliser les exemples historiques d’écriture ci-dessous.

> Mise à jour STAB-06 : le CRUD est maintenant accessible via la Gateway sur
> `127.0.0.1:3000`. Les exemples historiques ci-dessous utilisant le port 8000
> nécessitent `compose.debug.yaml`. Voir [[gateway-kms]] pour l'accès actuel.

Cette première itération implémente la collection `knowledge_items` du [[DevKnowledge_MLD_3NF_v0.2|MLD v0.2]]. Elle couvre les connaissances génériques, sans leurs spécialisations, sans authentification, sans historique et sans RAG.

## Audit du socle

La branche de travail `feature/kms-knowledge-crud` part de `dev`, commit `4c7d412`. Avant cette itération, le service contenait une application FastAPI dans `app/main.py`, un client MongoDB asynchrone partagé pendant le cycle de vie de l'application, `/health`, `/health/ready` et des tests de santé. Il ne contenait pas de CRUD métier.

Le dépôt utilise Docker Compose, MongoDB `8.0`, une Gateway Node.js/Express sur le port 3000 et un KMS Python/FastAPI sur le port 8000. MongoDB n'est pas publié sur l'hôte ; les ports de la Gateway et du KMS sont liés à `127.0.0.1`. La Gateway actuelle fournit des contrôles de santé, mais ne relaie pas encore le CRUD. Les routes décrites ici sont donc celles du KMS ; un relais Gateway reste à ajouter lors d'une itération dédiée. La cible demeure un point d'entrée applicatif unique par la Gateway.

Versions constatées dans l'environnement Python local pendant l'audit : Python `3.14.4`, FastAPI `0.162.0`, Pydantic `2.14.1`, Starlette `1.10.0`, PyMongo `4.19.0`, Uvicorn `0.54.0`, pytest `9.2.0`, HTTPX2 `2.16.0`. Ces versions observées ne constituent pas un verrouillage des dépendances ; le Dockerfile et `requirements.txt` définissent l'environnement de construction. `pytest-cov` était déclaré mais absent de cet environnement : il a été installé pour mesurer la couverture. La dépendance existante `httpx2` est conservée : le code de Starlette `1.10.0` la privilégie pour `TestClient` et déprécie le repli vers `httpx`. Les tests d'intégration utilisent également `httpx2`.

Pydantic v2 est déclaré explicitement pour les modèles employés. Le minimum PyMongo passe de `4.10` à `4.13`, version où l'API asynchrone employée est stable ([notes de version officielles](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/release-notes/#what-s-new-in-4-13)). La Gateway configure historiquement `HOST`/`PORT` dans Compose alors que son code lit `GATEWAY_HOST`/`GATEWAY_PORT` ; ses valeurs par défaut produisent aujourd'hui les mêmes écoute et port. Cette incohérence sans effet sur le CRUD n'est pas corrigée dans cette itération.

Le MLD est un modèle logique candidat à la 3NF. Il autorise une transposition MongoDB et laisse ouverts les statuts métier et les niveaux de difficulté. Les adaptations provisoires de cette itération sont détaillées ci-dessous ; le MLD de référence n'est pas modifié.

## Responsabilités du code

- **Routes** : contrat HTTP, paramètres, codes de réponse et injection des dépendances.
- **Schemas** : validation Pydantic des entrées et sorties, champs autorisés et conversion JSON.
- **Services** : génération de l'identifiant et des dates, identité du créateur, règles de modification et de suppression.
- **Repositories** : accès à `knowledge_items`, filtres MongoDB, tri, pagination et opérations atomiques sur un document.
- **DB** : configuration, client asynchrone partagé, initialisation des index et dépendances d'accès à la base.

Le service accepte un repository injectable, permettant les tests unitaires sans MongoDB. La connexion MongoDB est créée au démarrage puis fermée à l'arrêt ; aucune connexion n'est créée par requête.

## Représentation et écarts provisoires au MLD

### Identifiants et dates

Le serveur génère un UUID v4 pour chaque connaissance. Sa représentation canonique sous forme de chaîne, par exemple `80c2121e-55c9-4b2b-95df-069a1c44d81c`, est stockée dans `_id`. L'unicité repose sur l'index `_id` natif de MongoDB. Le repository transforme `_id` en `knowledge_id` pour le domaine et les réponses : aucun champ `knowledge_id` redondant n'est stocké. Pydantic valide les UUID dans les chemins et les modèles de sortie. Les clients n'envoient jamais l'identifiant à la création.

Les dates sont générées côté serveur en UTC avec fuseau. MongoDB les stocke comme dates BSON, à la précision de la milliseconde ; la configuration `tz_aware` du client assure une lecture avec fuseau. Les réponses JSON contiennent des dates ISO 8601 avec indication UTC. Il ne faut pas attendre la conservation de microsecondes au-delà de la précision BSON.

### Type de connaissance

Le référentiel `knowledge_types` n'est pas créé dans cette itération. Un champ physique et public `knowledge_type` contient obligatoirement un de ces huit codes :

| Code | Type logique |
| --- | --- |
| `CODE_SNIPPET` | Extrait de code |
| `TERMINAL_COMMAND` | Commande terminal |
| `TECHNICAL_PROCEDURE` | Procédure technique |
| `COURSE_NOTE` | Note de cours |
| `BUG_FIX` | Correction de problème |
| `DOCUMENTATION_RESOURCE` | Ressource documentaire |
| `BEST_PRACTICE` | Bonne pratique |
| `COMPLIANCE_STANDARD` | Norme de conformité |

Ce code est un discriminant provisoire validé, pas une fausse clé étrangère. Lors de l'implémentation du référentiel, chaque code unique pourra être associé à un `knowledge_type_id` réel. Aucun UUID de référentiel arbitraire n'est enregistré. La spécialisation correspondante est reportée ; le MLD autorise déjà une connaissance générique sans ligne spécialisée.

### Créateur et validation

Le MLD définit `created_by_user_id` comme une FK obligatoire vers `users`. Tant que les utilisateurs et l'authentification ne sont pas implémentés, ce champ est provisoirement nullable. Le service utilise une abstraction `RequesterIdentity` injectable. Par défaut, aucune identité n'est attribuée ; aucun UUID d'utilisateur fictif, en-tête libre ou champ fourni par le client ne vaut authentification.

L'authentification future devra renseigner cette abstraction depuis une identité effectivement vérifiée, puis traiter explicitement les documents historiques sans auteur. Cette abstraction ne constitue ni un contrôle d'accès ni un système RBAC.

`validated_at` est présent en lecture, initialement `null`, et ne peut pas être écrit par le client. Changer le texte `status` ne constitue pas une validation authentifiée et ne renseigne pas cette date. Un processus de validation métier et les permissions correspondantes seront définis ultérieurement.

### Suppression logique

`deleted_at` est une extension demandée pour cette itération, absente du MLD v0.2. Il vaut `null` à la création. La suppression renseigne cette date sans effacer le document. Toutes les lectures, listes et modifications applicatives filtrent les documents supprimés. La suppression utilise une opération atomique avec le critère `deleted_at: null` : une seconde suppression retourne 404.

### Index

Outre l'index unique `_id` natif, un index composé couvre le filtre des connaissances actives et leur tri :

```text
deleted_at ASC, created_at DESC, _id ASC
```

L'initialisation est idempotente et non destructive. Aucun index pour les futures spécialisations, l'historique, les utilisateurs ou le RAG n'est créé. Les filtres facultatifs de type et de statut n'ajoutent pas d'index prématuré ; leur indexation pourra être réévaluée selon les volumes et les requêtes réels.

## Contrat HTTP

Préfixe : `/api/v1/knowledges`.

| Méthode | Route | Réussite |
| --- | --- | --- |
| POST | `/api/v1/knowledges` | 201, connaissance créée |
| GET | `/api/v1/knowledges/{knowledge_id}` | 200, connaissance |
| GET | `/api/v1/knowledges` | 200, page de connaissances |
| PATCH | `/api/v1/knowledges/{knowledge_id}` | 200, connaissance modifiée |
| DELETE | `/api/v1/knowledges/{knowledge_id}` | 204, corps vide |

### Entrées et validations

| Champ | Création | Modification |
| --- | --- | --- |
| `knowledge_type` | Obligatoire, un des huit codes exacts | Facultatif, non nullable |
| `title` | Obligatoire, non vide, 150 caractères maximum | Facultatif, non nullable |
| `content` | Obligatoire, non vide | Facultatif, non nullable |
| `description` | Facultatif, nullable | Facultatif, `null` efface la valeur |
| `language_code` | Facultatif, nullable, 10 caractères maximum | Facultatif, `null` efface la valeur |
| `difficulty_level` | Facultatif, nullable, 30 caractères maximum | Facultatif, `null` efface la valeur |
| `status` | Facultatif, non vide, 30 caractères maximum ; défaut `DRAFT` | Facultatif, non nullable |
| `is_favorite` | Booléen, défaut `false` | Facultatif, non nullable |

`status` reste une chaîne libre bornée : le MLD ne définit pas encore de cycle de vie ou d'énumération de statuts. `difficulty_level` reste également un texte borné ; aucun référentiel de difficulté n'est inventé.

Les champs inconnus sont refusés. Cela inclut les champs internes `_id`, `knowledge_id`, `knowledge_type_id`, `created_by_user_id`, `created_at`, `updated_at`, `validated_at` et `deleted_at`. Un PATCH vide est invalide. Seuls les champs explicitement présents dans un PATCH sont modifiés ; les autres sont conservés. Le serveur actualise `updated_at`.

Exemple de création :

```json
{
  "knowledge_type": "COURSE_NOTE",
  "title": "Index composés MongoDB",
  "content": "Un index composé suit l'ordre de ses champs.",
  "language_code": "fr",
  "is_favorite": true
}
```

Exemple de réponse, avec dates et UUID illustratifs :

```json
{
  "knowledge_id": "80c2121e-55c9-4b2b-95df-069a1c44d81c",
  "knowledge_type": "COURSE_NOTE",
  "title": "Index composés MongoDB",
  "description": null,
  "content": "Un index composé suit l'ordre de ses champs.",
  "language_code": "fr",
  "difficulty_level": null,
  "status": "DRAFT",
  "created_at": "2026-11-02T12:00:00Z",
  "updated_at": "2026-11-02T12:00:00Z",
  "validated_at": null,
  "created_by_user_id": null,
  "is_favorite": true,
  "deleted_at": null
}
```

Exemple de PATCH : `{"description": null, "is_favorite": false}`.

### Liste et filtres

`GET /api/v1/knowledges?skip=0&limit=20&knowledge_type=COURSE_NOTE&status=DRAFT`

- `skip` : entier supérieur ou égal à 0, défaut 0.
- `limit` : entier de 1 à 100, défaut 20.
- `knowledge_type` : facultatif, même validation des huit codes que pour la création.
- `status` : facultatif, chaîne non vide de 30 caractères maximum.

La réponse est de la forme `{"items": [], "total": 0, "skip": 0, "limit": 20}`. `total` compte les connaissances actives correspondant aux filtres, avant pagination. Le tri est déterministe : `created_at` décroissant, puis UUID canonique croissant. Des écritures concurrentes peuvent naturellement modifier les résultats entre deux requêtes ; cette pagination par décalage n'est pas un instantané transactionnel.

### Erreurs et disponibilité

| Code | Signification |
| --- | --- |
| 404 | UUID valide inconnu, connaissance supprimée ou seconde suppression |
| 422 | Entrée, UUID de chemin ou paramètre invalide ; champ interdit ; PATCH vide |
| 503 | MongoDB indisponible ou non initialisé |

Les erreurs MongoDB sont traduites en réponse générique sans trace, URI, identifiant de connexion ni secret. Les journaux techniques ne consignent que le contexte de l'opération et la classe d'exception, jamais le contenu de l'exception pouvant porter des données sensibles.

`/health` reste un contrôle de vie du service ; `/health/ready` vérifie l'accès à MongoDB. Un échec de connexion au démarrage conserve la politique existante de tentatives bornées ; il peut empêcher le démarrage. Une indisponibilité pendant une requête métier produit une réponse 503.

## Lancement et vérification manuelle

Depuis la racine du dépôt, avec les variables d'environnement existantes et les images/dépendances préparées :

```powershell
docker compose up -d --build
docker compose ps
```

Conserver les identifiants existants ; cette itération ne crée ni ne modifie les mots de passe MongoDB. Après installation et préparation des images, l'exécution ne dépend d'aucun service cloud. Une construction sans cache ou l'installation initiale des dépendances peut nécessiter un accès aux registres de paquets et d'images.

La documentation OpenAPI du KMS est disponible sur `http://127.0.0.1:8000/docs` et le schéma sur `http://127.0.0.1:8000/openapi.json`. Vérifier les cinq opérations, leurs modèles et leurs réponses dans Swagger UI.

Parcours manuel conseillé : créer une connaissance avec l'exemple ci-dessus, conserver son `knowledge_id`, la relire, la retrouver avec les filtres, modifier uniquement son titre, puis la supprimer. Vérifier ensuite une lecture 404, son absence de la liste et une seconde suppression 404. Tester également un UUID mal formé et l'envoi de `created_by_user_id`, qui doivent produire 422. L'inspection de la base doit retrouver le document supprimé avec son `deleted_at` renseigné.

Pour un lancement Python hors Docker, depuis `backend/knowledge-service`, installer `requirements.txt`, fournir les variables MongoDB existantes puis lancer `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. Le serveur MongoDB doit être accessible depuis ce processus : le nom Docker `mongodb` n'est normalement résolu que sur le réseau Compose. Ne pas publier MongoDB sur une interface publique pour ce lancement.

## Tests et couverture

Depuis `backend/knowledge-service`, avec l'environnement Python du projet :

```powershell
python -m pip install -r requirements.txt
python -m pytest -m 'not integration'
```

Les tests unitaires injectent des repositories ou clients contrôlés ; ils ne nécessitent aucune base MongoDB disponible. Ils couvrent validation, contrats HTTP, pagination, filtres, mises à jour partielles, suppressions logiques, erreurs MongoDB, UUID, dates et contrôles de santé.

Le parcours reproductible recommandé utilise un Compose distinct, un MongoDB en mémoire (`tmpfs`), un réseau interne sans port publié et une image de test distincte. Depuis la racine du dépôt :

```powershell
docker compose -p devknowledge-kms-crud-test -f backend/knowledge-service/tests/compose.integration.yaml up --build --abort-on-container-exit --exit-code-from kms-tests kms-tests
docker compose -p devknowledge-kms-crud-test -f backend/knowledge-service/tests/compose.integration.yaml down --volumes
```

Ce Compose exécute toute la suite, y compris le CRUD HTTP sur le vrai processus Uvicorn et les intégrations repository. Ses identifiants publics `kms_test_only` sont exclusivement ceux de son serveur jetable ; ils n'ont aucun lien avec les secrets du développement. Aucun volume existant n'est monté. Le test HTTP déployé n'accepte que `KMS_TEST_HTTP_URL=http://api-kms-test:8000`, afin de refuser une URL de développement avant toute écriture. Il est ignoré hors de cet environnement si la variable est absente.

Pour les trois autres tests marqués `integration`, fournir `KMS_TEST_MONGODB_URI` vers un serveur dédié aux tests, puis lancer depuis `backend/knowledge-service` :

```powershell
python -m pytest -m integration
```

Chaque test repository/ASGI crée une base isolée dont le nom commence par `devknowledge_test_` et utilise un suffixe généré, puis nettoie uniquement cette base dans la même boucle asynchrone. Le service Uvicorn de test possède sa propre base `devknowledge_test_compose`, détruite avec le serveur jetable. Ne jamais utiliser les collections de développement comme fixtures. L'utilisateur MongoDB de test doit pouvoir créer, indexer et supprimer cette base temporaire. Les véritables identifiants sont transmis par l'environnement et ne doivent pas être versionnés. En l'absence de serveur/URI de test, les intégrations concernées sont ignorées explicitement ; cela ne vaut pas validation de la persistance réelle.

Sous le sandbox Windows de Codex, l'initialisation des sockets locales d'`asyncio` peut être bloquée. Les tests ont été exécutés hors sandbox et dans Docker ; ce blocage n'est pas une dépendance à MongoDB des tests unitaires.

La configuration pytest conserve `pytest-cov`, avec rapport terminal et rapport HTML. Les résultats mesurés, la couverture obtenue et les éventuelles validations empêchées par l'environnement figurent dans le rapport de livraison ; aucun pourcentage n'est supposé dans cette documentation.

## Limites et suites

Les spécialisations des huit types, le référentiel `knowledge_types`, les utilisateurs et rôles, l'authentification, les permissions par document, le proxy CRUD de la Gateway, `knowledge_versions`, le RAG, les compétences RNCP et les preuves de certification sont reportés. La suppression est logique uniquement : aucune restauration ou purge physique n'est exposée. Les mises à jour concurrentes ne disposent pas encore de contrôle de version optimiste.

Ce service local sans authentification n'est pas destiné à une exposition publique. L'injection d'une identité future et le référentiel des types devront respecter les données provisoires documentées ici, sans considérer les champs fournis par le client comme une identité vérifiée.
