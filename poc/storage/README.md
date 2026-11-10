# DevKnowledge — SQL Server 2025 / PostgreSQL 17 — DOC-38

Ce POC utilise **des images Docker officielles** et des jeux de données
**totalement fictifs** pour valider un domaine relationnel inspiré du MLD
RNCP v0.2. Les moteurs ne sont pas exposés sur l'hôte et sont exécutés
dans un projet Compose **indépendant**, sur un réseau `internal: true`.

| Moteur | Image | Client SQL |
|---|---|---|
| SQL Server 2025 | `mcr.microsoft.com/mssql/server:2025-latest` | `sqlcmd` et ODBC Driver 18 |
| PostgreSQL 17 | `postgres:17` | `psql` et psycopg 3 |

Pour chaque moteur, `run.py` crée des identifiants temporaires et un nom
de projet aléatoire. **Il ne référence aucun volume ou `.env` de DevKnowledge.**

## Exécuter les tests

Depuis la racine du dépôt et avec Docker Desktop déjà démarré :

```bash
python poc/storage/run.py --engine postgres --extended --rows 1500
python poc/storage/run.py --engine sqlserver --extended --rows 1500
```

Sans `--extended`, seul le POC de contraintes relationnelles/migration
et sauvegarde est joué ; avec `--extended` :

1. Création du schéma RNCP simplifié (6 tables) : référentiel, blocs,
   compétences, connaissances, preuves, liens connaissances/compétences.
2. Application de la migration **v2 idempotente** (réappliquée et vérifiée).
3. Tests FK, UNIQUE, validité JSON, jointures RNCP, ROLLBACK, écriture
   optimiste par révision et restauration dans une autre base.
4. Construction d'une image Python 3.12 de **FastAPI + SQLAlchemy Core**,
   utilisant le vrai driver Microsoft ODBC 18 ou psycopg 3 selon le moteur.
5. Insertion en lots de 1 500 connaissances fictives, de leurs 1 500 preuves
   et de leurs 1 500 correspondances RNCP, dans une transaction SQL.
6. Requêtes FastAPI de santé, consultation des preuves liées à une
   compétence et création/modification avec `If-Match` : 200, 201, 428, 412.
   Les demandes HTTP sont envoyées par `TestClient` ASGI **dans** le
   conteneur client ; ce n'est pas un service HTTP publié sur l'hôte.
7. Durées d'insertion et médiane/p95 sur requêtes HTTP ainsi que captures
   de mémoire/CPU du conteneur de base via `docker stats`.
8. Validation de backup et restauration, puis nettoyage exclusif du
   projet Compose temporaire ; résultats JSON sous
   `test-results/storage-poc/` et artefacts de GitHub Actions.

Le build du conteneur client récupère ses paquets via le réseau Docker
pendant la **préparation**. Le conteneur exécuté n'a pas de route
Internet. Les bibliothèques sont fixées par version mais pas encore par
digest/hashes. Une qualification de **build** totalement hors ligne
demande du travail supplémentaire.

## Limites et interprétation

Les chiffres sont des **mesures exploratoires de bout en bout**, non des
benchmarks comparables aux moteurs en production : ils incluent le build
d'image, l'initialisation, les drivers, SQLAlchemy et/ou TestClient et
sont effectués en jobs parallèles sur des runners GitHub différents.
Ne pas extrapoler les latences avant plusieurs répétitions et une
configuration mémoire/CPU uniformisée.

La connexion ODBC accepte le certificat auto-signé SQL Server
(`TrustServerCertificate=yes`) **uniquement dans ce POC isolé** ; cette
configuration n'est pas admissible pour une application exposée.

La migration v2 ne couvre qu'une colonne et un index ; l'évaluation des
**56 tables logiques** du MLD, la gestion de migrations complexes, les
charges de plusieurs utilisateurs, l'authentification finale et la
résilience métier interbases ne sont pas prouvées.

**ADR-004 inchangée :** MongoDB est conservé pour les métadonnées et les
futurs stockages LLM. SQL Server et PostgreSQL demeurent **candidats**
au moteur métier relationnel. Aucune migration de données réelles.
