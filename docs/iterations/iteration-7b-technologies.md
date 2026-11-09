---
title: "DevKnowledge — Itération 7B : technologies et versions"
date: "2026-11-10"
status: "PR #10 en revue, basée sur feature/knowledge-tags (PR #9)"
tags: [devknowledge, classification, technologies, mongodb, angular]
---

# Itération 7B — Technologies et versions

## Objectif métier et séquencement

Compléter les six tables logiques de classification du MLD 3NF v0.2 après le
lot A (tags) et sans anticiper le domaine « Relations entre connaissances ».
Cette PR (#10) est **empilée sur la branche `feature/knowledge-tags`**,
elle-même la source de la PR #9 vers `chat` : les dépendances doivent être
fusionnées dans le bon ordre et leurs branches de base actualisées.

## Traduction physique MongoDB

| Entité logique MLD v0.2 | Stockage MongoDB |
| --- | --- |
| `technologies` | Collection `technologies` |
| `technology_versions` | Collection `technology_versions` |
| `knowledge_technologies` | `knowledge_items.technology_ids` (tableau UUID) |
| `knowledge_technology_versions` | `knowledge_items.technology_version_ids` (tableau UUID) |

Les références sont en chaînes UUID, comme dans les tags ; le KMS les
reconstitue en `UUID` à la lecture. Les listes sont facultatives sur les
enregistrements historiques et apparaissent vides dans l'API, sans migration.

### Technologies

```text
technologies:
  _id      UUID sérialisé (string)
  name     1–100 caractères normalisés NFKC/trim
  name_key name.casefold() (index UNIQUE)
  category VARCHAR(100) facultatif
```

### Versions

```text
technology_versions:
  _id           UUID sérialisé (string)
  technology_id UUID sérialisé (string, parent obligatoire)
  version       1–50 caractères normalisés NFKC/trim
  version_key   version.casefold()
  release_date  date ISO YYYY-MM-DD ou null
```

Contrainte d'unicité composée `(technology_id, version_key)`. Le type date
est encodé en chaîne ISO car MongoDB BSON ne possède pas de date sans heure.
Le KMS valide son format (Pydantic `date`).

Les catalogues étant **immuables** (création + lecture seulement), le KMS
peut vérifier les références avant l'écriture atomique de la connaissance
sans risque de suppression concurrente. Dans la première itération, il n'y a
pas de renommage et suppression ; aucun recodage destructif de données.

## Règles d'intégrité

- `technology_ids` et `technology_version_ids` : listes d'UUID distincts,
  30 identifiants maximum par liste.
- Chaque identifiant doit correspondre à une technologie ou version existante.
  Les identifiants inconnus donnent HTTP 422.
- Le même parent technologique ne doit **pas** être associé simultanément
  de manière générique et au travers d'une ou plusieurs versions précises.
  Exemple : `Python` + `Python 3.14` est refusé, mais `Docker` générique
  + `Python 3.14` est accepté.
- Un `PATCH` ne modifiant qu'une seule liste est comparé à la valeur
  persistée de l'autre liste ; l'écriture reste soumise à `If-Match`
  (`412` si révision concurrente). Un `PATCH` portant les deux listes
  peut remplacer les associations en une seule opération MongoDB.
- La suppression d'une connaissance reste logique ; aucune opération de
  suppression ne touche les catalogues partagés.

## Contrat HTTP et permissions

| Méthode/route | Permission | Remarques |
| --- | --- | --- |
| `GET /api/v1/technologies` | knowledge.read | `skip` ≥ 0, `limit` 1–100 |
| `GET /api/v1/technologies/{UUID}` | knowledge.read | 404 si absent |
| `POST /api/v1/technologies` | knowledge.create | 201 ou 409 doublon |
| `GET /api/v1/technology-versions` | knowledge.read | Filtre facultatif `technology_id` |
| `GET /api/v1/technology-versions/{UUID}` | knowledge.read | 404 si absent |
| `POST /api/v1/technology-versions` | knowledge.create | 201, 409 doublon, 422 parent inconnu |
| `POST/PATCH /api/v1/knowledges` | knowledge.create/update | Champs `technology_ids`, `technology_version_ids` |
| `GET /api/v1/knowledges?technology_id=UUID` | knowledge.read | Filtre **générique uniquement** |
| `GET /api/v1/knowledges?technology_version_id=UUID` | knowledge.read | Filtre **version précise uniquement** |

Les filtres sur les connaissances sont combinables avec tags, texte,
type, statut et favoris. La Gateway Express n'expose que GET et POST du
catalogue : pas de DELETE/PATCH/PUT, et aucune identité supplémentaire
n'est diffusée. La source de vérité RBAC reste dans le KMS.

## Interface Angular

L'interface est exclusivement sous `frontend/ui-app/`.
Elle permet la création des deux références, la sélection des relations
génériques ou versionnées, l'affichage des associations et les filtres.
Elle élimine automatiquement les choix incompatibles lorsqu'elle connaît
le parent technologique de la version sélectionnée.

L'API pagine les catalogues ; l'éditeur charge uniquement les 100 premières
technologies et 100 premières versions pour le moment. Un catalogue
volumineux requiert une recherche asynchrone et une résolution des UUID
en dehors de la page initiale.

## Tests, sauvegarde et sortie

- Unitaires : validation normalisation, formats dates, doublons, RBAC,
  contrats API, filtres et structures UUID.
- Intégration réelle sur MongoDB jetable : indexes uniques, références
  manquantes, doublon sémantique, association atomique avec ETag, conflits
  de révision, lecture d'anciennes fiches et suppression logique.
- Frontend : services API, contrôle du filtrage et compilation Angular.
- La sauvegarde de `scripts/mongodb_backup.py` englobe **toutes**
  les collections : elle inclut donc technologies, versions, tags et index.

Avant fusion, vérifier la CI complète et mener la recette manuelle sur une
base sauvegardée ou jetable. Aucun volume de développement n'est modifié
par ces tests CI.
