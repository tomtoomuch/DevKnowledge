---
title: "ADR-005 — Stratégie de stockage : SQLite métriques, MongoDB métier et étude SQL Server"
date: "2026-11-10"
status: "Décision partielle : SQLite métriques retenu ; SQL Server métier en étude"
tags: [adr, stockage, sqlite, sqlserver, postgresql, mongodb, metriques]
---

# ADR-005 — Stratégie de stockage par responsabilité

## Contexte : ce que décrit réellement le MLD

Le document [[DevKnowledge_MLD_3NF_v0.2]] décrit **56 tables
logiques candidates à la 3NF**, comprenant notamment
`knowledge_items`, ses huit spécialisations, les relations N:N,
la conformité, le référentiel RNCP, les preuves et les identités RBAC.
Il indique explicitement que ce MLD **n'oblige pas à utiliser un SGBD
SQL** et que la projection MongoDB reste à étudier.

Actuellement, les données métiers et les comptes sont stockés dans
le volume MongoDB `mongodb:/data/db`; leurs opérations REST ont
été développées autour de PyMongo. Les portages SQL seraient des
migrations de schéma et de code, **pas de simples changements de
chaînes de connexion**.

## Décision A — Métriques : SQLite3 intégré au Superviseur

Le magasin local des métriques est **SQLite3 embarqué dans Node.js**
via `node:sqlite` (runtime Node 26), sans conteneur de base SQL
supplémentaire, uniquement dans le service de collecte (futur Superviseur).

- **Volume Docker dédié** : `supervisor-metrics:/var/lib/devknowledge-supervisor`,
  sans aucun port hôte, indépendant du volume MongoDB.
- Base `metrics.sqlite3` et journaux WAL sur le même volume et le
  même système de fichiers ; accès en écriture réservé au Superviseur.
- **Un seul écrivain applicatif**, échantillonnage par défaut toutes
  les 60 secondes, dédoublonnage des exécutions concurrentes,
  transactions d'insertion atomiques, `busy_timeout`, WAL
  et `synchronous=FULL`.
- Conservation du **snapshot JSON brut** (champ
  `raw_snapshot_json`), plus projections analytiques
  `metric_samples`, `service_metrics` et `gpu_metrics`.
- Rétention initiale **90 jours**, purge quotidienne des anciennes
  mesures ; aucun compte, secret, document métier ou audit de
  sécurité n'est copié dans SQLite.
- Lecture interne `GET /metrics/history?limit=N`, bornée et
  soumise à la garde réseau KMS actuelle ; aucune exposition
  directe au navigateur ni route de publication Gateway dans ce lot.

**Précision de vocabulaire :** cela constitue un **magasin analytique
local / data lake léger** plutôt qu'un data lake distribué avec
stockage d'objets. La séparation des JSON bruts et des projections
relationnelles facilite un futur ETL vers un système analytique
plus important si nécessaire.

La sauvegarde en ligne passe par la fonction native
`sqlite.backup()`, jamais par la copie simple d'un fichier
`.sqlite3` ouvert en WAL ; voir [[operations/metrics-sqlite]].

**Limites** : SQLite autorise plusieurs lectures simultanées mais un
seul écrivain actif à la fois ; un changement vers un moteur
client-serveur sera à envisager si l'ingestion devient multi-écrivains
ou distribuée.

## Décision B — Données métier : aucun changement immédiat

**SQL Server est un candidat sérieux**, particulièrement pertinent
pour exercer un MLD 3NF avec FK, contraintes, transactions, vues et
jointures liées aux exigences RNCP et aux preuves de certification.

Néanmoins, **nous ne remplaçons pas MongoDB dans cette PR**.
Un basculement prématuré mettrait en risque des données et
fonctionnalités déjà testées (fiches, versions, relations, identité,
sauvegarde/restauration). Il impose également une transition
des accès dans FastAPI, des modèles de documents et des scripts
d'exploitation.

### Comparaison initiale

