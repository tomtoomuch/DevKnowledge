---
title: "DevKnowledge — Itération 7 : classification par tags"
date: "2026-11-09"
status: "PR #9 en cours ; fusion conditionnée à la CI"
tags: [devknowledge, classification, mongodb, angular, securite]
---

# Itération 7 — tags réutilisables

## Modèle métier

Le MLD v0.2 propose les tables logiques `tags` et `knowledge_tags`.
Le présent lot conserve `tags` comme collection MongoDB autonome, mais
projette `knowledge_tags` sous forme de `knowledge_items.tag_ids` (UUID
sérialisés en chaînes) : une seule écriture conditionnelle `If-Match`
modifie les tags et les autres propriétés de la connaissance.

Les documents antérieurs à cette évolution ne comportent pas forcément
`tag_ids`; le schéma expose alors un tableau vide sans migration des
enregistrements. Le catalogue des tags n'est pas effacé lors d'une suppression
logique de connaissance.

### Collection `tags`

```text
_id      string UUID (clé primaire)
name     string, 1 à 100 caractères après normalisation NFKC + trim
name_key string, name.casefold(), index UNIQUE
```

Les noms ne contiennent pas de données utilisateur sensibles dans des
journaux ; les exceptions de duplication ne divulguent pas les détails Mongo.
Le catalogue est **créable et consultable**, mais ni modifiable ni
supprimable à ce stade pour préserver les références.

### Relation `tag_ids`

- `tag_ids` : maximum 30 UUID distincts, tableau facultatif sur création,
  tableau vide pour supprimer tous les liens sur PATCH.
- Les identifiants doivent correspondre à des entrées réellement présentes
  dans `tags` ; références inconnues rejetées HTTP 422.
- `PATCH` et `DELETE` respectent `If-Match`, avec réponses 428/412.
- Les liens sont atomiquement remplacés avec les autres propriétés de
  `knowledge_items`, sans transactions distribuées.

## API et permissions

| Route | Rôle métier | Validation |
| --- | --- | --- |
| `GET /api/v1/tags?skip=0&limit=100` | knowledge.read | Pagination stable par nom |
| `GET /api/v1/tags/{tag_id}` | knowledge.read | 404 si absent |
| `POST /api/v1/tags` | knowledge.create | 201, 409 si nom en doublon, 422 si invalide |
| `POST /api/v1/knowledges` avec `tag_ids` | knowledge.create | 201, 422 si références inconnues |
| `PATCH /api/v1/knowledges/{id}` avec `tag_ids` | knowledge.update | If-Match obligatoire ; ETag incrémenté |
| `GET /api/v1/knowledges?tag_id={uuid}` | knowledge.read | Filtre combinable avant pagination |

Seul le KMS valide le RBAC et l'intégrité métier ; Angular ne fait que
masquer les contrôles en fonction des permissions. La Gateway ne relaie
que les routes du catalogue nécessaires, sans exposer le KMS directement.

## Frontend

Le frontend existant sous `frontend/ui-app/` propose la création de tags,
la sélection multiple, l'affichage des libellés et un filtre serveur. Le
catalogue est chargé au maximum à 100 entrées ; une pagination et une
recherche dédiée à l'administration restent nécessaires. La création d'un
tag est persistée immédiatement dans le catalogue, même si l'édition de
la connaissance est ensuite annulée ; l'interface le précise.

## Limites et suite

1. Les six entités de classification du MLD ne sont pas toutes implémentées :
   `technologies` et versions sont au prochain lot.
2. Les tags ne sont pas supprimables/renommables dans cette version, ce qui
   préserve les références mais laisse la gestion du catalogue incomplète.
3. Les filtres `tag_id` fonctionnent sur l'ensemble des connaissances
   actives, mais l'index de requête `knowledge_items.tag_ids` devra être
   envisagé selon la taille du corpus et le profil de requêtes.
4. Le script existant `scripts/mongodb_backup.py` sauvegarde **toutes**
   les collections de la base (y compris `tags`) et vérifie les index et
   documents restaurés dans un volume jetable. Ne pas remplacer cette
   procédure par une exportation limitée à `knowledge_items` : les
   références de tags perdraient alors leurs libellés.
5. Une recette manuelle est encore nécessaire après la CI, sur base jetable
   ou sauvegardée ; aucune donnée locale n'a été migrée ni supprimée.
