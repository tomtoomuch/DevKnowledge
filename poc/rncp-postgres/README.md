# RNCP PostgreSQL — premier lot de persistance (ADR-005, DOC-39)

Ce lot **introduit un adaptateur KMS non activé** sous
`backend/knowledge-service/app/rncp/`, accompagné d'une base PostgreSQL
17 d'essai dans un projet Compose distinct.

**Il ne monte aucune nouvelle route dans `app.main`**, ne publie aucun
port PostgreSQL ni FastAPI et ne modifie ni le Compose principal ni les
volumes MongoDB. L'API de test est accessible **uniquement via FastAPI
TestClient**, à l'intérieur du conteneur de test. L'activation côté KMS
réel sera une itération ultérieure nécessitant contrôle RBAC du Gateway,
identité interservice, migrations métier, sauvegardes et rollback.

## Couverture du MLD

Schéma `rncp` reprenant les noms et champs du **MLD candidat 3NF v0.2** :

- `certification_frameworks` et `certification_framework_versions` ;
- `certification_blocks`, `certification_competencies`,
  `assessment_criteria`, `competency_assessments` ;
- `evidence_types`, `evidence_artifacts`, `competency_evidence` ;
- `knowledge_competency_links`.

Soit **10 tables métier** du périmètre logique, plus
`schema_migrations`. Les contraintes FK locales et UNIQUE sont
matérialisées ; la vérification transversale des UUID de connaissances,
utilisateurs et projets restés dans MongoDB **n'est pas encore résolue**.
Cela ne constitue pas une migration des 56 tables.

Les 13 codes de `evidence_types` sont repris du MLD ; aucun texte officiel
du RNCP 37827 n'est imaginé : les jeux de données utilisent uniquement
`RNCP-TEST`, deux versions fictives et des preuves factices.

## Tests réels

Depuis Git Bash à la racine du dépôt, Docker Desktop actif :

```bash
python poc/rncp-postgres/run.py
```

Le script crée un nom de projet Compose et un mot de passe aléatoires,
démarre `postgres:17` sur un réseau `internal:true` **sans ports hôtes**,
construit un conteneur Python distinct, exécute pytest + FastAPI TestClient
+ psycopg, sauvegarde par `pg_dump`, restaure dans une seconde base
et compare les comptes, puis détruit **uniquement les volumes du POC**.

Tests couverts : migrations versionnées et rejouables avec contrôle des
empreintes, identité de référentiel vs versions, navigation blocs/compétences,
critères et preuves, refus des références absentes, unicité, score 0..1,
transaction rollback, disponibilité PostgreSQL, vérification de restauration.
Rapport JSON disponible dans `test-results/rncp-postgres/result.json`.

**Limites :** non branché à l'authentification du KMS de production ;
pas de migration depuis MongoDB ni de jointure SQL–Mongo ; pas de
parcours Angular, pas de transaction répartie ni de stockage du LLM.
Image de test construite avec accès réseau pour les dépendances :
qualification du *build* entièrement hors ligne reportée.
