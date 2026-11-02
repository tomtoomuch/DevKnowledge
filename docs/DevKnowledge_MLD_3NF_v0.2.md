---
title: "DevKnowledge — Modèle logique de données consolidé (candidat 3NF)"
version: "0.2.0"
date: "2026-11-02"
status: "Proposition à relire — non implémentée"
project: "DevKnowledge"
tags: [devknowledge, mld, modelisation, 3nf, rncp, rbac, rag]
---

# DevKnowledge — MLD textuel consolidé, version 0.2

> **Statut : candidat à la 3NF, à valider métier.** Ce document n'est **pas** un script SQL ; il décrit le modèle logique attendu. Il peut être modifié librement dans VS Code ou Obsidian. Aucune modification du dépôt GitHub n'est impliquée par sa création.

## 1. Objet et conventions

Ce modèle couvre les connaissances locales (8 spécialisations), la classification, les procédures, les sources et versions, les projets, les référentiels de conformité, la certification RNCP, les preuves, le RAG et les autorisations RBAC.

- **56 tables** : 30 tables exigées dans le périmètre initial, 19 tables de structuration supplémentaires et 7 ajouts validés lors de la dernière itération.
- **`PK`** : clé primaire ; **`FK → table.colonne`** : clé étrangère ; **`PK, FK`** : colonne participant à une clé primaire composite et servant de clé étrangère.
- Les identifiants métier des tables utilisent par convention des **UUID** (choix encore ajustable). `VARCHAR`, `TEXT`, `DATE`, `TIMESTAMP`, `INTEGER`, `SMALLINT`, `BOOLEAN` et `DECIMAL` sont des types **logiques**, indépendants d'un SGBD particulier.
- Les champs marqués `NULL` sont facultatifs ; ceux marqués `NOT NULL` sont requis. En l'absence d'indication, la nullabilité est **à valider** lors du passage au schéma physique.
- **`UNIQUE`**, `CHECK`, les suppressions en cascade et les index sont détaillés dans la section « Contraintes » ; ils ne sont pas implicitement garantis par cette notation.
- Les champs `TEXT` tels que `benefits`, `parameters` ou `expected_deliverables` sont considérés comme des **descriptions libres atomiques** au niveau logique. S'ils doivent porter une liste d'objets indépendants et interrogeables, il faudra les normaliser davantage.
- Sauf exception documentée, les dates et heures sont enregistrées en **UTC** ; l'affichage sera localisé par l'application.

### Hypothèses métier structurantes

1. Chaque `knowledge_items` possède un **type principal** et zéro ou une ligne de la spécialisation correspondante ; huit types autorisés. Le contrôle de correspondance est une **contrainte intertables** à implémenter.
2. Une étape appartient à **une seule** procédure. Une version de connaissance appartient à **une seule** connaissance.
3. Sources et pièces jointes peuvent être **partagées** par plusieurs connaissances.
4. Une norme peut avoir plusieurs éditions. Ses exigences, codes locaux et obligations sont rattachés à une **édition** ; une exigence garde son identité propre, même si son code ressemble à celui d'une autre exigence.
5. Le référentiel RNCP possède une identité stable et plusieurs **versions**, dont les blocs et compétences sont propres à chaque version.
6. Plusieurs rôles peuvent être attribués à un utilisateur ; un rôle porte plusieurs permissions. Les droits effectifs sont calculés au niveau applicatif.
7. Les `knowledge_chunks` dépendent de la **version source** ; plusieurs embeddings peuvent exister pour un fragment.
8. L'architecture du service reste **locale/offline-first**. Le MLD relationnel n'impose pas l'utilisation d'un SGBD SQL : une transposition MongoDB sera étudiée séparément.

## 2. MLD textuel — 56 tables

### A. Identité, rôles et autorisations — 5 tables

```text
users = (
    user_id UUID [PK],
    username VARCHAR(100) [NOT NULL],
    email VARCHAR(255) [NULL],
    password_hash VARCHAR(255) [NULL],
    oidc_issuer VARCHAR(512) [NULL],
    oidc_subject VARCHAR(255) [NULL],
    account_status VARCHAR(30) [NOT NULL],
    created_at TIMESTAMP [NOT NULL],
    updated_at TIMESTAMP [NOT NULL],
    last_login_at TIMESTAMP [NULL]
);

roles = (
    role_id UUID [PK],
    code VARCHAR(50) [NOT NULL],
    name VARCHAR(100) [NOT NULL],
    description TEXT [NULL]
);

permissions = (
    permission_id UUID [PK],
    code VARCHAR(100) [NOT NULL],
    resource VARCHAR(100) [NOT NULL],
    action VARCHAR(50) [NOT NULL],
    description TEXT [NULL]
);

user_roles = (
    user_id UUID [PK, FK → users.user_id],
    role_id UUID [PK, FK → roles.role_id],
    assigned_at TIMESTAMP [NOT NULL]
);

role_permissions = (
    role_id UUID [PK, FK → roles.role_id],
    permission_id UUID [PK, FK → permissions.permission_id]
);
```

