# DevKnowledge — Récapitulatif global des modèles de données

Voici la synthèse consolidée de notre conception, en intégrant les évolutions successives :

- Les 8 catégories de connaissances ;
- le socle commun de gestion des connaissances ;
- les tables transversales ;
- le domaine Conformités, standards et réglementations ;
- le référentiel de certification RNCP 37827 ;
- le système de rapprochement des compétences et de gestion des preuves.
Je te propose de considérer cette version comme notre référentiel de conception du modèle de données DevKnowledge, avant de passer à la production du schéma SQL.

## 1. Vue d'ensemble de l'architecture

Le modèle est organisé en cinq domaines fonctionnels.

| Domaine | Intitulé | Contenu |
| --- | --- | --- |
| 1 | Gestion des connaissances | `knowledge_items` et les 8 modèles spécialisés. |
| 2 | Classification et relations | Tags, technologies, sources, pièces jointes, versions et relations entre connaissances. |
| 3 | Conformité et réglementation | Référentiels, exigences et évaluations de conformité. |
| 4 | Certification et compétences | RNCP, blocs de compétences, compétences individuelles, critères et évaluations. |
| 5 | Preuves et intelligence documentaire | Preuves de réalisation, associations aux compétences, fragments RAG et index vectoriels. |

## 2. Domaine 1 — Gestion des connaissances

### 2.1. Table centrale : `knowledge_items`

 C'est le point d'entrée de toutes les connaissances.

| Champ | Description |
| --- | --- |
| `id` | Identifiant UUID |
| `title` | Titre |
| `description` | Résumé |
| `knowledge_type` | Type de connaissance |
| `content` | Contenu textuel principal |
| `language` | Langue |
| `difficulty_level` | Niveau technique |
| `status` | Brouillon, validé, archivé |
| `created_at` | Date de création |
| `updated_at` | Dernière modification |
| `validated_at` | Date de validation |
| `created_by` | Auteur |
| `is_favorite` | Favori |

### 2.2. Les huit modèles spécialisés

Chaque modèle spécialisé possède une relation 1:1 avec `knowledge_items`, via `knowledge_id`, qui constitue sa clé primaire et sa clé étrangère.

| N° | Type de connaissance | Table | Fonction |
| --- | --- | --- | --- |
| 1 | Code snippets | `code_snippets` | Code source réutilisable |
| 2 | Commandes terminal | `terminal_commands` | Commandes CLI et systèmes |
| 3 | Procédures techniques | `technical_procedures` | Guides opératoires |
| 4 | Notes de cours | `course_notes` | Concepts et apprentissages |
| 5 | Résolutions de bugs | `bug_fixes` | Diagnostics et corrections |
| 6 | Ressources documentaires | `documentation_resources` | Documentation et références externes |
| 7 | Bonnes pratiques | `best_practices` | Recommandations et conventions |
| 8 | Conformités, standards et réglementations | `compliance_standards` | Référentiels et exigences réglementaires |

#### Champs spécifiques par modèle

| Table | Principaux champs |
| --- | --- |
| `code_snippets` | `code`, `language`, `framework`, `version`, `entry_point`, `dependencies`, `input_example`, `output_example`, `execution_context`, `is_executable`, `license` |
| `terminal_commands` | `command`, `shell`, `operating_system`, `working_directory`, `parameters`, `expected_output`, `risk_level`, `requires_sudo`, `is_destructive`, `execution_notes` |
| `technical_procedures` | `objective`, `prerequisites`, `environment`, `estimated_duration`, `difficulty`, `rollback_procedure`, `validation_criteria` |
| `course_notes` | `course_name`, `module_name`, `concept`, `definition`, `explanation`, `examples`, `learning_objectives`, `source_reference`, `mastery_level` |
| `bug_fixes` | `error_title`, `error_message`, `error_code`, `symptoms`, `root_cause`, `diagnostic_steps`, `solution`, `code_before`, `code_after`, `environment`, `resolution_status`, `verified_at` |
| `documentation_resources` | `url`, `resource_type`, `publisher`, `publication_date`, `accessed_at`, `version_reference`, `summary`, `reliability_level`, `is_official` |
| `best_practices` | `principle`, `rationale`, `recommendation`, `anti_pattern`, `benefits`, `application_context`, `reference_standard`, `validation_criteria` |
| `compliance_standards` | `reference_code`, `title`, `compliance_type`, `issuing_organization`, `jurisdiction`, `scope`, `description`, `applicability`, `publication_date`, `effective_date`, `review_date`, `expiration_date`, `official_url`, `version_reference` |

