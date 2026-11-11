---
title: "ADR-005 — Stratégie de stockage polyglotte : PostgreSQL métier, MongoDB IA, SQLite métriques"
date: "2026-11-10"
status: "Acceptée — décision PostgreSQL définitive pour le métier ; migration non engagée"
tags: [adr, stockage, postgresql, mongodb, sqlite, chromadb, architecture]
---

# ADR-005 — Répartition des responsabilités de stockage

- **Statut : accepté le 10 novembre 2026.**
- **Décision du porteur du projet : PostgreSQL est le SGBDR définitif des données métier relationnelles.**
- Cette décision **ne vaut ni autorisation de migration immédiate**, ni validation des 56 tables physiques, ni suppression de MongoDB.
- **Cette ADR affine l'ADR-002** : cette dernière reste exacte pour le stockage actuellement implémenté, mais son choix de MongoDB comme unique source métier ne décrit plus la cible retenue.
- **Ne pas confondre avec l'ADR-004 du dépôt**, consacrée au Superviseur, à l'identité et à la sécurité.

## Contexte et preuves

Le MLD `DevKnowledge_MLD_3NF_v0.2.md` définit **56 tables logiques candidates à la 3NF**, non encore matérialisées intégralement. Les connaissances, la classification et l'identité actuelles sont implémentées en MongoDB, avec des dépendances KMS/PyMongo, des révisions `If-Match`, du RBAC et des procédures de sauvegarde.