**Note :** `author_role` sur les preuves décrit la participation de la personne au projet (ex. responsable API), et **non** un rôle de sécurité `roles`. Un compte local utilise `password_hash` (jamais un mot de passe brut) ; un compte fédéré utilise le couple `oidc_issuer`/`oidc_subject`. Le modèle des comptes mixtes et le cycle de vie des identités seront précisés lors de l'implémentation OIDC.

### B. Connaissances et huit spécialisations — 10 tables

```text
knowledge_types = (
    knowledge_type_id UUID [PK],
    code VARCHAR(50) [NOT NULL],
    label VARCHAR(100) [NOT NULL],
    description TEXT [NULL]
);

knowledge_items = (
    knowledge_id UUID [PK],
    knowledge_type_id UUID [FK → knowledge_types.knowledge_type_id, NOT NULL],
    title VARCHAR(150) [NOT NULL],
    description TEXT [NULL],
    content TEXT [NOT NULL],
    language_code VARCHAR(10) [NULL],
    difficulty_level VARCHAR(30) [NULL],
    status VARCHAR(30) [NOT NULL],
    created_at TIMESTAMP [NOT NULL],
    updated_at TIMESTAMP [NOT NULL],
    validated_at TIMESTAMP [NULL],
    created_by_user_id UUID [FK → users.user_id, NOT NULL],
    is_favorite BOOLEAN [NOT NULL]
);

code_snippets = (
    knowledge_id UUID [PK, FK → knowledge_items.knowledge_id],
    code TEXT [NOT NULL],
    programming_language VARCHAR(50) [NOT NULL],
    framework VARCHAR(100) [NULL],
    snippet_version VARCHAR(30) [NULL],
    entry_point VARCHAR(255) [NULL],
    input_example TEXT [NULL],
    output_example TEXT [NULL],
    execution_context TEXT [NULL],
    is_executable BOOLEAN [NULL],
    license VARCHAR(100) [NULL]
);

terminal_commands = (
    knowledge_id UUID [PK, FK → knowledge_items.knowledge_id],
    command TEXT [NOT NULL],
    shell VARCHAR(50) [NOT NULL],
    operating_system VARCHAR(100) [NULL],
    working_directory VARCHAR(500) [NULL],
    parameters TEXT [NULL],
    expected_output TEXT [NULL],
    risk_level VARCHAR(30) [NULL],
    requires_sudo BOOLEAN [NULL],
    is_destructive BOOLEAN [NULL],
    execution_notes TEXT [NULL]
);

technical_procedures = (
    knowledge_id UUID [PK, FK → knowledge_items.knowledge_id],
    objective TEXT [NULL],
    environment TEXT [NULL],
    estimated_duration_minutes INTEGER [NULL],
    difficulty VARCHAR(30) [NULL],
    rollback_procedure TEXT [NULL],
    validation_criteria TEXT [NULL]
);

course_notes = (
    knowledge_id UUID [PK, FK → knowledge_items.knowledge_id],
    module_id UUID [FK → course_modules.module_id, NULL],
    concept VARCHAR(255) [NULL],
    definition TEXT [NULL],
    explanation TEXT [NULL],
    mastery_level SMALLINT [NULL]
);

bug_fixes = (
    knowledge_id UUID [PK, FK → knowledge_items.knowledge_id],
    error_title VARCHAR(255) [NULL],
    error_message TEXT [NULL],
    error_code VARCHAR(100) [NULL],
    symptoms TEXT [NULL],
    root_cause TEXT [NULL],
    solution TEXT [NULL],
    code_before TEXT [NULL],
    code_after TEXT [NULL],
    environment TEXT [NULL],
    resolution_status VARCHAR(30) [NULL],
    verified_at TIMESTAMP [NULL]
);

documentation_resources = (
    knowledge_id UUID [PK, FK → knowledge_items.knowledge_id],
    url TEXT [NULL],
    resource_type VARCHAR(50) [NULL],
    publisher VARCHAR(150) [NULL],
    publication_date DATE [NULL],
    accessed_at TIMESTAMP [NULL],
    version_reference VARCHAR(50) [NULL],
    summary TEXT [NULL],
    reliability_level VARCHAR(30) [NULL],
    is_official BOOLEAN [NULL]
);

best_practices = (
    knowledge_id UUID [PK, FK → knowledge_items.knowledge_id],
    principle TEXT [NULL],
    rationale TEXT [NULL],
    recommendation TEXT [NULL],
    anti_pattern TEXT [NULL],
    benefits TEXT [NULL],
    application_context TEXT [NULL],
    reference_standard_id UUID [FK → compliance_standards.knowledge_id, NULL],
    validation_criteria TEXT [NULL]
);

compliance_standards = (
    knowledge_id UUID [PK, FK → knowledge_items.knowledge_id],
    reference_code VARCHAR(100) [NOT NULL],
    compliance_type VARCHAR(50) [NULL],
    issuing_organization VARCHAR(150) [NULL],
    jurisdiction VARCHAR(100) [NULL],
    scope TEXT [NULL],
    applicability TEXT [NULL],
    official_url TEXT [NULL]
);
```

