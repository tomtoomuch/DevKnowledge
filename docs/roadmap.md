---
title: "DevKnowledge — Feuille de route"
updated: "2026-11-09"
status: "Planification évolutive"
tags: [devknowledge, roadmap, stabilisation]
---

# Feuille de route DevKnowledge

## Principes constants

- **Local-first et hors ligne en fonctionnement courant**, après préparation des images, dépendances et modèles.
- **Express comme point d'entrée applicatif unique cible**, FastAPI par service métier, MongoDB comme source de vérité.
- Données d'origine sous le contrôle de l'utilisateur ; sauvegarde distante facultative.
- Architecture incrémentale ; ne pas confondre fonctionnalités **documentées**, **implémentées** et **vérifiées en exécution**.
- Traçabilité Git et documentation Obsidian ; avancement et arbitrages revus ensemble.

## Situation au 9 novembre 2026

| Étape | État | Livrables / dépendances |
| --- | --- | --- |
| Cadrage et architecture | Réalisé pour le socle, arbitrages ouverts | Architecture globale ; ADR 001–003 ; blueprint BrainBlox |
| Modélisation | Modèle logique v0.2 à relire | 56 tables, huit spécialisations, utilisateurs/RBAC, RNCP et RAG ; aucune garantie d'implémentation physique globale |
| Socle Docker / Express / FastAPI / MongoDB | Bootstrap, configuration et readiness validés localement | Trois services Compose, contrôles de santé, stockage local |
| Itération 1 — CRUD générique KMS | Livrée, tests historiques positifs | `knowledge_items` ; routes, schémas, services, repository et tests |
| **Itération 2 — Stabilisation** | **STAB-01 à 08 implémentés ; revue de sortie à mener** | Config/env, compte MongoDB, readiness, tests, CI, reproductibilité, accès Gateway |
| Identité, rôles et droits | Prototype local + création/consultation de comptes Angular (itération 5), revue de sécurité à conduire | `users`, `roles`, `permissions`, `user_roles`, `role_permissions` ; arbitrage local/OIDC |
| Classification, spécialisations et historique | **Spécialisations intégrées ; tags PR #9 et technologies/versions PR #10 en cours** | `knowledge_types` et huit modèles ; catalogues `tags`, `technologies`, `technology_versions` et associations atomiques proposés ; sources, relations entre connaissances et historique encore non réalisés |
| Relations entre connaissances | **PR #11 en implémentation** | `relation_types`, `knowledge_relations`, orientation, unicité, éditions concurrentes, UI et tests sur MongoDB jetable |
| Certification RNCP et preuves | Non commencée | Versions du RNCP 37827, compétences, critères, correspondances, preuves |
| Recherche et assistant RAG local | Recherche textuelle générique implémentée dans l'itération 4 ; index sémantique/RAG non commencés | ChromaDB, chunking, embeddings, Ollama, citations, réponse « informations insuffisantes » |
| MCP, évaluation IA et MLOps | Non commencée | Outils contrôlés, tests d'autorisation, suivi MLflow |
| Sécurité, supervision et exploitation | Partiellement définies, exécution à planifier | Logs, métriques, sauvegardes/restauration, stratégies de mise à jour et déploiement |

### Jalon actif : stabilisation

Voir [[iterations/iteration-2-stabilisation]].

**Réalisé le 9 novembre :** bootstrap, compte limité, configuration Gateway, readiness, redémarrage et panne/reprise validés. Voir [[iterations/validation-stabilisation-2026-11-09]].

**Automatisation :** suites rejouées, workflow GitHub Actions versionné, dépendances Python verrouillées et séparées. Résultats distants consultables dans Actions.

**STAB-06 :** relais Gateway → KMS implémenté et testé ; KMS interne par défaut, diagnostic explicite via `compose.debug.yaml`. Voir [[architecture/gateway-kms]].

**STAB-08 :** sauvegarde BSON locale, restauration dans un nouveau volume et protection des écritures par révision/If-Match implémentées. Voir [[operations/backup-restore]] et [[architecture/knowledge-concurrency]].

**Hors ligne :** qualification de l'exécution après préparation des images, sans build ni téléchargement, via [[operations/offline-runtime]]. Les images système restent référencées par tags ; un build complet hors ligne reste à qualifier.

**Reste à conduire :** revue commune de sortie, préparée dans [[iterations/revue-sortie-stabilisation-2026-11-09]], puis arbitrage de l'identité locale (ADR-003).

Critères de sortie : installation propre reproductible, tests unitaires et intégration **réexécutés** (avec preuves et dates), CI opérationnelle, aucun secret versionné, documentation à jour, aucune donnée de développement supprimée.

## Itération 4 — Recherche globale de la bibliothèque

L'interface interroge désormais le KMS pour les recherches sur titre,
description et contenu, combinables aux filtres type/statut/favoris.
La pagination et les totaux sont calculés après filtrage et les
connaissances supprimées logiquement sont exclues. Cette solution est
fonctionnelle pour une bibliothèque personnelle de taille modérée,
mais repose sur une recherche regex non indexée : l'optimisation
des corpus volumineux reste à planifier. Voir
[[iterations/iteration-4-search]].

L'ADR-003 demeure à valider avant l'authentification/RBAC.

## Itération 6 — Spécialisations métier (PR #8)

