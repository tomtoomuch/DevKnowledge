---
title: "DevKnowledge — Feuille de route"
updated: "2026-11-24"
status: "Qualification PostgreSQL/RNCP après migration identité"
tags: [devknowledge, roadmap, stabilisation]
---

# Feuille de route DevKnowledge

## Périmètre et preuves

Cette photographie décrit le code intégré dans `chat` au commit `a26ba97` du 13 novembre 2026, puis la reprise de la PR #21 et l'achèvement du circuit d'identité le 24 novembre. Le candidat `codex/doc-41-identity-migration` est proposé à la revue vers `chat` ; sa CI est suivie dans DOC-41. `dev` et `main` ne contiennent pas tous ces lots.

[La CI de `a26ba97`](https://github.com/tomtoomuch/DevKnowledge/actions/runs/43402738352) a réussi ses six jobs : frontend, Gateway, Superviseur, KMS Windows/Linux et Docker. Le job Docker couvre bootstrap MongoDB, intégration, redémarrage, panne/reprise et exécution hors ligne avec images préparées. Cette preuve ne constitue ni une recette manuelle actuelle ni une qualification des modifications ultérieures.

## Principes

- Fonctionnement local et hors ligne après préparation des images et dépendances.
- Gateway Express comme unique point d'entrée, y compris pour Angular/Nginx ; services et bases internes.
- PostgreSQL retenu pour le métier relationnel, MongoDB pour les métadonnées et futurs usages IA, SQLite pour les métriques : [[decisions/ADR-005-strategie-stockage]]. Les connaissances et comptes actuels restent dans MongoDB.
- Préservation des données et volumes existants ; qualifications sur projets jetables distincts.
- Séparation entre code implémenté, mode activé, preuve de test et décision de promotion.

## État des domaines

| Domaine | Implémenté dans `chat` | Reste à traiter |
| --- | --- | --- |
| Socle | Angular/Nginx, Express, FastAPI, MongoDB, Superviseur ; cinq services Compose | Verrouillage des dépendances frontend/Superviseur et des images système |
| Stabilisation | Bootstrap, readiness, panne/reprise, sauvegarde/restauration MongoDB, ETag/If-Match, CI et offline préparé | Revue de sortie et recette de la révision candidate ; build complet hors ligne |
| Connaissances | CRUD, huit spécialisations, recherche textuelle, filtres, favoris et pagination | Sources, pièces jointes, historique versionné ; recherche indexée sur gros corpus |
| Classification | Tags, technologies et versions, API/UI et associations atomiques (PR #9/#10) | Administration des catalogues immuables et navigation avancée |
| Relations | Cinq types, relations dirigées/symétriques, unicité, API/UI et révisions (PR #11) | Politique de traitement des liens vers les fiches supprimées et administration des types |
| Identité locale | Sessions opaques, RBAC et CRUD complet des comptes, désormais portés par Superviseur dans le code local | Revue/fusion de la PR #22 ; récupération locale du mot de passe disponible |
| Superviseur | Métriques SQLite, login/logout, CRUD comptes, routage Gateway, jetons obligatoires et droits MongoDB limités qualifiés localement | Rotation à clés multiples, signature asymétrique et audits centralisés |
| PostgreSQL/RNCP | Dix tables métier, migrations et API optionnelle protégée (PR #19) ; qualification complète candidate dans DOC-42 | Cohérence MongoDB/SQL (DOC-43), droits PostgreSQL, UI et contenu officiel RNCP (DOC-25) |
| IA/RAG | Recherche textuelle littérale existante | Chunking, embeddings, index sémantique, Ollama, citations et évaluation |
| MCP/MLOps | Non implémentés | Outils autorisés, évaluations et suivi MLflow |

Le MLD v0.2 contient **56 tables logiques candidates** ; ce nombre n'est pas celui des tables physiques déployées. Les détails spécialisés et associations de classification actuels sont embarqués dans les documents MongoDB pour garantir les écritures atomiques.

## Migration identité : revue ouverte, installation locale activée

L'[issue #16](https://github.com/tomtoomuch/DevKnowledge/issues/16) est implémentée dans le checkout local : le Compose normal impose l'autorité Superviseur et les jetons obligatoires côté KMS. Les routes d'identité KMS sont retirées dans ce mode ; aucune session navigateur n'est relayée au KMS. Les identifiants et sessions historiques restent compatibles.

La PR #21 est reprise dans DOC-40 ; le lot suivant termine le CRUD, le routage et l'exploitation. Les tests couvrent les droits MongoDB distincts, la concurrence, la révocation, les pannes, le redémarrage et le retour de l'application sur une sauvegarde restaurée, sans téléchargements. Voir [[operations/identity-migration]] pour les preuves, commandes et limites. La PR #22 est publiée et sa CI #151 est verte sur 94789e5. L'installation locale a été basculée après sauvegarde/restauration vérifiée : cinq services sains et 14 collections d'origine conservées à l'identique. La revue/fusion reste ouverte.

L'ADR-003 reste le contrat de données historique. L'ADR-004 décrit désormais un circuit local implémenté ; la signature asymétrique, la rotation `kid` sans interruption et l'audit centralisé restent des lots de durcissement.

## Prochaines étapes

1. Maintenir README, index et présente feuille de route en accord avec le code et le suivi [Linear DOC](https://linear.app/documentation-perso/team/DOC/all).
2. Faire relire et intégrer la PR #22 de migration identité ; CI et activation locale réalisées, preuves conservées.
3. Faire relire la qualification PostgreSQL/RNCP DOC-42 : circuit Superviseur/JWT, pannes et restauration MongoDB/PostgreSQL/SQLite sur données fictives. Voir [[iterations/rncp-stack-2026-11-24]].
4. Préparer une promotion revue de `chat` vers `dev`, sur une révision précise avec CI complète et recette ; aucune fusion automatique vers `dev` ou `main`.
5. Traiter DOC-43 avant activation réelle : une suppression MongoDB concurrente peut laisser un lien SQL orphelin. L'audit détecte cette incohérence sans la réparer. Compléter ensuite le référentiel officiel et l'interface RNCP dans DOC-25.
6. Compléter sources et historique, puis construire RAG et MCP avec contrôle d'accès et évaluation.

## Exploitation et limites

- Sauvegardes MongoDB non chiffrées : [[operations/backup-restore]].
- Offline validé après préparation ; images système par tags et build hors ligne non qualifié : [[operations/offline-runtime]].
- Gateway : lockfile npm présent ; frontend et Superviseur : lockfiles à établir.
- Métriques SQLite persistantes et sauvegarde dédiée : [[operations/metrics-sqlite]]. La centralisation des journaux et audits reste distincte.
- Le runner Docker utilise Ubuntu 22.04 pour la compatibilité MongoDB ; suivre le correctif et le calendrier du runner.

## Références

- [[index]] : navigation documentaire.
- [[iterations/revue-sortie-stabilisation-2026-11-09]] : preuves historiques et décisions de sortie au 9 novembre, à replacer dans leur contexte.
- [[iterations/iteration-9-user-crud]] : comptes et garanties de concurrence.
- [[iterations/issue-16-supervisor-shadow-mongodb]] : mode de lecture et provisionnement explicite.
- [[iterations/issue-16-users-manage-contract]] : autorisation administrative sans token KMS.
- [[iterations/postgres-rncp-api-2026-11-10]] : API optionnelle, preuves et limites.
- [[decisions/ADR-003-identite-securite]], [[decisions/ADR-004-superviseur-identite-securite]], [[decisions/ADR-005-strategie-stockage]] : décisions et cible.