Les **huit codes** attendus dans `knowledge_types` sont : `CODE_SNIPPET`, `TERMINAL_COMMAND`, `TECHNICAL_PROCEDURE`, `COURSE_NOTE`, `BUG_FIX`, `DOCUMENTATION_RESOURCE`, `BEST_PRACTICE`, `COMPLIANCE_STANDARD`.

### C. Procédures et contenus structurés — 9 tables

```text
procedure_steps = (
    step_id UUID [PK],
    procedure_knowledge_id UUID [FK → technical_procedures.knowledge_id, NOT NULL],
    step_order INTEGER [NOT NULL],
    title VARCHAR(150) [NOT NULL],
    instructions TEXT [NOT NULL],
    expected_result TEXT [NULL],
    command TEXT [NULL]
);

procedure_prerequisites = (
    prerequisite_id UUID [PK],
    procedure_knowledge_id UUID [FK → technical_procedures.knowledge_id, NOT NULL],
    required_knowledge_id UUID [FK → knowledge_items.knowledge_id, NULL],
    prerequisite_text TEXT [NULL],
    position INTEGER [NOT NULL]
);

snippet_dependencies = (
    dependency_id UUID [PK],
    snippet_knowledge_id UUID [FK → code_snippets.knowledge_id, NOT NULL],
    dependency_name VARCHAR(150) [NOT NULL],
    version_constraint VARCHAR(100) [NULL]
);

courses = (
    course_id UUID [PK],
    name VARCHAR(150) [NOT NULL],
    description TEXT [NULL]
);

course_modules = (
    module_id UUID [PK],
    course_id UUID [FK → courses.course_id, NOT NULL],
    name VARCHAR(150) [NOT NULL],
    description TEXT [NULL]
);

learning_objectives = (
    objective_id UUID [PK],
    description TEXT [NOT NULL]
);

course_note_objectives = (
    course_note_knowledge_id UUID [PK, FK → course_notes.knowledge_id],
    objective_id UUID [PK, FK → learning_objectives.objective_id]
);

course_note_examples = (
    example_id UUID [PK],
    course_note_knowledge_id UUID [FK → course_notes.knowledge_id, NOT NULL],
    example_order INTEGER [NOT NULL],
    example_content TEXT [NOT NULL]
);

bug_diagnostic_steps = (
    diagnostic_step_id UUID [PK],
    bug_fix_knowledge_id UUID [FK → bug_fixes.knowledge_id, NOT NULL],
    step_order INTEGER [NOT NULL],
    instructions TEXT [NOT NULL],
    expected_observation TEXT [NULL]
);
```

La contrainte sur `procedure_prerequisites` est **exactement une valeur** renseignée parmi `required_knowledge_id` et `prerequisite_text`. `procedure_steps.command` est un texte d'instruction associé à l'étape ; une relation directe vers une connaissance de type `TERMINAL_COMMAND` pourra être ajoutée si la réutilisation des commandes devient nécessaire.

### D. Classification des connaissances et versions technologiques — 6 tables

```text
tags = (
    tag_id UUID [PK],
    name VARCHAR(100) [NOT NULL]
);

knowledge_tags = (
    knowledge_id UUID [PK, FK → knowledge_items.knowledge_id],
    tag_id UUID [PK, FK → tags.tag_id]
);

technologies = (
    technology_id UUID [PK],
    name VARCHAR(100) [NOT NULL],
    category VARCHAR(100) [NULL]
);

technology_versions = (
    technology_version_id UUID [PK],
    technology_id UUID [FK → technologies.technology_id, NOT NULL],
    version VARCHAR(50) [NOT NULL],
    release_date DATE [NULL]
);

knowledge_technologies = (
    knowledge_id UUID [PK, FK → knowledge_items.knowledge_id],
    technology_id UUID [PK, FK → technologies.technology_id]
);

knowledge_technology_versions = (
    knowledge_id UUID [PK, FK → knowledge_items.knowledge_id],
    technology_version_id UUID [PK, FK → technology_versions.technology_version_id]
);
```

`knowledge_technologies` décrit une association générique, sans engagement sur une version. `knowledge_technology_versions` décrit une association précise. Une règle applicative doit éviter les doublons sémantiques si les deux liens sont utilisés conjointement.

### E. Relations entre connaissances — 2 tables

```text
relation_types = (
    relation_type_id UUID [PK],
    code VARCHAR(50) [NOT NULL],
    label VARCHAR(100) [NOT NULL],
    is_directed BOOLEAN [NOT NULL]
);

knowledge_relations = (
    relation_id UUID [PK],
    origin_knowledge_id UUID [FK → knowledge_items.knowledge_id, NOT NULL],
    target_knowledge_id UUID [FK → knowledge_items.knowledge_id, NOT NULL],
    relation_type_id UUID [FK → relation_types.relation_type_id, NOT NULL],
    relation_notes TEXT [NULL]
);
```