| Critère | MongoDB (actuel) | SQL Server 2025 | PostgreSQL 18 |
| --- | --- | --- | --- |
| Modèle physique | Documents, champs embarqués | Relationnel / FK / SQL | Relationnel / FK / SQL |
| Jointures N:N complexes | Via agrégations / projections | Natives | Natives |
| Champs de spécialisation variables | Naturels en BSON | Colonnes et JSON | Colonnes et JSONB indexable |
| Contrainte d'intégrité entre entités | Souvent applicative | FK et transactions | FK et transactions |
| Fonctionnement local et hors ligne | Déjà validé | Image et volume Docker locaux | Image et volume Docker locaux |
| Licence | Selon la distribution et l'usage | Express gratuite avec limites ; Developer réservée au développement/test | Licence open source permissive |
| Coût de migration | Aucun | Élevé | Élevé |

SQL Server 2025 Express autorise **50 Go par base** mais limite la
capacité d'une instance Express à **4 cœurs / 1 socket** et la mémoire
de buffer pool à **1 410 Mo**. Developer est destinée aux
environnements de développement, pas à une exploitation commerciale.
Ces limites doivent être rapprochées des volumes réels et des
capacités de l'hôte.

PostgreSQL propose `JSONB` et des index GIN pour des contenus
partiellement structurés, ce qui peut être intéressant pour les
spécialisations du KMS.

### Preuve de concept avant arbitrage

Isoler un **projet Docker Compose jetable**, sans publier le port SQL
sur l'hôte et sans réutiliser le volume MongoDB métier. Comparer
SQL Server Express 2025 et PostgreSQL sur un échantillon **anonymisé**
provenant du MLD :

1. `knowledge_items`, `tags`, `knowledge_tags`,
   `knowledge_relations`, `users`, `roles`, `user_roles` ;
   puis un sous-ensemble RNCP/conformité avec ses FK.
2. Insertion et restitution d'UUID historiques, révisions `If-Match`,
   index uniques, FK, suppression logique et recherche textuelle.
3. Requêtes mixtes connaissances ↔ tags ↔ RNCP et volumes
   proportionnés à la charge attendue ; mesurer latence et mémoire.
4. Sauvegarde, redémarrage, restauration isolée et disponibilité
   hors ligne avec images préchargées ; vérifier la licence ciblée.
5. Évaluer les impacts du pilote SQL sur le KMS et le Superviseur,
   afin de conserver une **base propriétaire par domaine** et des
   transactions locales.

**Critère de décision** : choisir le SGBD seulement après avoir
mesuré le gain de cohérence et de requêtage par rapport au coût
d'exploitation et de migration ; ne pas ajouter SQL Server
simplement parce que le MLD est exprimé en 3NF.

## Découpage cible des responsabilités

- **Superviseur / identité** : collections d'identité sous
  autorisation forte ; actuellement MongoDB, migration SQL à étudier
  indépendamment des connaissances.
- **Superviseur / métriques** : SQLite3 et son volume propre.
- **Superviseur / logs et audits** : collecte prévue par ADR-004,
  stockage, taille et rétention à arbitrer distinctement.
- **KMS / connaissance et référentiels** : MongoDB en production
  locale actuelle ; SQL Server/PostgreSQL restent candidats de POC.
- **RAG / embeddings** : à arbitrer selon la recherche vectorielle
  réelle et les contraintes offline.

**Aucun accès direct à ces données depuis le navigateur** :
toutes les consultations externes passent par Gateway Express,
puis par les microservices autorisés.

## Sources consultées

- [SQLite : usages adaptés et limites de concurrence](https://www.sqlite.org/whentouse.html)
- [SQLite : fonctionnement du WAL](https://www.sqlite.org/wal.html)
- [Node.js : API SQLite native et backup](https://nodejs.org/download/release/v26.8.2/docs/api/sqlite.html)
- [Microsoft Learn : éditions SQL Server 2025](https://learn.microsoft.com/en-us/sql/sql-server/editions-and-components-of-sql-server-2025?view=sql-server-ver17)
- [Microsoft Learn : persistance des conteneurs SQL Server](https://learn.microsoft.com/en-us/sql/linux/sql-server-linux-docker-container-configure)
- [PostgreSQL : JSONB et indexation GIN](https://www.postgresql.org/docs/current/datatype-json.html)
