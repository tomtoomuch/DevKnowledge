---
title: "MongoDB — Bootstrap et smoke test"
date: "2026-11-04"
status: "STAB-01/02 validées sur Docker le 9 novembre 2026"
tags: [devknowledge, mongodb, stabilisation]
---

# Bootstrap MongoDB — STAB-01 / STAB-02

## Fonctionnement

Le fichier `backend/mongodb/init/01-create-app-user.js` est monté dans `/docker-entrypoint-initdb.d/` du conteneur `mongo:8.0`. Lors de la **première initialisation d'un volume vide**, il crée `MONGODB_APP_USERNAME` dans `MONGODB_DATABASE` avec **uniquement** le rôle `readWrite` sur cette base. Le compte administrateur est créé par le mécanisme officiel de l'image MongoDB.

**Sur un volume MongoDB déjà initialisé, ce script ne s'exécute pas.** Il ne migre pas les comptes existants, ne modifie pas les mots de passe et ne supprime aucune donnée.

## Variables d'environnement

Pour une installation neuve, copier `.env.example` vers `.env` sans committer ce dernier ; définir deux identifiants distincts et des mots de passe forts. Le nom canonique est `MONGODB_APP_USERNAME` (ancien : `MONGODB_APP_USER`). Pour un nouveau volume, `MONGODB_AUTH_SOURCE` doit être égal à `MONGODB_DATABASE`, puisque l'utilisateur y est créé.

**En développement déjà initialisé :** ne pas écraser `.env` ni changer aveuglément les mots de passe ; renommer uniquement `MONGODB_APP_USER` en `MONGODB_APP_USERNAME` si nécessaire, en conservant sa valeur. L'ancienne source d'authentification (parfois `admin`) doit être conservée tant que l'utilisateur existant n'a pas été vérifié. Modifier `.env` ne change pas les comptes stockés dans MongoDB.

La nouvelle configuration Compose échoue explicitement si une variable obligatoire est vide, au lieu de démarrer avec des identifiants incomplets.

## Test de bootstrap isolé — Git Bash

Depuis la racine du projet :

```bash
git fetch origin
git switch chat
git pull --ff-only origin chat
git status --short

docker compose -p devknowledge-bootstrap-test \
  -f backend/mongodb/tests/compose.bootstrap.yaml config --quiet

docker compose -p devknowledge-bootstrap-test \
  -f backend/mongodb/tests/compose.bootstrap.yaml \
  up --build --abort-on-container-exit --exit-code-from bootstrap-check bootstrap-check

docker compose -p devknowledge-bootstrap-test \
  -f backend/mongodb/tests/compose.bootstrap.yaml down --volumes
```

Le Compose de test utilise **une base MongoDB jetable sur `tmpfs`, un réseau interne et aucun port publié**. Les mots de passe codés en dur dans *ce fichier de test exclusivement* sont fictifs. Le test vérifie : création du compte `readWrite` sur la seule base test ; lecture/écriture d'un document ; connexion du vrai KMS avec ce compte, initialisation des index et réponse `/health/ready`.

Le message de réussite attendu est : `STAB-01 / STAB-02 : utilisateur limité, lecture/écriture et readiness KMS OK`.

**Statut : test exécuté avec succès sur Docker le 9 novembre 2026.** La commande shell du conteneur de vérification a été corrigée pour être passée comme un seul argument. Le `down --volumes` ci-dessus s'applique **uniquement au projet de test** `devknowledge-bootstrap-test`. Ne jamais l'utiliser sur le Compose de développement sans sauvegarde et décision de suppression explicite.

La campagne complète de redémarrage, refus des identifiants incorrects et
panne/reprise MongoDB se lance avec `python scripts/check_stabilization.py`.
Voir le [rapport de validation](../iterations/validation-stabilisation-2026-11-09.md).

## Avant un démarrage de développement

```bash
docker compose config --quiet
```

Ne pas partager `docker compose config` sans `--quiet` : sa sortie peut exposer les secrets du `.env`. Cette vérification syntaxique ne valide pas les comptes d'un ancien volume.

Références : [image officielle MongoDB](https://hub.docker.com/_/mongo), [variables d'environnement mongosh](https://www.mongodb.com/docs/mongodb-shell/write-scripts/env-variables/), [[../iterations/iteration-2-stabilisation|itération 2]].
