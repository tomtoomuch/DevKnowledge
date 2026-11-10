---
title: "DevKnowledge — persistance des volumes Docker"
date: "2026-11-10"
status: "PR #12 — revue, aucun volume de développement modifié"
tags: [docker, mongodb, volumes, sauvegarde, exploitation]
---

# Persistance des volumes Docker Compose

## État et décision

La **source de vérité** est MongoDB (base métier locale). Le conteneur
`mongodb` utilise le volume nommé logique `mongodb` sur `/data/db`,
lequel est résolu par Compose sous la forme
`<nom-projet>_mongodb`. **Le nom du projet est donc une partie de la
configuration de stockage** : démarrer depuis un autre worktree, avec
`-p` différent ou avec un autre `COMPOSE_PROJECT_NAME`, crée un nouveau
volume vide sans retrouver les données de la première instance.

Cette PR conserve le montage de données `mongodb:/data/db` et son nom
logique. Elle ajoute explicitement le volume local
`mongodb-configdb:/data/configdb` pour ne pas accumuler les volumes
anonymes créés par l'image officielle lors des recréations. Sur cette
instance MongoDB autonome, la base métier reste dans `/data/db`.
Le délai d'arrêt MongoDB est augmenté à 60 secondes pour privilégier un
arrêt propre. Le frontend, Gateway, KMS et collector ne détiennent pas de
bases persistantes propres dans ce lot ; aucun montage hôte supplémentaire
n'est nécessaire.

**Aucun volume existant n'est renommé, remplacé, migré ni supprimé
automatiquement.** Le volume complémentaire `mongodb-configdb` sera
créé lors du prochain démarrage avec la configuration mise à jour ;
cela n'efface pas le volume MongoDB métier existant.

## Vérifier le volume *effectivement monté*

Depuis Git Bash et la racine du dépôt, utiliser **le même nom de projet**
et le même environnement que pour les démarrages usuels :

```bash
python scripts/persistence_check.py --project devknowledge --env-file .env
```

Le script n'emploie que des commandes `docker compose config`,
`docker compose ps`, `docker inspect` et `docker volume ls`.
Il ne lance, ne recrée, n'arrête, ni ne supprime aucun conteneur ou volume.
La sortie affiche le nom de projet, les noms exacts attendus aux deux
montages, les volumes réellement montés et les autres volumes Compose
MongoDB observés. Elle ne reproduit pas le contenu de `.env` ou les
mots de passe.

Avant de configurer un nom différent ou de basculer depuis un autre
worktree, **noter le résultat d'audit de l'installation en service**.
Le paramètre `--project devknowledge` n'est qu'un exemple : si votre
installation utilise déjà `-p autre-projet`, conserver ce nom exact.

## Protocole d'évolution sans perte de données

1. Identifier le projet Compose original et confirmer que
   `/data/db` pointe bien sur son volume.
2. Produire une sauvegarde certifiée dans un **nouveau dossier** :
   `python scripts/mongodb_backup.py backup backups/avant-crud-users`.
3. Vérifier la sauvegarde :
   `python scripts/mongodb_backup.py restore-check backups/avant-crud-users`.
   Elle comprend les connaissances, comptes, rôles, sessions, index et
   collections de relations (s'ils existent).
4. Examiner le fichier Compose modifié :
   `docker compose -p <projet-existant> --env-file .env config --quiet`.
5. Reconstruire l'application depuis ce **même projet** :
   `docker compose -p <projet-existant> --env-file .env up -d --build`.
   Ne pas utiliser `down --volumes` ; ne pas exécuter `docker volume prune`
   pendant la migration.
6. Relancer `persistence_check.py` avec le même nom de projet et confirmer
   la même valeur `mounted./data/db` qu'avant.
7. Vérifier `/health/ready`, la présence des connaissances existantes,
   des utilisateurs et la possibilité de se reconnecter après le
   redémarrage.

**Important :** le script d'audit exige le volume nommé
`mongodb-configdb`, introduit par cette PR. Avant son adoption, inspecter
les montages via `docker compose ps`/`docker inspect` ou utiliser la
version de l'audit présente sur la branche de travail ; ne pas conclure
à une perte de données sur la seule absence du second volume.

La base de données sauvegardée contient les **hachages de mots de passe**,
les journaux métiers, sessions et informations personnelles. Les archives
BSON sont **non chiffrées** : conserver `backups/` sur un disque privé,
et prévoir un chiffrement authentifié avant toute copie externe.

## Restauration et collision de projets

La restauration est toujours faite dans un **nouveau volume** par
`scripts/mongodb_backup.py`. L'activation se fait explicitement à
travers `compose.recovery.yaml` et `RESTORED_MONGODB_VOLUME`, sans
écraser le volume métier d'origine. Le composant `mongodb-configdb`
reste distinct.

Un affichage d'une base « vide » après changement de worktree ou de
`-p` **n'implique pas** la disparition de l'ancien volume. Ne jamais
forcer un bootstrap d'administrateur sur un projet dont on n'a pas vérifié
le volume `/data/db`. Utiliser l'audit pour identifier les volumes
préexistants, puis réutiliser le nom de projet d'origine ou activer
volontairement une restauration isolée.

**Qualification automatisée :** le script
`scripts/check_stabilization.py` exécute déjà les tests de redémarrage,
panne/reprise, sauvegarde et restauration dans un projet et des volumes
**jetables**. Les tests `scripts/test_persistence_check.py`
vérifient le mode lecture seule, la détection d'un montage erroné et
l'absence de création de volume par l'audit.