- **Implémenté et fusionné via la PR #8 dans `chat` :** référentiel MongoDB `knowledge_types` (8 entrées initialisées au démarrage) et route sécurisée `GET /api/v1/knowledge-types` à travers la Gateway.
- Chaque catégorie du MLD v0.2 possède un contrat Pydantic `details` avec champs spécialisés, validation des types et refus des champs inconnus.
- L'interface Angular existante (`frontend/ui-app/`) propose des formulaires dynamiques, la lecture et le remplacement des détails sur les routes CRUD existantes.
- **Compatibilité :** les connaissances génériques historiques restent lisibles et modifiables sans spécialisation. `PATCH` conserve la précondition `If-Match` ; le changement de type efface les détails incompatibles et l'annulation ne touche pas MongoDB.
- **Implémentation physique choisie :** `details` est un sous-document de `knowledge_items` pour garantir la modification atomique dans une seule collection MongoDB. Les huit tables spécialisées décrites au MLD sont **logiques** et ne sont pas huit collections physiques supplémentaires.
- **À mener après recette :** migrations et validations d'intégrité des références métier, tables associées (étapes, dépendances, cours, etc.), classification, sources et historique. Voir [[iterations/iteration-6-specializations]].
- **Validation :** ne considérer l'itération livrée qu'après une CI entièrement verte et une recette manuelle sur une base sauvegardée ou jetable.

## Itération 7 — Classification par tags (PR #9)

Premier lot proposé sur `feature/knowledge-tags` : catalogue MongoDB `tags`
normalisé et indexé, API de lecture/création, filtres sur les connaissances,
liaisons `tag_ids` modifiables par `If-Match`, interface Angular dédiée et
tests sur base jetable. Voir [[iterations/iteration-7-tags]].

**Projection MongoDB :** la relation logique `knowledge_tags` est intégrée
à `knowledge_items.tag_ids`, sans création d'une collection physique
`knowledge_tags`. Les catalogues restent immuables pour ce premier lot.
Cette projection doit être prise en compte lors de l'implémentation des
relations complexes et des opérations d'administration.

**Lot suivant déjà engagé :** `technologies`, `technology_versions`,
`knowledge_technologies`, `knowledge_technology_versions` (PR #10, empilée
sur #9). Voir [[iterations/iteration-7b-technologies]].

**Après le lot B :** liens entre connaissances, sources partagées et historique versionné.

## Itération 8 — Relations entre connaissances (PR #11)

Les deux entités logiques du domaine E, `relation_types` et
`knowledge_relations`, sont proposées dans la PR #11 :
référentiel stable de cinq types, relations dirigées ou symétriques,
unicité canonique, API CRUD de liens avec `If-Match`, RBAC et interface
Angular dans les fiches. Voir [[iterations/iteration-8-knowledge-relations]].

**Reste à traiter :** politique de nettoyage des relations vers des
connaissances supprimées logiquement, édition/administration des types,
sources/pièces jointes et versions de connaissances.

## Ordre recommandé après stabilisation

1. Consolider la frontière Gateway → KMS et préparer le modèle d'identité locale/RBAC ; valider l'ADR-003 avant de promouvoir les interfaces.
2. Introduire `knowledge_types`, les spécialisations et leurs contraintes ; enrichir la classification, la traçabilité et l'historique.
3. Mettre en place les référentiels de certification versionnés, commencer par RNCP 37827, puis les preuves et leur rattachement aux compétences.
4. Construire la recherche locale et le RAG : index reconstructible, filtrage des accès, citations et refus explicite en cas de corpus insuffisant.
5. Ajouter MCP et les fonctionnalités MLOps/supervision avec autorisations et tests d'évaluation.

Cette séquence est indicative : les arbitrages métiers et le résultat des tests peuvent la modifier.

## Gouvernance et références

- [[iterations/point-avancement-2026-11-04]] : photographie du dépôt et risques datés.
- [[iterations/iteration-1-kms-crud]] : résultats historiques et périmètre réellement livré.
- [[architecture/kms-knowledge-crud]] : contrat du KMS et commandes de vérification.
- [[DevKnowledge_MLD_3NF_v0.2]] : source métier, **candidat** 3NF.
- [[architecture/architecture-globale]] : cible de communication et modules à venir.
- [[decisions/ADR-001-architecture]] / [[decisions/ADR-002-stockage]] / [[decisions/ADR-003-identite-securite]] : décisions confirmées ou encore à valider.

Les tâches de stabilisation doivent être traitées sur `chat`, avec revue commune ; aucune fusion automatique vers `dev` ou `main` n'est prévue.

## Itération 9 — CRUD utilisateurs et invariant d'entrée unique (PR #12)

La branche `feature/user-crud-volume-persistence` propose le CRUD complet
des comptes locaux (pagination, détails, rôles, statut, réinitialisation
des mots de passe et suppression logique avec révisions/ETag), ainsi qu'un
audit de persistance des volumes. L'unique point d'entrée extérieur est
**API Gateway Express**, pour les pages Angular comme pour les API.
Le volume historique MongoDB demeure conservé.

Voir [[iterations/iteration-9-user-crud]],
[[operations/volume-persistence]] et [[architecture/gateway-kms]].

## Décision ADR-004 — Superviseur (feature/supervisor-identity)

Migration progressive de l'ancien Collector : identité/RBAC/sessions,
CRUD utilisateurs, vérification de session par la Gateway et tokens internes
limités par audience et permissions pour le KMS. La PR est dépendante de
`feature/user-crud-volume-persistence` (PR #12), sans changement du volume
MongoDB historique ni d'accès direct aux services internes.

## Lot stockage observabilité — SQLite métriques et étude SQL (PR #14)

Le Superviseur doit stocker ses métriques dans un volume SQLite3 distinct
(`supervisor-metrics`) et centraliser ultérieurement les journaux techniques
et les audits de sécurité authentifiés. L'étude [[decisions/ADR-005-strategie-stockage]]
compare SQL Server 2025 Express, PostgreSQL et MongoDB pour le MLD métier de
56 tables, **sans activer de migration de données**. Les sauvegardes et
le fonctionnement offline doivent rester validés avant fusion.