Exemples de types : `DEPENDS_ON`, `COMPLEMENTS`, `CONTRADICTS`, `SUPERSEDES`, `RELATED_TO`. Les relations non orientées nécessitent une convention de rangement canonique ou une validation équivalente pour éviter les doublons inversés.

### F. Sources, pièces jointes et historique — 5 tables

```text
knowledge_sources = (
    source_id UUID [PK],
    source_reference TEXT [NOT NULL],
    source_type VARCHAR(50) [NULL],
    source_url TEXT [NULL],
    retrieved_at TIMESTAMP [NULL]
);

knowledge_source_links = (
    knowledge_id UUID [PK, FK → knowledge_items.knowledge_id],
    source_id UUID [PK, FK → knowledge_sources.source_id]
);

knowledge_attachments = (
    attachment_id UUID [PK],
    file_path VARCHAR(1000) [NOT NULL],
    mime_type VARCHAR(150) [NULL],
    file_checksum VARCHAR(128) [NULL],
    added_at TIMESTAMP [NOT NULL]
);

knowledge_attachment_links = (
    knowledge_id UUID [PK, FK → knowledge_items.knowledge_id],
    attachment_id UUID [PK, FK → knowledge_attachments.attachment_id]
);

knowledge_versions = (
    version_id UUID [PK],
    knowledge_id UUID [FK → knowledge_items.knowledge_id, NOT NULL],
    version_number VARCHAR(50) [NOT NULL],
    content_snapshot TEXT [NOT NULL],
    created_at TIMESTAMP [NOT NULL],
    created_by_user_id UUID [FK → users.user_id, NOT NULL]
);
```

`knowledge_items.content` est l'état courant ; `knowledge_versions.content_snapshot` est un instantané historique. Les données sont volontairement distinctes, même si les valeurs peuvent coïncider à un instant donné.

### G. Conformité — 6 tables

```text
compliance_requirements = (
    requirement_id UUID [PK],
    title VARCHAR(255) [NOT NULL],
    description TEXT [NOT NULL],
    verification_method TEXT [NULL],
    implementation_guidance TEXT [NULL]
);

compliance_standard_versions = (
    standard_version_id UUID [PK],
    standard_knowledge_id UUID [FK → compliance_standards.knowledge_id, NOT NULL],
    version_reference VARCHAR(100) [NOT NULL],
    publication_date DATE [NULL],
    effective_date DATE [NULL],
    review_date DATE [NULL],
    expiration_date DATE [NULL]
);

compliance_standard_requirements = (
    standard_version_id UUID [PK, FK → compliance_standard_versions.standard_version_id],
    requirement_id UUID [PK, FK → compliance_requirements.requirement_id],
    requirement_code VARCHAR(100) [NOT NULL],
    severity VARCHAR(30) [NULL],
    mandatory BOOLEAN [NOT NULL]
);

compliance_assessments = (
    assessment_id UUID [PK],
    project_id UUID [FK → projects.project_id, NOT NULL],
    standard_version_id UUID [FK → compliance_standard_versions.standard_version_id, NOT NULL],
    assessment_status VARCHAR(30) [NOT NULL],
    assessment_date TIMESTAMP [NOT NULL],
    assessment_notes TEXT [NULL],
    assessed_by_user_id UUID [FK → users.user_id, NOT NULL],
    next_review_date DATE [NULL]
);

compliance_assessment_results = (
    assessment_id UUID [PK, FK → compliance_assessments.assessment_id],
    requirement_id UUID [PK, FK → compliance_requirements.requirement_id],
    result_status VARCHAR(30) [NOT NULL],
    assessment_notes TEXT [NULL],
    reviewed_at TIMESTAMP [NULL]
);

compliance_result_evidence = (
    assessment_id UUID [PK],
    requirement_id UUID [PK],
    evidence_id UUID [PK, FK → evidence_artifacts.evidence_id]
);
```

**Point d'intégrité intertables :** la paire `(assessment_id, requirement_id)` de `compliance_result_evidence` est une **clé étrangère composite** vers `compliance_assessment_results(assessment_id, requirement_id)`. Une exigence évaluée doit appartenir à la version de norme de la campagne. Ce contrôle ne découle pas automatiquement des seules clés étrangères déclarées ; une contrainte adaptée au SGBD, un déclencheur ou une validation transactionnelle sera nécessaire. `requirement_code` est unique **dans une version de norme**, pas globalement.

### H. Projets — 1 table

```text
projects = (
    project_id UUID [PK],
    name VARCHAR(150) [NOT NULL],
    description TEXT [NULL],
    repository_url TEXT [NULL],
    start_date DATE [NULL],
    end_date DATE [NULL],
    status VARCHAR(30) [NOT NULL],
    created_at TIMESTAMP [NOT NULL]
);
```

### I. Référentiels de certification et suivi des compétences — 7 tables

