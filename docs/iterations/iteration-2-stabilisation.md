---
title: "DevKnowledge — Itération 2 : stabilisation du socle"
date: "2026-11-04"
status: "STAB-01 à 08 implémentées ; revue de sortie ouverte"
tags: [devknowledge, stabilisation, qualite, tests, docker, ci]
---

# Itération 2 — Stabilisation du socle

> **Mise à jour du 9 novembre :** bootstrap, configuration Gateway, readiness et panne/reprise validés localement. CI versionnée, dépendances Python verrouillées et séparées. Voir [[validation-stabilisation-2026-11-09]]. STAB-06 est maintenant implémenté et testé : [[../architecture/gateway-kms]]. STAB-08 ajoute les sauvegardes/restaurations isolées et les écritures conditionnelles. La revue commune de sortie reste ouverte. Les sections datées du 4 novembre ci-dessous décrivent le point de départ.

## Objectif

Disposer d'un socle **reproductible, testable et documenté** (Gateway Express, KMS FastAPI, MongoDB 8, Docker Compose), sans modifier prématurément le MLD candidat 3NF ni ajouter de nouveaux services métier. La stabilisation se fait sur `chat` avec revue conjointe.

## Périmètre

**Inclus :** configuration, démarrage neuf contrôlé, provisionnement MongoDB, readiness, vérifications d'accès locaux, automatisation des tests, CI, reproductibilité, documentation d'exploitation et tests de non-régression.

