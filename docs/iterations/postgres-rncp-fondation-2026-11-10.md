# Lot PostgreSQL RNCP — première fondation (10 novembre 2026)

**Décision :** [ADR-005](../decisions/ADR-005-strategie-stockage.md) — PostgreSQL pour le métier relationnel, MongoDB conservé pour les métadonnées et les futurs stockages LLM.

**PR :** [#19](https://github.com/tomtoomuch/DevKnowledge/pull/19) ; **Linear :** [DOC-39](https://linear.app/documentation-perso/issue/DOC-39).

## Périmètre effectivement codé

- Sous `backend/knowledge-service/app/rncp/` : migrateur PostgreSQL et adaptateur de **lecture** des versions de référentiel, compétences, critères et preuves. Il **n'est pas importé dans `app.main`** ; aucun endpoint supplémentaire n'est exposé sur la pile applicative actuelle.
- Sous `poc/rncp-postgres/` : Compose isolé PostgreSQL 17, image Python de tests, scripts versionnés 001/002 et données fictives `RNCP-TEST`.
- **10 tables métier** de la section I/J du MLD 3NF v0.2 : `certification_frameworks`, `certification_framework_versions`, `certification_blocks`, `certification_competencies`, `assessment_criteria`, `knowledge_competency_links`, `competency_assessments`, `evidence_types`, `evidence_artifacts`, `competency_evidence`, plus `schema_migrations`.
- Contrôles FK locaux, contraintes d'unicité, plage de confiance 0–1, migrations avec empreintes et sauvegarde/restauration dans une seconde base.
- Les `knowledge_id`, `created_by_user_id` et `project_id` restent **des identifiants externes, sans FK SQL inventée**, car les enregistrements maîtres existent dans MongoDB.

## Reproduction

Avec Docker Desktop démarré et Git Bash, depuis la racine du dépôt :

```bash
python poc/rncp-postgres/run.py
```

Le script attribue un nom de projet Docker et des identifiants de test uniques, démarre la base sans publier de port, exécute les tests et détruit **uniquement son projet Compose jetable**. La sauvegarde/restauration s'effectue dans le conteneur PostgreSQL de ce projet. Les résultats se trouvent dans `test-results/rncp-postgres/result.json` et sont publiés comme artefact CI.

## Validation et limitations

La [première exécution CI](https://github.com/tomtoomuch/DevKnowledge/actions/runs/42793010712) a réussi 5 tests et la restauration : PostgreSQL ~24,59 Mio avant tests et ~28,36 Mio après, avec limite mémoire de 512 Mio. L'itération ajoute ensuite un test de non-altération des migrations existantes ; consulter les exécutions suivantes pour le nombre de tests mis à jour.

Ces résultats ne sont ni une recette du KMS en production, ni un mapping de toutes les 56 tables. **Aucun contenu officiel du RNCP 37827 n'est introduit par le jeu fictif.** Le protocole de validation des références entre PostgreSQL et MongoDB, l'authentification via Gateway/Superviseur, la gestion des écritures métier, la sauvegarde multi-moteurs et les migrations de données existantes restent les prochains lots.