```text
certification_frameworks = (
    framework_id UUID [PK],
    code VARCHAR(50) [NOT NULL],
    title VARCHAR(255) [NOT NULL],
    certifier VARCHAR(255) [NOT NULL]
);

certification_framework_versions = (
    framework_version_id UUID [PK],
    framework_id UUID [FK → certification_frameworks.framework_id, NOT NULL],
    version VARCHAR(50) [NOT NULL],
    qualification_level VARCHAR(50) [NULL],
    registration_date DATE [NULL],
    expiration_date DATE [NULL],
    source_url TEXT [NULL],
    retrieved_at TIMESTAMP [NULL]
);

certification_blocks = (
    block_id UUID [PK],
    framework_version_id UUID [FK → certification_framework_versions.framework_version_id, NOT NULL],
    block_code VARCHAR(100) [NOT NULL],
    title VARCHAR(255) [NOT NULL],
    description TEXT [NULL],
    evaluation_method TEXT [NULL]
);

certification_competencies = (
    competency_id UUID [PK],
    block_id UUID [FK → certification_blocks.block_id, NOT NULL],
    competency_code VARCHAR(100) [NOT NULL],
    official_description TEXT [NOT NULL],
    operational_description TEXT [NULL],
    expected_deliverables TEXT [NULL],
    evaluation_method TEXT [NULL],
    is_mandatory BOOLEAN [NOT NULL]
);

assessment_criteria = (
    criterion_id UUID [PK],
    competency_id UUID [FK → certification_competencies.competency_id, NOT NULL],
    criterion_code VARCHAR(100) [NOT NULL],
    description TEXT [NOT NULL]
);

knowledge_competency_links = (
    link_id UUID [PK],
    knowledge_id UUID [FK → knowledge_items.knowledge_id, NOT NULL],
    competency_id UUID [FK → certification_competencies.competency_id, NOT NULL],
    relevance_level VARCHAR(30) [NULL],
    mapping_rationale TEXT [NULL],
    confidence_score DECIMAL(5,4) [NULL],
    created_at TIMESTAMP [NOT NULL],
    created_by_user_id UUID [FK → users.user_id, NOT NULL]
);

competency_assessments = (
    assessment_id UUID [PK],
    competency_id UUID [FK → certification_competencies.competency_id, NOT NULL],
    assessed_by_user_id UUID [FK → users.user_id, NOT NULL],
    assessment_level VARCHAR(30) [NOT NULL],
    assessment_source VARCHAR(100) [NULL],
    assessment_date TIMESTAMP [NOT NULL],
    strengths TEXT [NULL],
    gaps TEXT [NULL],
    improvement_plan TEXT [NULL]
);
```

Une ligne de `certification_frameworks` représente une **identité** de référentiel (par exemple le code RNCP). Ses éditions sont dans `certification_framework_versions`. Les blocs, compétences et critères sont propres à la version. **Si le titre ou le certificateur dépend de l'édition, il faudra déplacer le champ concerné dans `certification_framework_versions`** : c'est un arbitrage de dépendance fonctionnelle à vérifier avec les données officielles.

### J. Preuves et justification des compétences — 3 tables

```text
evidence_types = (
    evidence_type_id UUID [PK],
    code VARCHAR(50) [NOT NULL],
    label VARCHAR(150) [NOT NULL],
    description TEXT [NULL]
);

evidence_artifacts = (
    evidence_id UUID [PK],
    title VARCHAR(255) [NOT NULL],
    description TEXT [NULL],
    evidence_type_id UUID [FK → evidence_types.evidence_type_id, NOT NULL],
    project_id UUID [FK → projects.project_id, NULL],
    file_path VARCHAR(1000) [NULL],
    repository_url TEXT [NULL],
    commit_hash VARCHAR(128) [NULL],
    demonstration_url TEXT [NULL],
    author_role VARCHAR(150) [NULL],
    created_at TIMESTAMP [NOT NULL],
    created_by_user_id UUID [FK → users.user_id, NOT NULL],
    verification_status VARCHAR(30) [NOT NULL],
    verification_notes TEXT [NULL]
);

competency_evidence = (
    id UUID [PK],
    competency_id UUID [FK → certification_competencies.competency_id, NOT NULL],
    evidence_id UUID [FK → evidence_artifacts.evidence_id, NOT NULL],
    evidence_role VARCHAR(30) [NOT NULL],
    demonstrated_aspects TEXT [NULL],
    limitations TEXT [NULL],
    review_status VARCHAR(30) [NOT NULL]
);
```

Codes de `evidence_types` à initialiser :

| Code | Signification |
|---|---|
| `SOURCE_CODE` | Code source |
| `UNIT_TEST` | Test unitaire |
| `INTEGRATION_TEST` | Test d'intégration |
| `TECHNICAL_DOCUMENTATION` | Documentation technique |
| `ARCHITECTURE_DIAGRAM` | Diagramme d'architecture |
| `DATABASE_SCHEMA` | Schéma de données |
| `API_DOCUMENTATION` | Documentation API |
| `CI_CD_PIPELINE` | Pipeline CI/CD |
| `SCREENSHOT` | Capture d'écran |
| `VIDEO_DEMO` | Démonstration vidéo |
| `PROFESSIONAL_REPORT` | Rapport professionnel |
| `INCIDENT_REPORT` | Rapport d'incident |
| `BENCHMARK` | Étude comparative |