### 2.3. Tables complémentaires aux procédures

Une procédure peut contenir plusieurs étapes ordonnées.

| Table | Principaux champs | Fonction |
| --- | --- | --- |
| `procedure_steps` | `id`, `procedure_id`, `step_order`, `title`, `instructions`, `expected_result`, `command` | Décomposer une procédure en étapes |

## 3. Domaine 2 — Classification et relations transversales

Ces tables permettent d'organiser les connaissances indépendamment de leur catégorie.

| Table | Principaux champs | Fonction |
| --- | --- | --- |
| `tags` | `id`, `name` | Référentiel des étiquettes |
| `knowledge_tags` | `knowledge_id`, `tag_id` | Association N:N connaissances / tags |
| `technologies` | `id`, `name`, `category`, `version` | Référentiel des technologies |
| `knowledge_technologies` | `knowledge_id`, `technology_id` | Association N:N connaissances / technologies |
| `knowledge_relations` | `id`, `source_id`, `target_id`, `relation_type` | Relations entre connaissances |
| `knowledge_sources` | `id`, `knowledge_id`, `source_reference` | Traçabilité des origines |
| `knowledge_attachments` | `id`, `knowledge_id`, `file_path`, `mime_type` | Fichiers associés |
| `knowledge_versions` | `id`, `knowledge_id`, `version_number`, `content_snapshot` | Historique des versions |

### Relations sémantiques envisagées

La table `knowledge_relations` pourra notamment gérer :

| Relation | Signification |
| --- | --- |
| `RELATED_TO` | Deux connaissances sont liées |
| `SOLVES` | Une connaissance résout un problème |
| `REQUIRES` | Une connaissance nécessite une autre |
| `EXPLAINS` | Une connaissance explique un concept |
| `REFERENCES` | Une connaissance fait référence à une autre |
| `IMPROVES` | Une connaissance améliore une autre |

Exemple : une procédure Docker peut nécessiter une commande terminal et être documentée par une ressource officielle.

## 4. Domaine 3 — Conformités, standards et réglementations

Ce domaine complète la huitième catégorie de connaissances.

Il doit permettre de distinguer le référentiel lui-même, ses exigences et l'évaluation de son application dans un projet.

| Table | Principaux champs | Fonction |
| --- | --- | --- |
| `compliance_standards` | `knowledge_id`, `reference_code`, `compliance_type`, `issuing_organization`, `jurisdiction`, `version_reference`, `effective_date`, `official_url` | Référentiels et normes |
| `compliance_requirements` | `id`, `knowledge_id`, `requirement_code`, `title`, `description`, `severity`, `mandatory`, `verification_method`, `implementation_guidance` | Exigences individualisées |
| `compliance_assessments` | `id`, `requirement_id`, `project_id`, `assessment_status`, `assessment_date`, `assessment_notes`, `evidence_reference`, `assessed_by`, `next_review_date` | Évaluation de conformité |

### Exemples de référentiels

- RGPD
- ISO/IEC 27001
- OWASP ASVS
- OWASP Top 10
- AI Act européen
- NIS2
- OAuth 2.0
- OpenAPI
Une précision de conception : tous ces éléments n'ont pas la même portée juridique. Par exemple, OAuth 2.0 est un standard technique, tandis que le RGPD est un règlement. Le champ `compliance_type` doit préserver cette distinction.

