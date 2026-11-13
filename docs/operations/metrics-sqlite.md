---
title: "Superviseur — persistance des métriques SQLite3"
date: "2026-11-10"
status: "PR #14 en cours de validation"
tags: [superviseur, sqlite, datalake, metriques, sauvegarde]
---

# Magasin analytique local SQLite3 des métriques

Cette première implémentation utilise encore le **nom de service
Docker et le répertoire source `supervisor`**, pour préserver
la compatibilité tant que la PR #13 n'a pas migré l'identité et
renommé le microservice. Le magasin est destiné au **Superviseur**.

## Sources, tables et fréquence

Chaque minute (valeur `METRICS_SAMPLE_INTERVAL_MS=60000` dans
Compose), le service enregistre un échantillon daté UTC de santé
Gateway / Frontend / KMS / MongoDB, ainsi que les GPU si activés.

```text
metric_samples (
  sample_id INTEGER PRIMARY KEY,
  sampled_at TEXT UTC ISO8601,
  gpu_status TEXT,
  raw_snapshot_json JSON validé
)

service_metrics (
  sample_id INTEGER FK -> metric_samples,
  service_id TEXT,
  status TEXT,
  PRIMARY KEY(sample_id, service_id)
)

gpu_metrics (
  sample_id INTEGER FK -> metric_samples,
  gpu_index INTEGER,
  gpu_name TEXT,
  utilization_pct REAL NULL,
  memory_used_mib REAL NULL,
  memory_total_mib REAL NULL,
  temperature_c REAL NULL,
  PRIMARY KEY(sample_id, gpu_index)
)
```

Les observations sont validées puis insérées dans **une transaction
unique**. Les index et la politique de conservation automatique
(90 jours) sont initialisés dès l'ouverture du magasin.
`journal_mode=WAL`, `foreign_keys=ON` et
`synchronous=FULL` sont activés.

Le fichier est monté dans un volume Docker nommé logique
`supervisor-metrics` au chemin
`/var/lib/devknowledge-supervisor/metrics.sqlite3`.
Le montage est inscriptible même si le filesystem du conteneur
est `read_only: true`. Il **n'expose aucun port SQL**.

## Lecture et contrôle d'accès

`GET http://supervisor:9109/metrics/history?limit=20` est interne
au réseau Docker : il retourne au plus 100 snapshots, du plus récent
au plus ancien. Il n'est **pas publié au Gateway** dans cette PR et
conserve provisoirement le contrôle de provenance KMS utilisé par
`/snapshot`. Il devra être remplacé par une authentification de
service vérifiable cryptographiquement au cours d'ADR-004.

**Il est interdit de connecter Angular directement au Supervisor /
Superviseur**. Le futur tableau de bord passera par Gateway,
une API du Superviseur avec RBAC et les tokens d'identité nécessaires.

## Sauvegarde cohérente et non destructive

Le script `scripts/mongodb_backup.py` ne sauvegarde **que MongoDB** ;
il n'inclut pas `supervisor-metrics`. Le nouvel outil
`src/metrics-backup.js` crée un cliché SQLite en ligne via
`node:sqlite.backup`, vérifie `PRAGMA integrity_check`, met les
permissions à 0600 et refuse d'écraser une archive existante.

Depuis la racine Git Bash, sur une instance utilisant le bon projet
Compose, choisir un **nom de sortie inédit** :

```bash
docker compose --env-file .env exec -T supervisor node src/metrics-backup.js \
  /var/lib/devknowledge-supervisor/exports/metrics-2026-11-10.sqlite3
mkdir -p backups/supervisor
docker compose --env-file .env cp \
  supervisor:/var/lib/devknowledge-supervisor/exports/metrics-2026-11-10.sqlite3 \
  backups/supervisor/metrics-2026-11-10.sqlite3
```

Vérifier que l'archive copiée est indépendante du volume source
et, dans un conteneur ou environnement SQLite de test, que
`PRAGMA integrity_check` renvoie `ok`. Ne jamais faire un
`cp` direct du seul fichier live `metrics.sqlite3` alors que
le service écrit en mode WAL.

Le répertoire `backups/` reste hors Git. Une restauration doit
utiliser **un volume neuf / une instance jetable** pour éviter tout
écrasement silencieux de mesures de développement.

Le contenu historique du volume MongoDB `mongodb` est intégralement
préservé par ce lot. Le changement d'identifiant du projet Compose
peut changer les volumes nommés effectifs ; consulter
[[operations/volume-persistence]] avant tout démarrage sur un autre
worktree.

## Limites

Ce magasin ne contient actuellement que les snapshots de santé et
de GPU. Il **ne collecte pas encore les journaux de sécurité**.
La collecte multi-services des journaux sera développée séparément
conformément à ADR-004. Un vrai data lake d'objets,
la recherche interservices en temps réel et les index analytiques
avancés ne sont pas fournis dans cette itération.
