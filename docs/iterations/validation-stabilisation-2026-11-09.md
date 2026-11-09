# Stabilisation — validation du 9 novembre 2026

Branche de travail : `chat`, à partir de `8f55e0c`. Aucun changement de données
de développement, aucune fusion vers `dev` ou `main`.

## Changements livrés

- STAB-01/02 : validation réelle du bootstrap existant ; correction du test
  dont la commande multiligne était découpée par Compose avant son passage à
  `/bin/sh -ec`. La commande est désormais un unique argument de liste.
- STAB-03 : noms `GATEWAY_HOST` / `GATEWAY_PORT` cohérents dans Compose et
  le Dockerfile ; publication locale et healthcheck suivent le port configuré.
- STAB-04 : healthcheck KMS sur `/health/ready`, avec délai de requête supérieur
  au délai de sélection MongoDB. `/health` conserve son rôle de vivacité.
- STAB-05 : workflow `.github/workflows/ci.yml`, déclenché sur les push de
  `chat`, `dev`, `main`, les PR et manuellement. Jobs Gateway, KMS unitaire
  Linux/Windows et Docker. Actions référencées par SHA, permissions en lecture,
  rapports et journaux conservés 14 jours.
- STAB-07 : dépendances Python directes dans les fichiers `.in`, résolutions
  transitives exactes et empreintes dans les fichiers `.txt`. Dépendances de
  test séparées ; cible Docker `test`, image par défaut sans pytest ni httpx2.
  Le verrou npm existant reste utilisé par `npm ci`.

## Résultats locaux effectivement observés

| Vérification | Résultat |
| --- | --- |
| Gateway Jest, Node 24.16.0 Windows | 2 tests réussis ; 100 % de `app.js` |
| KMS Windows, Python 3.14.4 | 113 réussis, 4 intégrations désélectionnées ; 259/260 instructions |
| KMS Docker Linux, Python 3.14.10 | 117 réussis dont 4 intégrations ; 260/260 instructions |
| Bootstrap MongoDB corrigé | Compte limité, lecture/écriture et readiness : succès |
| Configuration Compose de développement et de test | Acceptée |
| `pip check` | Aucune dépendance cassée |
| Image KMS de production | Absence de pytest et httpx2 vérifiée |
| Test de la configuration Compose réelle | Six groupes de vérifications réussis, nettoyage réussi |

Docker Engine 29.9.2, Compose 5.6.1 ; Gateway conteneurisée Node 26.13.0.
La couverture porte sur le code KMS/Gateway exécuté, pas sur l'architecture cible.
Les exécutions distantes sont consultables dans
[GitHub Actions](https://github.com/tomtoomuch/DevKnowledge/actions/workflows/ci.yml) ;
le tableau ci-dessus décrit uniquement la campagne locale.

La première exécution distante (`42629736571`) a validé Gateway et les deux
jobs unitaires KMS, mais MongoDB a refusé de démarrer sur le noyau du runner
`ubuntu-latest` (Ubuntu 26.04). Son journal renvoie à
[SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912). Le job Docker
utilise donc explicitement `ubuntu-24.04` et consigne le noyau dans ses artefacts.
Les tests unitaires Linux restent sur `ubuntu-latest`. Le workflow a également
passé la validation statique `actionlint`.

Le script `python scripts/check_stabilization.py` utilise le Compose réel avec
une surcharge de test, un projet au nom unique, des identifiants fictifs, aucun
port publié et un volume MongoDB neuf. Il vérifie :

1. L'isolation du projet et de son stockage.
2. Le compte `readWrite`, le refus d'écriture dans une autre base, les index KMS
   et l'accès à la Gateway sur le port personnalisé 3107.
3. Un arrêt puis un deuxième démarrage conservant compte et document témoin.
4. MongoDB arrêté : `/health` retourne 200, `/health/ready` et le CRUD retournent
   503, le conteneur KMS devient `unhealthy`.
5. Le rétablissement de MongoDB : KMS à nouveau prêt et `healthy`, sans
   redémarrage du KMS ni perte du document témoin.
6. Le refus de démarrage avec un mauvais mot de passe, sans divulgation de
   celui-ci ; absence des mots de passe dans les journaux KMS.

Le rapport est écrit dans `test-results/stabilization.json` (non versionné).
Les projets et volumes de test créés pendant cette campagne ont été supprimés.

## Reproduction et maintenance

Depuis la racine :

```bash
python scripts/check_stabilization.py
```

Pour les tests KMS locaux, installer `requirements-test.txt` dans un environnement
virtuel avec `python -m pip install --require-hashes -r requirements-test.txt`.
Les commandes de la suite Docker et du bootstrap restent dans le README et le
[guide MongoDB](../operations/mongodb-bootstrap.md).

Pour actualiser les dépendances, depuis `backend/knowledge-service`, avec uv
(génération initiale effectuée avec uv 0.11.8) :

```bash
uv pip compile requirements.in --python-version 3.14 --universal --generate-hashes --output-file requirements.txt --upgrade
uv pip compile requirements-test.in --python-version 3.14 --universal --generate-hashes --output-file requirements-test.txt --upgrade
```

Le fichier de test est contraint par le verrou de production. Réexécuter ensuite
les validations Windows/Linux et Docker avant de retenir les nouveaux verrous.
Les images Docker restent référencées par tags : le verrouillage Python/npm ne
garantit pas une image système identique. Le build hors ligne n'a pas été validé.

## Suite du travail

- STAB-06 : décider puis implémenter le relais Gateway → KMS ; actuellement,
  seule la route `/health` existe côté Gateway.
- STAB-08 : sauvegarde/restauration et gestion des modifications concurrentes.
- L'authentification/RBAC et Angular restent à réaliser ; l'ADR-003 reste à valider.
- `npm audit` signale 19 alertes dans les dépendances de développement
  (3 faibles, 16 modérées) ; l'audit `--omit=dev` n'en signale aucune.
  La mise à jour de cet outillage reste à traiter séparément.
- L'environnement de développement existant n'a pas été redémarré ou migré.

Références techniques : [commande Compose](https://docs.docker.com/reference/compose-file/services/#command),
[tests Python dans GitHub Actions](https://docs.github.com/en/actions/tutorials/build-and-test-code/python).
