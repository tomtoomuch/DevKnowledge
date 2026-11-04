---
title: "DevKnowledge — Itération 2 : stabilisation du socle"
date: "2026-11-04"
status: "Plan proposé — à exécuter ensemble"
tags: [devknowledge, stabilisation, qualite, tests, docker, ci]
---

# Itération 2 — Stabilisation du socle

> **Statut : préparation.** Ce document décrit les activités et leurs critères d'acceptation ; les corrections et validations ne sont pas encore exécutées. Source de l'état initial : [[point-avancement-2026-11-04]].

## Objectif

Disposer d'un socle **reproductible, testable et documenté** (Gateway Express, KMS FastAPI, MongoDB 8, Docker Compose), sans modifier prématurément le MLD candidat 3NF ni ajouter de nouveaux services métier. La stabilisation se fait sur `chat` avec revue conjointe.

## Périmètre

**Inclus :** configuration, démarrage neuf contrôlé, provisionnement MongoDB, readiness, vérifications d'accès locaux, automatisation des tests, CI, reproductibilité, documentation d'exploitation et tests de non-régression.

**À arbitrer :** intégrer dès ce cycle le relais minimal Gateway → KMS ou le garder pour un incrément immédiatement suivant. Ne pas annoncer de point d'entrée unique tant que le relais n'existe pas.

**Exclus :** Angular, utilisateurs et RBAC, huit spécialisations, RNCP, RAG, embeddings, MCP, MLOps, refonte du MLD et migration de données existantes.

## Préparation commune : état initial et sécurité des données

- [ ] Confirmer le SHA de `chat` et l'état de la copie locale (`git status`).
- [ ] Sauvegarder les connaissances existantes avant toute intervention sur le Compose de développement ; vérifier la restauration sur un espace distinct lorsque la procédure existe.
- [ ] Distinguer le Compose de développement `compose.yaml` et le Compose jetable `backend/knowledge-service/tests/compose.integration.yaml`.
- [ ] Ne jamais effacer de volume de développement pour reproduire une installation neuve : utiliser un **nom de projet Compose dédié**, des volumes propres et des identifiants de test.
- [ ] Garder les secrets dans `.env` non suivi ; aucune valeur sensible dans les logs, captures ou commits.

## Lots proposés

### Lot A — Configuration et provisionnement (STAB-01, STAB-02, STAB-03)

- [ ] Choisir `MONGODB_APP_USERNAME` comme nom canonique (ou modifier les deux fichiers de façon cohérente) et mettre à jour `.env.example` avec des commentaires non sensibles.
- [ ] Documenter et automatiser la création du compte applicatif MongoDB, limité à la base métier, sans exécuter l'application en root.
- [ ] Vérifier la configuration de `MONGODB_AUTH_SOURCE` pour le compte réellement créé.
- [ ] Aligner `GATEWAY_HOST` / `GATEWAY_PORT` entre Compose et Express.
- [ ] Tester démarrage neuf, deuxième démarrage idempotent et erreur volontaire d'identifiants sans fuite de secret.

**Acceptation :** une installation depuis un volume jetable vierge fonctionne ; le compte métier a uniquement les permissions nécessaires ; les ports personnalisés et la configuration déclarée sont respectés.

### Lot B — Santé et robustesse (STAB-04)

- [ ] Réserver `/health` à la vivacité et `/health/ready` à la dépendance MongoDB.
- [ ] Adapter le healthcheck Compose du KMS à `/health/ready`.
- [ ] Vérifier les états lors du démarrage, d'une coupure de base, puis d'un rétablissement.
- [ ] Vérifier les codes d'erreur HTTP (422, 404, 503) et l'absence de secrets dans les journaux.
- [ ] Documenter le rôle exact de `depends_on` et la différence entre santé de conteneur et disponibilité métier.

**Acceptation :** la santé Docker n'indique pas à tort un KMS prêt pendant une indisponibilité MongoDB, et la récupération est observable.

### Lot C — Tests, CI et reproductibilité (STAB-05, STAB-07)

- [ ] Rejouer `npm test` dans `backend/api-gateway` et enregistrer la couverture réelle.
- [ ] Rejouer `python -m pytest -m "not integration"` dans `backend/knowledge-service`.
- [ ] Rejouer le Compose d'intégration jetable avec `--exit-code-from kms-tests` ; enregistrer succès, échecs, versions et couverture.
- [ ] Ajouter un workflow GitHub Actions avec jobs Gateway et KMS, et un job d'intégration MongoDB si supporté par le runner.
- [ ] Ajouter des tests de configuration et de démarrage neuf ; envisager lint et contrôle de dépendances.
- [ ] Définir un verrouillage reproductible des dépendances et distinguer runtime/test sans rompre les contraintes d'exécution locale.

**Acceptation :** jobs reproductibles, statut visible sur GitHub, aucun test historique présenté comme une mesure actuelle ; les causes des éventuels échecs sont conservées.

### Lot D — Frontière API et exploitation (STAB-06, STAB-08)

- [ ] Arbitrer et documenter la stratégie de proxy Gateway → KMS, sa gestion des erreurs, timeouts et en-têtes, et ses futurs contrôles d'identité.
- [ ] Si implémenté pendant cette itération, tester les cinq opérations via la Gateway et vérifier les statuts/erreurs sans modifier les contrats KMS.
- [ ] Documenter les limites actuelles : KMS publié en local, absence d'authentification et de RBAC.
- [ ] Définir les exigences minimales de sauvegarde, restauration et gestion des mises à jour concurrentes.
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
python -m pip install -r requirements.txt
python -m pytest -m "not integration"
cd ../..
```

Suite d'intégration **sur l'environnement jetable uniquement** :

```bash
docker compose -p devknowledge-kms-crud-test -f backend/knowledge-service/tests/compose.integration.yaml up --build --abort-on-container-exit --exit-code-from kms-tests kms-tests
docker compose -p devknowledge-kms-crud-test -f backend/knowledge-service/tests/compose.integration.yaml down --volumes
```

**Attention :** le `down --volumes` ci-dessus vise uniquement `devknowledge-kms-crud-test`. Il ne doit jamais être recopié vers la pile de développement sans une décision explicite de suppression de données.

## Journal de validation à remplir pendant l'itération

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