### Une table métier supplémentaire : `projects`

Elle devient nécessaire pour rattacher les évaluations de conformité aux projets.

| Champ | Type | Fonction |
| --- | --- | --- |
| `id` | UUID | Identifiant |
| `name` | VARCHAR | Nom du projet |
| `description` | TEXT | Présentation |
| `repository_url` | TEXT | Dépôt Git |
| `project_status` | VARCHAR | État du projet |
| `created_at` | DATETIME | Date de création |
| `updated_at` | DATETIME | Date de modification |

Cette table sera également utile au domaine certification et preuves.

## 5. Domaine 4 — Certification et référentiels de compétences

Ce domaine permettra à DevKnowledge de gérer plusieurs référentiels de certification, le RNCP 37827 étant le premier.

### 5.1. Les tables du référentiel

| Table | Principaux champs | Fonction |
| --- | --- | --- |
| `certification_frameworks` | `id`, `code`, `title`, `certifier`, `qualification_level`, `version`, `registration_date`, `expiration_date`, `source_url`, `retrieved_at` | Référentiel de certification |
| `certification_blocks` | `id`, `framework_id`, `block_code`, `title`, `description`, `evaluation_method` | Blocs de compétences |
| `certification_competencies` | `id`, `block_id`, `competency_code`, `official_description`, `operational_description`, `expected_deliverables`, `evaluation_method`, `is_mandatory` | Compétences individuelles |
| `assessment_criteria` | `id`, `competency_id`, `criterion_code`, `description` | Critères d'évaluation |

### 5.2. Tables de rapprochement

| Table | Principaux champs | Fonction |
| --- | --- | --- |
| `knowledge_competency_links` | `id`, `knowledge_id`, `competency_id`, `relevance_level`, `mapping_rationale`, `confidence_score`, `created_at` | Rapprochement connaissances / compétences |

Cette table permet une relation N:N.

Une connaissance peut contribuer à plusieurs compétences et une compétence peut être associée à plusieurs connaissances.

### 5.3. Évaluation de la maîtrise

| Table | Principaux champs | Fonction |
| --- | --- | --- |
| `competency_assessments` | `id`, `competency_id`, `assessment_level`, `assessment_source`, `assessment_date`, `strengths`, `gaps`, `improvement_plan` | Suivi de la progression individuelle |

Les niveaux de progression envisagés :

1. Non étudiée.
2. Connaissance théorique acquise.
3. Mise en pratique réalisée.
4. Preuves disponibles.
5. Dossier prêt à présenter.
6. Évaluée par un formateur.
7. Validée officiellement.
La validation officielle doit rester distincte de l'auto-évaluation.

## 6. Domaine 5 — Preuves et réalisations

| Champ | Description |
| --- | --- |
| `evidence_type` | Type de preuve |
| `demonstration_url` | Démonstration |
| `author_role` | Rôle personnel |
| `evidence_id` | Preuve associée |
| `evidence_role` | Principale ou complémentaire |
| `demonstrated_aspects` | Éléments démontrés |
 C'est le domaine qui donnera à DevKnowledge sa capacité à t'accompagner dans la constitution de ton dossier de certification.

### 6.1. Table `evidence_artifacts`

Elle centralise les preuves concrètes issues de tes projets.

| Champ | Description |
| --- | --- |
| `id` | Identifiant UUID |
| `title` | Titre de la preuve |
| `description` | Description de ce qui est démontré |
| `evidence_type` | Type de preuve |
| `project_id` | Projet associé |
| `file_path` | Emplacement du fichier |
| `repository_url` | Dépôt Git |
| `commit_hash` | Commit associé |
| `demonstration_url` | Démonstration |
| `author_role` | Rôle personnel |
| `created_at` | Date de réalisation |
| `verification_status` | État de vérification |
| `verification_notes` | Commentaires |

#### Types de preuves

