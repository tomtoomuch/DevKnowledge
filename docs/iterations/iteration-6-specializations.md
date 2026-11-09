---
title: "DevKnowledge — Itération 6 : CRUD des spécialités"
updated: "2026-11-09"
status: "Implémentation en PR #8, validation CI et recette en cours"
tags: [devknowledge, knowledge, mongodb, angular, modelisation]
---

# Itération 6 — CRUD des spécialisations métier

## Référence et périmètre

Le MLD candidat 3NF v0.2 définit huit spécialisations rattachées à
`knowledge_items` : `code_snippets`, `terminal_commands`,
`technical_procedures`, `course_notes`, `bug_fixes`,
`documentation_resources`, `best_practices` et
`compliance_standards`. Le présent lot implémente **leurs attributs** et la
validation métier, mais **pas huit collections MongoDB indépendantes**.

## Projection physique retenue

```text
MongoDB
├── knowledge_items
│   ├── _id: UUID en chaîne
│   ├── knowledge_type: code du type
│   ├── champs génériques (title, content, revision, deleted_at, etc.)
│   └── details: sous-document facultatif propre au type
└── knowledge_types
    ├── _id: UUID stable
    ├── code: unique
    ├── label
    ├── schema_version: 1
    └── required_fields
```

Le sous-document réduit les écritures multi-collections à un seul document
MongoDB : `PATCH` et la révision `If-Match` restent atomiques, y compris
lors d'un changement de type. Cette projection ne modifie pas les anciennes
connaissances ; une valeur `details` absente reste valide. Un changement
de catégorie sans nouveaux détails supprime les détails incompatibles.

Le référentiel est créé ou réconcilié de manière idempotente au démarrage
dans `knowledge_types`. Les données métier existantes ne sont pas recréées
et aucun volume n'est réinitialisé.

## API et autorisations

Les routes génériques `POST /api/v1/knowledges`,
`GET /api/v1/knowledges/{id}`, `PATCH /api/v1/knowledges/{id}`
et `DELETE /api/v1/knowledges/{id}` sont conservées.

- `details` sur POST : dictionnaire facultatif ; lorsqu'il est fourni,
  validé contre le schéma du `knowledge_type`.
- `details` sur PATCH : remplacement entier du dictionnaire ; `null` pour
  retirer les données spécialisées ; les changements de catégorie sont
  validés avec la révision courante.
- `GET /api/v1/knowledge-types` : consultation du catalogue, protégée
  par la permission `knowledge.read`, relayée par la Gateway.

Les rôles `ADMIN`, `EDITOR`, `READER` conservent leurs droits existants ;
le serveur applique le RBAC, indépendamment de l'interface.

## Frontend

Toutes les sources Angular se trouvent dans `frontend/ui-app/`. L'éditeur
unique propose un formulaire réactif par type, les champs requis,
dates et nombres typés, ainsi que des options booléennes à trois états
(non renseigné / oui / non). La vue de détail expose ces propriétés.
Une fiche historique sans `details` reste en mode générique ; l'utilisateur
peut activer les détails ultérieurement.

## Limites et travaux à poursuivre

- Les associations de type `procedure_steps`, `courses`,
  `snippet_dependencies`, `knowledge_tags`, `knowledge_sources`,
  etc. ne sont pas encore implémentées.
- Les champs `module_id` et `reference_standard_id` sont validés au format
  UUID, mais l'existence des références et leurs cardinalités ne sont pas
  encore contrôlées.
- Aucun référentiel versionné, historique de contenus, migration d'anciens
  documents, import/export ou index de recherche sur `details`.
- Les URL documentaires sont des chaînes déclaratives ; pas de téléchargement
  automatique ni de validation réseau.
- Tests unitaires et tests MongoDB jetables prévus en CI ; ne pas confondre
  leur réussite avec une recette utilisateur sur les données locales.

## Critères de validation

CI frontend/KMS/Gateway/Docker verte ; création et édition des huit types ;
conflits 412 et entrées invalides 422 ; affichage et sérialisation des champs ;
absence de régression sur les anciennes fiches ; aucun fichier Angular à la
racine de `frontend/` ; aucune suppression de volume de développement.