La [PR #15](https://github.com/tomtoomuch/DevKnowledge/pull/15) a comparé dans des conteneurs isolés PostgreSQL 17 et SQL Server 2025 : deux moteurs ayant réussi les contrôles FK, UNIQUE, JSON, jointures RNCP simplifiées, rollback, révisions conditionnelles, migrations V2 et sauvegarde/restauration, ainsi qu'une API FastAPI de démonstration avec pilotes réels. [Rapport technique](https://github.com/tomtoomuch/DevKnowledge/blob/feature/poc-sqlserver-postgres-rncp/docs/iterations/poc-stockage-v2-2026-11-10.md) ; [CI POC 2/2](https://github.com/tomtoomuch/DevKnowledge/actions/runs/42779548344) et [CI socle 6/6](https://github.com/tomtoomuch/DevKnowledge/actions/runs/42779548319).

Dans **un seul essai exploratoire** : 4 500 lignes liées insérées en ~141 ms sur PostgreSQL contre ~514 ms sur SQL Server ; mémoire des conteneurs de base après essai ~27 MiB et ~487 MiB, respectivement. Les temps comprennent les drivers/outils, les runners ne sont pas identiques et ces chiffres ne constituent pas un benchmark reproductible de production. Le choix définitif appartient au propriétaire du projet, pas au seul résultat du micro-POC.

## Décision A — PostgreSQL pour le métier relationnel

**PostgreSQL est choisi définitivement comme moteur SQL cible**, notamment pour :

- les connaissances métier, les huit spécialisations, les relations entre connaissances, les tags, technologies et versions ;
- les projets, sources, versions de contenus, pièces justificatives et référentiels de conformité ;
- les référentiels RNCP versionnés, blocs, compétences, critères, associations et preuves de validation.

La liste ci-dessus délimite un **périmètre cible à détailler par lots** ; elle n'autorise pas à déplacer toutes les collections existantes dans un même commit. PostgreSQL offre des clés étrangères, transactions, contraintes, index et `JSONB` pour les données spécialisées dont le schéma doit rester adaptable. **La version à déployer** est à pinner après qualification de la cible (PostgreSQL 17 est la version testée).

Le **KMS reste propriétaire fonctionnel des API métier** ; les accès PostgreSQL sont exclusivement internes. Le navigateur n'accède à aucune base directement.

## Décision B — MongoDB demeure présent

**MongoDB est conservé pour les métadonnées et les futurs stockages documentaires liés au LLM** : configurations/versions de traitement IA, provenance, métadonnées d'indexation, traces fonctionnelles et fragments documentaires éventuels. Les frontières exactes des collections IA seront précisées à l'implémentation.

**État de transition :** les connaissances, les catégories et l'identité actuellement dans MongoDB y restent tant qu'aucune migration validée par domaine n'a été menée. Les comptes/sessions du Superviseur font l'objet de l'ADR-004 ; **aucun déplacement de leur autorité n'est décidé par cette ADR**.

MongoDB ne sera pas supprimé au terme de la transition. Les index IA et collections dérivées devront mentionner l'identifiant stable et la version/source de la connaissance d'origine.

## Décision C — SQLite 3 pour les métriques du Superviseur

Les métriques et instantanés de santé/GPU du service Collector devenu Superviseur sont stockés dans un **fichier SQLite3 local**, sans nouveau service de base de données ni port publié.

- **Volume dédié :** `supervisor-metrics:/var/lib/devknowledge-supervisor` ; fichier `metrics.sqlite3`.
- **WAL** et journaux sur le même volume, écrivain unique, `busy_timeout`, `synchronous=FULL`.
- Collecte initiale toutes les **60 secondes** et rétention de **90 jours**, configurables.
- Instantané brut `raw_snapshot_json` et projections `metric_samples`, `service_metrics`, `gpu_metrics`.
- Sauvegarde cohérente par l'API `sqlite.backup()`, **pas** par simple copie à chaud du fichier en WAL.
- Les logs et audits de sécurité sont un domaine distinct, non assimilé aux métriques.

Le code et les tests de cette couche existent sur `chat` ; consulter `docs/operations/metrics-sqlite.md`. **SQLite est un entrepôt analytique local, pas un data lake distribué.**

## Décision D — Stockages IA complémentaires

- **ChromaDB** demeure la cible d'index vectoriel de recherche sémantique. L'index doit être **reconstructible**.
- Les **fichiers/poids Ollama** résident dans des volumes de fichiers locaux dédiés, pas automatiquement dans MongoDB.
- Le stockage de chunks et la synchronisation entre PostgreSQL, MongoDB et l'index vectoriel demandent un contrat explicitement versionné.

Aucun de ces composants futurs ne devient obligatoire pour faire fonctionner le CRUD local actuel.

## Matrice des propriétaires de données

| Domaine | Source de vérité cible | Situation actuelle |
| --- | --- | --- |
| Fiches de connaissance et spécialisations, liens métier, tags/technologies | **PostgreSQL** | MongoDB tant que migration non validée |
| RNCP, référentiels et preuves | **PostgreSQL** | MLD proposé ; module complet non déployé |
| Métadonnées, provenance et contenu LLM prévu | **MongoDB** | MongoDB conservé, schémas IA futurs à définir |
| Identité et sessions | **Décision distincte ADR-004** | MongoDB et Superviseur ; pas de migration par cette ADR |
| Historique de mesures du Superviseur | **SQLite 3** | Implémentation locale sous `chat` |
| Vecteurs/index sémantiques | **ChromaDB envisagé** | Non déployé |
| Poids des modèles IA | **Volumes Ollama locaux envisagés** | Non déployé |

## Invariants, migrations et validation

1. **Une seule autorité d'écriture par donnée** ; ne pas créer de double écriture PostgreSQL/MongoDB non transactionnelle sans stratégie d'événements, d'outbox et de reprise.
2. Utiliser des **UUID stables** et des références versionnées ; vérifier les liens entre PostgreSQL et MongoDB dans les services, car les FK ne traversent pas ces moteurs.
3. Conserver les contrats API existants (`ETag`/`If-Match`, 428/412, suppression logique, rôles et permission), la Gateway comme point d'entrée et des bases non publiées dans Docker.
4. Créer un **Compose PostgreSQL de test isolé** avec volume distinct et données fictives, puis des migrations SQL versionnées et tests FastAPI d'intégration.
5. Migrer **un domaine cohérent à la fois** après inventaire, stratégie de rollback, sauvegarde restaurée dans un environnement neuf, contrôle des comptes et accord explicite. Aucune opération destructive sur les volumes de `dev`.
6. Qualifier enfin le démarrage offline avec images disponibles, le comportement en panne, la réplication éventuelle et les politiques de sauvegarde PostgreSQL/MongoDB/SQLite.

## Conséquences et alternatives

- **PostgreSQL retenu** pour le relationnel métier. **SQL Server écarté comme moteur cible** malgré la réussite technique du POC ; les travaux exploratoires restent comme preuve.
- **MongoDB et SQLite maintenus** selon leurs responsabilités. Davantage de moteurs implique une exploitation et des sauvegardes distinctes, et demande de documenter les frontières des données.
- L'ADR-002 conserve sa valeur historique et les règles local/offline/confidentialité ; **l'ADR-005 prévaut sur la nouvelle cible de stockage**.

## Sources internes

- [[DevKnowledge_MLD_3NF_v0.2]] — modèle logique candidat à la 3NF.
- [[decisions/ADR-002-stockage]] — choix historique MongoDB de l'implémentation.
- [[decisions/ADR-004-superviseur-identite-securite]] — identité et autorité du Superviseur.
- [[operations/metrics-sqlite]] — stockage SQLite des métriques.
- [PR #15 et rapport de comparaison](https://github.com/tomtoomuch/DevKnowledge/pull/15).