### K. Fragmentation documentaire et indexation RAG — 2 tables

```text
knowledge_chunks = (
    chunk_id UUID [PK],
    knowledge_version_id UUID [FK → knowledge_versions.version_id, NOT NULL],
    chunk_index INTEGER [NOT NULL],
    chunk_content TEXT [NOT NULL],
    token_count INTEGER [NOT NULL],
    generated_at TIMESTAMP [NOT NULL]
);

chunk_embeddings = (
    chunk_embedding_id UUID [PK],
    chunk_id UUID [FK → knowledge_chunks.chunk_id, NOT NULL],
    embedding_id VARCHAR(255) [NOT NULL],
    embedding_model VARCHAR(150) [NOT NULL],
    indexed_at TIMESTAMP [NULL]
);
```

`embedding_id` est une **référence externe au magasin vectoriel** (ex. ChromaDB), et non une valeur vectorielle stockée en relationnel. Le modèle de chunking (taille, recouvrement, stratégie) pourra être historisé dans un ajout ultérieur si plusieurs stratégies doivent être comparées.

---

## 3. Catalogue de contrôle : 30 tables impératives

| N° | Domaine | Table | Vérification |
|---:|---|---|---|
| 01 | Connaissances | `knowledge_items` | Présente |
| 02 | Connaissances | `code_snippets` | Présente |
| 03 | Connaissances | `terminal_commands` | Présente |
| 04 | Connaissances | `technical_procedures` | Présente |
| 05 | Connaissances | `course_notes` | Présente |
| 06 | Connaissances | `bug_fixes` | Présente |
| 07 | Connaissances | `documentation_resources` | Présente |
| 08 | Connaissances | `best_practices` | Présente |
| 09 | Connaissances | `compliance_standards` | Présente |
| 10 | Procédures | `procedure_steps` | Présente |
| 11 | Classification | `tags` | Présente |
| 12 | Classification | `knowledge_tags` | Présente |
| 13 | Classification | `technologies` | Présente |
| 14 | Classification | `knowledge_technologies` | Présente |
| 15 | Relations | `knowledge_relations` | Présente |
| 16 | Traçabilité | `knowledge_sources` | Présente |
| 17 | Traçabilité | `knowledge_attachments` | Présente |
| 18 | Traçabilité | `knowledge_versions` | Présente |
| 19 | Conformité | `compliance_requirements` | Présente |
| 20 | Conformité | `compliance_assessments` | Présente |
| 21 | Projets | `projects` | Présente |
| 22 | Certification | `certification_frameworks` | Présente |
| 23 | Certification | `certification_blocks` | Présente |
| 24 | Certification | `certification_competencies` | Présente |
| 25 | Certification | `assessment_criteria` | Présente |
| 26 | Certification | `knowledge_competency_links` | Présente |
| 27 | Certification | `competency_assessments` | Présente |
| 28 | Preuves | `evidence_artifacts` | Présente |
| 29 | Preuves | `competency_evidence` | Présente |
| 30 | RAG | `knowledge_chunks` | Présente |

**19 tables complémentaires du modèle précédent :** `knowledge_types`, `technology_versions`, `relation_types`, `knowledge_source_links`, `knowledge_attachment_links`, `compliance_standard_versions`, `compliance_standard_requirements`, `compliance_assessment_results`, `compliance_result_evidence`, `evidence_types`, `chunk_embeddings`, `snippet_dependencies`, `procedure_prerequisites`, `courses`, `course_modules`, `learning_objectives`, `course_note_objectives`, `course_note_examples`, `bug_diagnostic_steps`.

**7 dernières tables ajoutées et validées :** `certification_framework_versions`, `knowledge_technology_versions`, `users`, `roles`, `permissions`, `user_roles`, `role_permissions`.

## 4. Cardinalités structurantes

