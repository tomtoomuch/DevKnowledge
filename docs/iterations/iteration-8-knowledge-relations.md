---
title: "DevKnowledge — Itération 8 : relations entre connaissances"
date: "2026-11-10"
status: "PR #11 en cours ; validation CI et recette manuelle requises"
tags: [devknowledge, relations, graphe, mongodb, angular]
---

# Itération 8 — Relations entre connaissances (MLD v0.2, domaine E)

## Modèle et stockage

Le MLD 3NF v0.2 prévoit deux tables logiques, directement matérialisées
comme deux **collections MongoDB distinctes** :

```text
relation_types:
  _id UUID sérialisé, PK
  code string UNIQUE
  label string
  is_directed bool

knowledge_relations:
  _id UUID sérialisé, PK
  origin_knowledge_id UUID sérialisé, FK logique
  target_knowledge_id UUID sérialisé, FK logique
  relation_type_id UUID sérialisé, FK logique
  relation_notes string facultative, max 4000 caractères
  relation_key string UNIQUE (type + paire canonique)
  revision int (initial 1)
  created_at UTC datetime
  updated_at UTC datetime
```

La collection des types est initialisée idempotemment au démarrage avec
des identifiants stables UUIDv5, préservés entre les démarrages. Ce catalogue
est immuable à ce stade. Les références vers les connaissances sont contrôlées
à la création pour interdire les nœuds inconnus ou supprimés logiquement.

## Types de relation initiaux

| Code | Direction | Sens métier |
| --- | --- | --- |
| `DEPENDS_ON` | Orienté | A dépend de B |
| `COMPLEMENTS` | Non orienté | A et B se complètent |
| `CONTRADICTS` | Non orienté | A et B expriment des informations contradictoires |
| `SUPERSEDES` | Orienté | A remplace B |
| `RELATED_TO` | Non orienté | A et B sont en rapport |

Pour les relations non orientées, les UUID des deux connaissances sont
stockés dans l'ordre croissant ; l'index `relation_key` unique empêche
qu'une relation `A↔B` soit créée deux fois avec le même type, même lorsque
les requêtes ont des ordres inverses. Les relations orientées
`A→B` et `B→A` peuvent coexister : leur clé respecte l'ordre.

Les auto-relations sont rejetées HTTP 422.

## API (point d'entrée Gateway)

| Route | Permission | Réponse |
| --- | --- | --- |
| GET `/api/v1/relation-types` | knowledge.read | Types et orientation |
| GET `/api/v1/knowledge-relations?knowledge_id=UUID` | knowledge.read | Liens entrants et sortants, total et pagination |
| POST `/api/v1/knowledge-relations` | knowledge.create | 201 + ETag ; 409 doublon ; 422 référence invalide |
| GET `/api/v1/knowledge-relations/{uuid}` | knowledge.read | Relation + ETag |
| PATCH `/api/v1/knowledge-relations/{uuid}` | knowledge.update | Remplacement de `relation_notes` seulement, ETag obligatoire |
| DELETE `/api/v1/knowledge-relations/{uuid}` | knowledge.delete | Suppression **du lien uniquement**, 204, ETag obligatoire |

Les champs origine, cible et type sont immuables après création : pour
changer ces attributs, il faut supprimer puis recréer une relation.
Les erreurs 428 (absence d'ETag), 400 (format invalide) et 412 (révision
dépassée) utilisent le même contrat que le CRUD KMS existant.
Les changements de notes se font par `find_one_and_update` avec vérification
atomique de révision ; la suppression utilise `delete_one` avec révision.

Les définitions de catalogues et leurs écritures sont privées au KMS ;
le navigateur ne se connecte jamais directement à MongoDB ou FastAPI.

## Limites de l'intégrité sur MongoDB autonome

- La vérification de l'existence des deux fiches actives est préalable
  à `insert_one` ; une suppression logique *concurrente* peut survenir
  entre ces opérations. Une transaction multi-documents ou une stratégie
  d'application plus stricte sera nécessaire si les garanties doivent
  évoluer.
- La suppression logique d'une connaissance ne supprime pas les liens
  existants, pour éviter une suppression de données involontaire. La liste
  de liens depuis une connaissance supprimée renvoie HTTP 404 ;
  depuis une autre fiche active, ces liens peuvent encore apparaître avec
  un UUID de cible devenu inaccessible. Une politique de conservation,
  signalement et nettoyage reste à définir.
- Ce lot n'implémente pas de détection de cycles `DEPENDS_ON`, ni de
  graphe de dépendances transitives ou recherche par chemin.
- Le catalogue initial est figé (pas d'édition des types depuis l'UI).

## Angular et recette

Le composant autonome `knowledge-relations.component` vit sous
`frontend/ui-app/src/app/components/`. La vue d'une connaissance expose
son UUID, le catalogue de types, les relations paginées entrantes et
sortantes, ainsi que la création d'un lien depuis l'UUID de l'autre
connaissance. Les droits locaux conditionnent la création, l'annotation
et la suppression. La liste distingue les sens pour les liens dirigés.
La navigation vers le nœud voisin utilise la vue de connaissances
existante.

Recette à réaliser sur une base sauvegardée ou jetable :
1. Vérifier les cinq types après deux redémarrages KMS : aucun doublon.
2. Créer A et B, lier A→B (`DEPENDS_ON`) et B→A ;
   les deux liens doivent être possibles.
3. Créer A↔B (`RELATED_TO`), vérifier HTTP 409 sur B↔A de même type.
4. Tester lien sur soi-même, UUID absent et suppression logique d'un nœud.
5. Tester deux PATCH avec le même `If-Match` ; le second doit répondre 412.
6. Délier un lien et vérifier que les deux connaissances restent actives.
7. Vérifier les droits ADMIN/EDITOR/READER, pagination et Gateway.

Les tests unitaires, HTTP, Angular et MongoDB isolé sont intégrés
à la CI. La fusion sur `chat` est conditionnée à une CI entièrement verte ;
la recette UI humaine reste recommandée.

## Suite

Le prochain domaine du MLD est **F — Sources, pièces jointes et
historique** (`knowledge_sources`, `knowledge_source_links`,
`knowledge_attachments`, `knowledge_attachment_links`,
`knowledge_versions`). Les pièces jointes doivent faire l'objet d'un
arbitrage spécifique sur les chemins locaux, quotas, sauvegardes et sécurité.
