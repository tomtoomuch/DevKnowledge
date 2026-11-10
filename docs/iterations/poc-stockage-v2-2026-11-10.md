# POC V2 — comparaison SQL Server 2025 / PostgreSQL 17 (10 novembre 2026)

**Issue :** [DOC-38](https://linear.app/documentation-perso/issue/DOC-38)  
**PR :** [#15, branche `feature/poc-sqlserver-postgres-rncp`](https://github.com/tomtoomuch/DevKnowledge/pull/15)  
**Exécution probante :** [GitHub Actions 42779109464](https://github.com/tomtoomuch/DevKnowledge/actions/runs/42779109464) — **deux jobs réussis**.  
**Commit testé :** `dd14a162889eabda42c3842da4597e7c1f0bba5e`.

## Protocole

- Deux moteurs **réels**, conteneurs Docker sur projets Compose et réseaux internes jetables distincts :
  `mcr.microsoft.com/mssql/server:2025-latest` (Developer POC) et `postgres:17`.
- Aucun port de base de données publié ; aucun accès au MongoDB ou aux volumes de `dev`.
- Six tables métier représentatives (référentiel RNCP, blocs, compétences,
  connaissances, preuves et associations), sur données **fictives**.
- Migration V2 (ajout d'une colonne `source_kind` et d'un index)
  appliquée **deux fois** pour vérifier l'idempotence.
- Validation FK, UNIQUE, JSON, jointure RNCP et preuve, transaction ROLLBACK,
  écriture conditionnelle de révision, sauvegarde et restauration dans une
  base distincte.
- Image cliente Python 3.12 avec **FastAPI + SQLAlchemy Core + ODBC Driver 18**
  pour SQL Server et **FastAPI + SQLAlchemy Core + psycopg 3** pour PostgreSQL.
  Requêtes HTTP via `TestClient` ASGI (sans ouverture de port public).
- Insertion en une transaction de **1 500 connaissances + 1 500 preuves +
  1 500 associations** ; validation de 50 consultations HTTP et 15 créations
  HTTP avec contrôle 200/201/412/428 ; comparaison de compteur source/restauré.
- Mesure d'un instantané CPU/mémoire via `docker stats --no-stream` avant
  et après tests, limites mémoire identiques à 3 Gio.

## Résultats mesurés

| Mesure | PostgreSQL 17 | SQL Server 2025 |
|---|---:|---:|
| Statut global POC | **PASS** | **PASS** |
| Démarrage Docker + readiness | 13,835 s | 24,035 s |
| Création du schéma | 0,138 s | 0,394 s |
| Migration V2, première application | 0,136 s | 0,198 s |
| Migration V2, réapplication | 0,133 s | 0,176 s |
| Invariants SQL | 0,134 s | 0,212 s |
| Build image cliente FastAPI | 16,441 s | 15,886 s |
| Insertion de 4 500 lignes en une transaction | 141,001 ms | 513,864 ms |
| GET /coverage via FastAPI, médiane (n=50) | 3,677 ms | 3,292 ms |
| GET /coverage, p95 | 3,823 ms | 3,587 ms |
| POST /knowledge via FastAPI, médiane (n=15) | 1,973 ms | 2,530 ms |
| POST /knowledge, p95 | 2,855 ms | 3,435 ms |
| Mémoire DB avant benchmark | 24,81 MiB / 3 Gio | 420,2 MiB / 3 Gio |
| Mémoire DB après benchmark | 27,09 MiB / 3 Gio | 487,2 MiB / 3 Gio |
| Backup et restauration base distincte | 0,778 s, **PASS** | 0,665 s, **PASS** |
| Nettoyage conteneurs/volumes uniquement temporaires | **PASS** | **PASS** |

**Preuves :** artefacts JSON `storage-poc-postgres` et
`storage-poc-sqlserver` sur l'exécution liée ci-dessus ; logs des deux jobs.

## Bugs révélés et corrigés pendant la recette

1. La migration V2 ajoutait une colonne à `evidence_items` ; les fixtures
   historiques sans liste explicite de colonnes échouaient. Corrigé pour
   les deux dialectes SQL.
2. L'ancien test de restauration supposait une seule connaissance en révision 2.
   Les 15 écritures FastAPI supplémentaires portaient ce nombre à 16.
   Correction : comparaison des comptes et révisions **de la base source
   et de la base restaurée**.

## Interprétation et recommandation

Les deux moteurs prouvent qu'ils savent implémenter **un sous-ensemble
relationnel représentatif** de DevKnowledge, avec une API Python.
PostgreSQL consomme **moins de mémoire** dans cette exécution unique
et son insertion en transaction est plus rapide. SQL Server conserve une
bonne latence de lecture sur ce test, mais utilise plus de mémoire.

**Il ne s'agit pas d'un benchmark de production** : un seul run, jobs GitHub
distincts, processeurs/voisins non contrôlés, temps SQLAlchemy, FastAPI et
drivers inclus, jeux de données limités, pas de requêtes concurrentes,
aucune comparaison d'index avancés ni des 56 tables logiques. Les images
sont référencées par tags mutables (leurs IDs sont conservés dans les JSON).
L'image cliente demande un build connecté.

**Recommandation provisoire :** privilégier **PostgreSQL comme hypothèse de
travail** pour un SGBDR métier à faible coût matériel et opérationnel
local, sans exclure SQL Server si un besoin Microsoft ou métier concret
le justifie. Une décision finale nécessite étude des licences,
authentification, sécurité et migrations grandeur nature.

**Décision déjà prise : MongoDB reste conservé** pour les métadonnées et
les futurs stockages LLM. Aucun domaine métier ni volume actuel n'a été
migré. L'ADR-004 demeure **proposée**, la PR #15 demeure en brouillon
jusqu'à revue et acceptation explicite.