| Relation | Cardinalité |
|---|---|
| `knowledge_types → knowledge_items` | 1:N |
| `knowledge_items → spécialisation de son type` | 1:0..1 dans la table correspondante |
| `users → knowledge_items` (créateur) | 1:N |
| `users ↔ roles` via `user_roles` | N:N |
| `roles ↔ permissions` via `role_permissions` | N:N |
| `technical_procedures → procedure_steps` | 1:N |
| `knowledge_items ↔ tags` | N:N |
| `knowledge_items ↔ technologies` | N:N générique |
| `knowledge_items ↔ technology_versions` | N:N versionnée |
| `knowledge_items ↔ knowledge_items` via `knowledge_relations` | N:N auto-référentielle |
| `knowledge_items ↔ knowledge_sources` | N:N |
| `knowledge_items ↔ knowledge_attachments` | N:N |
| `knowledge_items → knowledge_versions` | 1:N |
| `compliance_standards → compliance_standard_versions` | 1:N |
| `compliance_standard_versions ↔ compliance_requirements` | N:N avec code/contextualisation |
| `projects → compliance_assessments` | 1:N |
| `compliance_assessments → compliance_assessment_results` | 1:N |
| `certification_frameworks → certification_framework_versions` | 1:N |
| `certification_framework_versions → certification_blocks` | 1:N |
| `certification_blocks → certification_competencies` | 1:N |
| `certification_competencies → assessment_criteria` | 1:N |
| `knowledge_items ↔ certification_competencies` via `knowledge_competency_links` | N:N |
| `certification_competencies ↔ evidence_artifacts` via `competency_evidence` | N:N |
| `projects → evidence_artifacts` | 1:N facultatif côté preuve |
| `knowledge_versions → knowledge_chunks` | 1:N |
| `knowledge_chunks → chunk_embeddings` | 1:N |

## 5. Contraintes uniques, contrôles et invariants

Les contraintes suivantes sont **attendues** pour le schéma physique ; elles ne sont pas toutes réalisables avec une simple clé étrangère.

| Table | Règle |
|---|---|
| `users` | `UNIQUE(username)` ; `UNIQUE(email)` lorsque non nul ; `UNIQUE(oidc_issuer, oidc_subject)` pour identité OIDC complète |
| `roles` | `UNIQUE(code)` |
| `permissions` | `UNIQUE(code)` et `UNIQUE(resource, action)` si chaque couple désigne une permission unique |
| `knowledge_types` | `UNIQUE(code)` |
| `tags` | `UNIQUE(name)` (normalisation de la casse à définir) |
| `technologies` | `UNIQUE(name)` si l'identité est globale |
| `technology_versions` | `UNIQUE(technology_id, version)` |
| `relation_types` | `UNIQUE(code)` |
| `procedure_steps` | `UNIQUE(procedure_knowledge_id, step_order)` |
| `procedure_prerequisites` | `UNIQUE(procedure_knowledge_id, position)` ; exactement un prérequis textuel ou référencé |
| `course_modules` | `UNIQUE(course_id, name)` si noms uniques dans un cours |
| `course_note_examples` | `UNIQUE(course_note_knowledge_id, example_order)` |
| `bug_diagnostic_steps` | `UNIQUE(bug_fix_knowledge_id, step_order)` |
| `knowledge_versions` | `UNIQUE(knowledge_id, version_number)` |
| `knowledge_relations` | `UNIQUE(origin_knowledge_id, target_knowledge_id, relation_type_id)` si aucune répétition de lien n'est autorisée |
| `compliance_standard_versions` | `UNIQUE(standard_knowledge_id, version_reference)` |
| `compliance_standard_requirements` | `UNIQUE(standard_version_id, requirement_code)` et clé primaire `(standard_version_id, requirement_id)` |
| `compliance_assessment_results` | clé primaire `(assessment_id, requirement_id)` ; exigence autorisée dans la norme évaluée |
| `certification_frameworks` | `UNIQUE(code)` |
| `certification_framework_versions` | `UNIQUE(framework_id, version)` |
| `certification_blocks` | `UNIQUE(framework_version_id, block_code)` |
| `certification_competencies` | `UNIQUE(block_id, competency_code)` |
| `assessment_criteria` | `UNIQUE(competency_id, criterion_code)` |
| `knowledge_competency_links` | `UNIQUE(knowledge_id, competency_id)` ; `confidence_score` compris entre 0 et 1 |
| `competency_evidence` | `UNIQUE(competency_id, evidence_id)` |
| `evidence_types` | `UNIQUE(code)` |
| `knowledge_chunks` | `UNIQUE(knowledge_version_id, chunk_index)` ; index >= 0 ; token_count >= 0 |
| `chunk_embeddings` | `UNIQUE(chunk_id, embedding_model)` **si un seul index par modèle et fragment** ; sinon la clé doit inclure l'identité de la stratégie ou de l'index |

**Intégrité des spécialisations.** Pour chaque connaissance, au plus une ligne spécialisée correspondant à son type. La simple présence d'une clé étrangère `specialisation.knowledge_id → knowledge_items.knowledge_id` ne garantit pas cette exclusivité : ajouter une validation transactionnelle ou une stratégie de discriminant adaptée.

**Intégrité des conformités.** `compliance_assessment_results.requirement_id` doit figurer parmi les exigences de la version référencée par l'évaluation ; la relation `compliance_result_evidence` ne peut référencer qu'un résultat effectivement présent.

**Intégrité des référentiels.** Une compétence et son bloc sont liés à la **même version** d'un référentiel par construction. La mise à jour d'un référentiel doit créer une nouvelle version lorsque les blocs ou les critères officiels changent.

**Sécurité.** Conserver l'historique en désactivant les comptes plutôt qu'en supprimant en cascade leurs connaissances, évaluations ou preuves. Les règles de permission sont appliquées par l'API Gateway **et** par les services sur leurs ressources. Le RBAC ne remplace pas à lui seul les règles de propriété ou de confidentialité par document.