**STAB-06 retenu :** relais minimal Gateway → KMS livré après fusion de la stabilisation dans `dev` (PR #2). La Gateway est le seul port publié par défaut ; les accès KMS directs sont réservés au mode de diagnostic explicite.

**Exclus :** Angular, utilisateurs et RBAC, huit spécialisations, RNCP, RAG, embeddings, MCP, MLOps, refonte du MLD et migration de données existantes.

## Travaux déposés — 4 novembre 2026

- **STAB-01 :** `.env.example` et `compose.yaml` utilisent maintenant `MONGODB_APP_USERNAME`, avec contrôle des variables obligatoires.
- **STAB-02 :** le script `backend/mongodb/init/01-create-app-user.js` crée le compte `readWrite` sur un volume vierge.
- **Test d'acceptation préparé :** `backend/mongodb/tests/compose.bootstrap.yaml` (MongoDB jetable sur `tmpfs`, vérification du rôle, lecture/écriture, KMS `/health/ready`).
- **Vérification actuelle :** 9 contrôles statiques ciblés réussis sur le code récupéré de GitHub.
- **Reste à faire :** exécution Docker et revue de l'environnement existant ; les cases d'acceptation restent ouvertes.
- **Important :** les scripts d'initialisation ne s'appliquent pas rétroactivement aux volumes existants.

Guide : [[../operations/mongodb-bootstrap]].

## Préparation commune : état initial et sécurité des données

- [x] Confirmer le SHA de `chat` et l'état de la copie locale (`git status`).
- [ ] Sauvegarder les connaissances existantes avant toute intervention sur le Compose de développement ; vérifier la restauration sur un espace distinct lorsque la procédure existe.
- [ ] Distinguer le Compose de développement `compose.yaml` et le Compose jetable `backend/knowledge-service/tests/compose.integration.yaml`.
- [ ] Ne jamais effacer de volume de développement pour reproduire une installation neuve : utiliser un **nom de projet Compose dédié**, des volumes propres et des identifiants de test.
- [ ] Garder les secrets dans `.env` non suivi ; aucune valeur sensible dans les logs, captures ou commits.

## Lots proposés

### Lot A — Configuration et provisionnement (STAB-01, STAB-02, STAB-03)

- [x] Choisir `MONGODB_APP_USERNAME` comme nom canonique (ou modifier les deux fichiers de façon cohérente) et mettre à jour `.env.example` avec des commentaires non sensibles.
- [x] Documenter et automatiser la création du compte applicatif MongoDB, limité à la base métier, sans exécuter l'application en root.
- [x] Vérifier la configuration de `MONGODB_AUTH_SOURCE` pour le compte réellement créé.
- [x] Aligner `GATEWAY_HOST` / `GATEWAY_PORT` entre Compose et Express.
- [x] Tester démarrage neuf, deuxième démarrage idempotent et erreur volontaire d'identifiants sans fuite de secret.

**Acceptation :** une installation depuis un volume jetable vierge fonctionne ; le compte métier a uniquement les permissions nécessaires ; les ports personnalisés et la configuration déclarée sont respectés.

### Lot B — Santé et robustesse (STAB-04)

- [x] Réserver `/health` à la vivacité et `/health/ready` à la dépendance MongoDB.
- [x] Adapter le healthcheck Compose du KMS à `/health/ready`.
- [x] Vérifier les états lors du démarrage, d'une coupure de base, puis d'un rétablissement.
- [x] Vérifier les codes d'erreur HTTP (422, 404, 503) et l'absence de secrets dans les journaux.
- [x] Documenter le rôle exact de `depends_on` et la différence entre santé de conteneur et disponibilité métier.

**Acceptation :** la santé Docker n'indique pas à tort un KMS prêt pendant une indisponibilité MongoDB, et la récupération est observable.

### Lot C — Tests, CI et reproductibilité (STAB-05, STAB-07)

- [x] Rejouer `npm test` dans `backend/api-gateway` et enregistrer la couverture réelle.
- [x] Rejouer `python -m pytest -m "not integration"` dans `backend/knowledge-service`.
- [x] Rejouer le Compose d'intégration jetable avec `--exit-code-from kms-tests` ; enregistrer succès, échecs, versions et couverture.
- [x] Ajouter un workflow GitHub Actions avec jobs Gateway et KMS, et un job d'intégration MongoDB si supporté par le runner.
- [x] Ajouter des tests de configuration et de démarrage neuf ; envisager lint et contrôle de dépendances.
- [x] Définir un verrouillage reproductible des dépendances et distinguer runtime/test sans rompre les contraintes d'exécution locale.

**Acceptation :** jobs reproductibles, statut visible sur GitHub, aucun test historique présenté comme une mesure actuelle ; les causes des éventuels échecs sont conservées.

### Lot D — Frontière API et exploitation (STAB-06, STAB-08)

- [x] Arbitrer et documenter la stratégie de proxy Gateway → KMS, sa gestion des erreurs, timeouts et en-têtes, et ses futurs contrôles d'identité.
- [x] Si implémenté pendant cette itération, tester les cinq opérations via la Gateway et vérifier les statuts/erreurs sans modifier les contrats KMS.
- [x] Documenter les limites actuelles : KMS interne par défaut, diagnostic local optionnel, absence d'authentification et de RBAC.
- [x] Implémenter et tester sauvegarde/restauration isolée et mises à jour conditionnelles ; procédures dans [[../operations/backup-restore]] et [[../architecture/knowledge-concurrency]].
- [ ] Vérifier la préparation à l'usage hors ligne **après** construction/téléchargement des dépendances ; ne pas revendiquer un build hors ligne sans test.

**Acceptation :** la frontière API et les limites de sécurité ne sont pas ambiguës ; les choix reportés sont explicitement consignés.

## Ordre des séances de stabilisation

| Séance | Travail prioritaire | Critère de fin |
| --- | --- | --- |
| S1 | Diagnostic de configuration et démarrage vierge isolé | STAB-01/02/03 documentés et reproduits |
| S2 | Corrections Compose et MongoDB | Démarrage idempotent + compte applicatif limité |
| S3 | Readiness, pannes et retour à la normale | États et réponses contrôlés |
| S4 | Tests et GitHub Actions | Suites rejouées ; premiers jobs verts |
| S5 | Gateway, exploitation et revue de sortie | Décisions et documentation finalisées |

L'ordre peut être adapté aux observations ; une séance n'a pas de durée prédéterminée.

## Commandes de vérification (Git Bash)

Depuis la racine du dépôt :

```bash
git fetch origin
git switch chat
git status
docker compose config --quiet
docker compose ps
```

Tests Gateway :

```bash
cd backend/api-gateway
npm ci
npm test
cd ../..
```

Tests unitaires KMS :

```bash
cd backend/knowledge-service
python -m pip install --require-hashes -r requirements-test.txt
python -m pytest -m "not integration"
cd ../..
```

Suite d'intégration **sur l'environnement jetable uniquement** :

```bash
docker compose -p devknowledge-kms-crud-test -f backend/knowledge-service/tests/compose.integration.yaml up --build --abort-on-container-exit --exit-code-from kms-tests kms-tests
docker compose -p devknowledge-kms-crud-test -f backend/knowledge-service/tests/compose.integration.yaml down --volumes
```

**Attention :** le `down --volumes` ci-dessus vise uniquement `devknowledge-kms-crud-test`. Il ne doit jamais être recopié vers la pile de développement sans une décision explicite de suppression de données.

## Journal initial du 4 novembre (historique)

Résultats datés et environnement : [[validation-stabilisation-2026-11-09]].

| Vérification | Date | Commit | Environnement / version | Résultat / preuve |
| --- | --- | --- | --- | --- |
| Configuration Compose | À faire | À renseigner | À renseigner | À renseigner |
| Premier démarrage isolé | À faire | À renseigner | À renseigner | À renseigner |
| Compte applicatif MongoDB | À faire | À renseigner | À renseigner | À renseigner |
| Gateway Jest | À faire | À renseigner | À renseigner | À renseigner |
| KMS pytest unitaire | À faire | À renseigner | À renseigner | À renseigner |
| KMS intégration Docker | À faire | À renseigner | À renseigner | À renseigner |
| Readiness / panne MongoDB | À faire | À renseigner | À renseigner | À renseigner |
| CI GitHub Actions | À faire | À renseigner | À renseigner | À renseigner |

## Fin de phase

La phase ne sera clôturée qu'après revue commune des résultats, régressions, conditions d'installation et décisions reportées. Aucune fusion vers `dev` ou `main` n'est incluse par défaut.
