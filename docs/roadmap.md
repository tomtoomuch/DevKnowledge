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
| Classification, spécialisations et historique | Non commencée | Référentiel `knowledge_types` ; huit spécialisations ; tags, technologies, sources, versions |
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
