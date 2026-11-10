# Documentation DevKnowledge

## État actuel et prochaines étapes

- [[iterations/revue-sortie-stabilisation-2026-11-09|Dossier de revue de sortie de stabilisation]]
- [[operations/offline-runtime|Qualification du fonctionnement hors ligne]]
- [[iterations/validation-stab08-2026-11-09|Validation STAB-08 — sauvegarde et concurrence]]
- [[iterations/validation-gateway-2026-11-09|Validation STAB-06 — Gateway vers KMS]]
- [[iterations/point-avancement-2026-11-04|Point d'avancement — 4 novembre 2026]]
- [[iterations/iteration-2-stabilisation|Itération 2 — Plan de stabilisation à réaliser ensemble]]
- [[roadmap|Feuille de route actualisée]]
- [[operations/mongodb-bootstrap|MongoDB : provisionnement et smoke test isolé]]

- [[operations/backup-restore|Sauvegarde locale et restauration isolée]]
- [[operations/monitoring|Monitoring — santé des services via la Gateway]]
- [[architecture/knowledge-concurrency|Révisions et écritures conditionnelles]]

## Implémentation et référentiel

- [[architecture/gateway-kms|Gateway → KMS : contrat du relais et diagnostic]]
- [[architecture/kms-knowledge-crud|KMS : architecture, contrat CRUD et vérification manuelle]]
- [[iterations/iteration-1-kms-crud|Itération 1 : livraison et résultats historiques des tests]]
- [[DevKnowledge_MLD_3NF_v0.2|Modèle logique candidat 3NF — 56 tables, non intégralement implémentées]]
- [[architecture/architecture-globale|Architecture globale cible]]

## Décisions

- [[decisions/ADR-001-architecture|ADR 001 : architecture]]
- [[decisions/ADR-002-stockage|ADR 002 : stockage historique MongoDB]]
- [[decisions/ADR-003-identite-securite|ADR 003 : identité et sécurité — à valider]]

- [[iterations/iteration-4-search]] — Recherche globale et favoris via Gateway et KMS.

- [[iterations/iteration-5-identite-locale]] — Comptes locaux, sessions et RBAC.

- [[iterations/iteration-6-specializations]] — Huit spécialisations métier et catalogue des types (itération 6, PR #8).

- [[iterations/iteration-7-tags]] — Catalogue, affectation et filtrage des tags (PR #9 en validation).

- [[iterations/iteration-7b-technologies]] — Technologies, versions et associations aux connaissances (PR #10, dépendante de #9).

- [[iterations/iteration-8-knowledge-relations]] — Graphes typés de connaissances, prévention des doublons et révisions (PR #11).
- [Gateway, authentification et ports locaux](operations/auth-gateway.md)

- [Réseaux DMZ et interne / règles de communication](architecture/gateway-kms.md)

- [[iterations/iteration-9-user-crud]] — CRUD complet des comptes locaux (PR #12).
- [[operations/volume-persistence]] — Audit sans destruction du stockage MongoDB, identité Compose et persistance.

- [[decisions/ADR-004-superviseur-identite-securite]] — Gateway unique, Superviseur autorité d’identité et tokens interservices.

- [[decisions/ADR-005-strategie-stockage]] — **Décision acceptée** : PostgreSQL pour le métier, MongoDB pour les métadonnées et besoins LLM, SQLite pour les métriques.
- [[operations/metrics-sqlite]] — Échantillonnage, stockage, lecture interne et sauvegarde des métriques du Superviseur.

- [[iterations/postgres-rncp-fondation-2026-11-10]] — Premier lot PostgreSQL RNCP isolé : schéma, migrations, API de lecture et tests Docker ([PR #19](https://github.com/tomtoomuch/DevKnowledge/pull/19)).

- [[iterations/postgres-rncp-api-2026-11-10]] — Routes RNCP protégées et écriture PostgreSQL prévisualisée derrière Gateway ; opt-in, tests Docker et limites interbases.