## 6. Analyse 1NF / 2NF / 3NF : portée et réserves

- **1NF :** toutes les relations ont une clé et des colonnes typées ; les listes métier identifiées (dépendances de code, prérequis, objectifs, exemples, étapes de diagnostic) ont été externalisées. Les attributs textuels conservés sont supposés être des textes libres, et non des tableaux sérialisés.
- **2NF :** les tables à clés composites (`knowledge_tags`, `user_roles`, `role_permissions`, `compliance_standard_requirements`...) ne comportent aucun attribut supposé dépendre seulement d'une fraction de la clé primaire. Cela dépend des règles métier : `requirement_code`, `severity` et `mandatory` sont supposés caractériser une exigence **dans une édition de norme**, et non l'exigence de manière universelle.
- **3NF :** les entités de référence et leurs versions ont été distinguées ; les liens N:N sont explicites ; les dépendances indirectes identifiées ont été supprimées du modèle principal. Une preuve formelle de 3NF exige une revue des **clés candidates et des dépendances fonctionnelles métier** pour chaque relation : ce document est donc un **candidat 3NF**, non une certification mathématique automatique.

### Points d'arbitrage ouverts pour la prochaine revue

1. **Identité/versions RNCP** : confirmer si `title` et `certifier` sont invariants entre versions ; sinon les déplacer vers `certification_framework_versions`.
2. **Normes** : confirmer que `compliance_requirements` exprime une exigence métier réutilisable ; si le sens change à chaque édition, l'identité même de l'exigence doit être versionnée plutôt que seulement ses attributs contextuels.
3. **Association technologie** : décider si le lien générique `knowledge_technologies` est nécessaire en plus du lien versionné ; éviter le double enregistrement d'une relation identique.
4. **Comptes** : préciser l'authentification locale, OIDC ou mixte, ainsi que la gestion des utilisateurs désactivés et des permissions par connaissance/projet.
5. **Évaluations de compétences** : préciser si elles sont exclusivement personnelles ou si elles peuvent être réalisées pour plusieurs utilisateurs ; dans le second cas, ajouter un `subject_user_id` distinct de l'évaluateur.
6. **Preuves** : préciser si une preuve peut être rattachée à plusieurs projets ; le modèle actuel prévoit zéro ou un projet par preuve.
7. **RAG** : choisir si plusieurs configurations d'embedding et plusieurs index doivent coexister pour un même modèle ; leur identité mérite alors une entité de configuration.
8. **Durée et dates** : préciser les fuseaux, les versions à format libre ou sémantique, les valeurs autorisées pour les statuts et les niveaux de maîtrise.
9. **Documents techniques** : décider si les `framework`, `parameters`, `benefits`, `expected_deliverables` et autres textes sont des descriptions libres ou des ensembles structurés nécessitant des entités supplémentaires.

## 7. Correspondance avec le premier schéma

| Ancien nom / association | Nom actuel / traitement |
|---|---|
| `knowledges` | `knowledge_items` |
| `study_notes` | `course_notes` |
| `correspondre` | `knowledge_tags` |
| `associer` | `knowledge_technologies` |
| `emaner` | `knowledge_source_links` |
| `etre_constitue` | Suppression ; FK `procedure_steps.procedure_knowledge_id` |
| `etre_attache` | `knowledge_attachment_links` |
| `exister_en` | Suppression ; FK `knowledge_versions.knowledge_id` |
| `attendre` | `compliance_standard_requirements` |
| `repondre` | `compliance_assessment_results` |
| `lier`, `relier` | Suppression ; deux FK dans `knowledge_relations` |
| `code_snippets.dependencies` | `snippet_dependencies` |
| `technical_procedures.prerequisites` | `procedure_prerequisites` |
| `study_notes.study_name`, `module_name` | `courses`, `course_modules` |
| `study_notes.learning_objectives`, `examples` | `course_note_objectives`, `course_note_examples` |
| `bug_fixes.diagnostic_steps` | `bug_diagnostic_steps` |
| `knowledge_versions` ↔ RAG | `knowledge_chunks` référence `knowledge_versions.version_id` |
| `knowledge_chunks.embedding_id`, `embedding_model`, `indexed_at` | `chunk_embeddings` |
| `knowledge_items.created_by`, etc. | Clés étrangères vers `users.user_id` |

## 8. Périmètre de livraison et suite du projet

- **À ce stade** : MLD textuel à relire, sans SQL, sans migration MongoDB et sans changement du dépôt.
- **Après ta validation** : documenter les dépendances fonctionnelles et cardinalités définitives, établir le dictionnaire des données, puis traduire ce modèle en collections/index MongoDB et modèles Pydantic du `knowledge-service`.
- **Pour Codex** : utiliser cette note comme source métier ; faire implémenter de manière incrémentale, avec tests pytest, contrôle des permissions et aucun changement non validé des services existants.