| Code | Type |
| --- | --- |
| `SOURCE_CODE` | Code source |
| `UNIT_TEST` | Test unitaire |
| `INTEGRATION_TEST` | Test d'intégration |
| `TECHNICAL_DOCUMENTATION` | Documentation technique |
| `ARCHITECTURE_DIAGRAM` | Diagramme d'architecture |
| `DATABASE_SCHEMA` | Schéma de base de données |
| `API_DOCUMENTATION` | Documentation API |
| `CI_CD_PIPELINE` | Pipeline CI/CD |
| `SCREENSHOT` | Capture d'écran |
| `VIDEO_DEMO` | Démonstration vidéo |
| `PROFESSIONAL_REPORT` | Rapport professionnel |
| `INCIDENT_REPORT` | Rapport d'incident |
| `BENCHMARK` | Étude comparative |

### 6.2. Table `competency_evidence`

Elle associe les preuves aux compétences qu'elles démontrent.

| Champ | Description |
| --- | --- |
| `id` | Identifiant |
| `competency_id` | Compétence visée |
| `evidence_id` | Preuve associée |
| `evidence_role` | Principale ou complémentaire |
| `demonstrated_aspects` | Éléments démontrés |
| `limitations` | Limites de la preuve |
| `review_status` | À examiner, recevable, insuffisante |

Une même preuve peut contribuer à plusieurs compétences.

Exemple : un pipeline GitHub Actions peut constituer une preuve pour une compétence de livraison continue en MLOps et une compétence de livraison continue applicative, à condition de démontrer effectivement les deux aspects.

## 7. Domaine 6 — Intelligence documentaire et RAG

Je distingue ici les données métier de la couche technique d'indexation.

| Table | Principaux champs | Fonction |
| --- | --- | --- |
| `knowledge_chunks` | `id`, `knowledge_id`, `chunk_index`, `chunk_content`, `token_count`, `embedding_id`, `embedding_model`, `indexed_at` | Fragments documentaires |

Cette table permettra de découper les connaissances en fragments exploitables par le moteur RAG.

### Stockage vectoriel

Les embeddings seront conservés dans une base vectorielle dédiée, indépendamment de la base relationnelle.

- ChromaDB pour la recherche vectorielle ;
- un modèle d'embedding local ;
- une référence `embedding_id` pour relier le fragment à son vecteur.
Le modèle relationnel conserve donc la traçabilité et les métadonnées, tandis que le stockage vectoriel gère la recherche sémantique.

## 8. Inventaire général des tables

Voici le catalogue consolidé de toutes les tables envisagées.

### 30 tables conceptuelles

| N° | Domaine | Table |
| --- | --- | --- |
| 01 | Connaissances | `knowledge_items` |
| 02 | Connaissances | `code_snippets` |
| 03 | Connaissances | `terminal_commands` |
| 04 | Connaissances | `technical_procedures` |
| 05 | Connaissances | `course_notes` |
| 06 | Connaissances | `bug_fixes` |
| 07 | Connaissances | `documentation_resources` |
| 08 | Connaissances | `best_practices` |
| 09 | Connaissances | `compliance_standards` |
| 10 | Procédures | `procedure_steps` |
| 11 | Classification | `tags` |
| 12 | Classification | `knowledge_tags` |
| 13 | Classification | `technologies` |
| 14 | Classification | `knowledge_technologies` |
| 15 | Relations | `knowledge_relations` |
| 16 | Traçabilité | `knowledge_sources` |
| 17 | Traçabilité | `knowledge_attachments` |
| 18 | Traçabilité | `knowledge_versions` |
| 19 | Conformité | `compliance_requirements` |
| 20 | Conformité | `compliance_assessments` |
| 21 | Projets | `projects` |
| 22 | Certification | `certification_frameworks` |
| 23 | Certification | `certification_blocks` |
| 24 | Certification | `certification_competencies` |
| 25 | Certification | `assessment_criteria` |
| 26 | Certification | `knowledge_competency_links` |
| 27 | Certification | `competency_assessments` |
| 28 | Preuves | `evidence_artifacts` |
| 29 | Preuves | `competency_evidence` |
| 30 | RAG | `knowledge_chunks` |

La base vectorielle constitue une infrastructure complémentaire, et non une table relationnelle supplémentaire.

## 9. Relations structurantes

Voici les grandes relations qui doivent guider la conception SQL :

| Relation | Cardinalité |
| --- | --- |
| Knowledge → modèle spécialisé | 1:1 |
| Knowledge → tags | N:N |
| Knowledge → technologies | N:N |
| Knowledge → knowledge | N:N |
| Procédure → étapes | 1:N |
| Knowledge → versions | 1:N |
| Knowledge → pièces jointes | 1:N |
| Standard → exigences | 1:N |
| Exigence → évaluations | 1:N |
| Projet → évaluations de conformité | 1:N |
| Référentiel → blocs | 1:N |
| Bloc → compétences | 1:N |
| Knowledge → compétences | N:N |
| Compétence → preuves | N:N |
| Compétence → évaluations | 1:N |
| Knowledge → chunks | 1:N |

## 10. Quelques décisions à stabiliser avant le SQL

Je souhaite attirer ton attention sur quatre points qui méritent d'être arbitrés.

### 1. Gestion des utilisateurs

Les champs `created_by`, `assessed_by` et `author_role` impliquent une gestion des utilisateurs. Nous pouvons rattacher les identifiants au service d'identité OAuth/OIDC, sans nécessairement créer une table utilisateurs dans la base métier.

### 2. Gestion des sources

- `knowledge_sources` : provenance d'une connaissance, quelle qu'en soit la nature ;
- `documentation_resources` : connaissance dont la nature même est une ressource documentaire.
Il faudra éviter de dupliquer inutilement les mêmes métadonnées.

### 3. Gestion des preuves

Je recommande de rattacher systématiquement les preuves à un projet et de conserver les références Git, les commits et les versions des livrables. C'est important pour démontrer ton implication personnelle.

### 4. Gestion des versions réglementaires et RNCP

Un référentiel doit conserver son historique. Une évolution du RGPD, d'une norme ISO ou du RNCP ne doit pas modifier rétroactivement les évaluations réalisées sur une version antérieure.

## 11. Ordre de construction recommandé

Je ne créerais pas les 30 tables dès le premier sprint.

| Phase | Tables / fonctionnalités | Objectif |
| --- | --- | --- |
| P0 | `projects`, `knowledge_items`, 8 modèles spécialisés | Socle métier |
| P1 | Tags, technologies, sources, relations, versions, pièces jointes | Enrichissement |
| P2 | Tables de certification et critères | Import RNCP |
| P3 | Preuves, rapprochements et évaluations | Cartographie des compétences |
| P4 | Conformité et exigences réglementaires | Gouvernance |
| P5 | Chunks et base vectorielle | RAG |
| P6 | API, tableaux de bord et automatisation IA | Exploitation |

## 12. Ma recommandation finale

Je considère que nous avons désormais une architecture conceptuelle suffisamment structurée pour passer à une véritable conception relationnelle.

Je souhaite néanmoins préserver trois principes fondamentaux de DevKnowledge :

- **Indépendance des connaissances** : une connaissance ne doit jamais dépendre d'une certification pour exister ;
- **Traçabilité** : chaque connaissance, réalisation et preuve doit avoir une provenance identifiable ;
- **Évolutivité** : le RNCP 37827 est le premier référentiel, pas une contrainte permanente de l'architecture.
La prochaine étape logique serait de produire le modèle conceptuel de données (MCD), puis le modèle logique de données (MLD), avant d'écrire les scripts SQL de création.

Cela nous permettra de vérifier les cardinalités, les dépendances fonctionnelles, les clés primaires, les clés étrangères et la normalisation avant toute implémentation.

Je te conseille de valider ce catalogue de 30 tables comme base de travail, puis de construire le MCD global de DevKnowledge.