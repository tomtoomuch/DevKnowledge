# STAB-08 — sauvegarde/restauration et concurrence

Travail effectué sur `chat` après fusion de la
[PR #3](https://github.com/tomtoomuch/DevKnowledge/pull/3) dans `dev`
(`f3dcfab985aa2009fbb5ecf935ca1a1f21f7dbd9`).

## Livraison

- Révision serveur et ETag ; `If-Match` obligatoire pour PATCH/DELETE.
  Le contrôle et l'incrément sont atomiques dans MongoDB. Les anciens documents
  sans révision sont pris en charge sans migration globale.
- Sauvegarde BSON locale avec arrêt temporaire des écrivains applicatifs,
  manifeste SHA-256 et comparaison de l'état avant/après le dump.
- Restauration vérifiée dans un nouveau conteneur sans réseau et un nouveau
  volume ; reprovisionnement des comptes depuis le `.env`, sans restaurer de
  mots de passe archivés. Mode contrôle jetable ou volume récupéré conservé.
- Activation d'un volume récupéré séparée et explicite via `compose.recovery.yaml`.

## Validations locales observées

| Vérification | Résultat |
| --- | --- |
| KMS Windows, Python 3.14.4 | 123 tests réussis, 5 intégrations désélectionnées |
| KMS Docker Linux, Python 3.14.10 | 128 tests réussis, dont 5 intégrations ; 293/293 instructions couvertes |
| Gateway Jest | 44 tests réussis |
| Opérateur de sauvegarde, sans Docker | 5 tests de refus et de reprise après échec réussis |
| Écritures réellement concurrentes MongoDB | Un seul gagnant pour une révision donnée ; PATCH/DELETE concurrents inclus |
| CRUD via Gateway | If-Match transmis et révision périmée refusée en 412 |
| Sauvegarde/restauration réelle | Documents, types BSON, suppressions logiques, révisions, index et options identiques |
| Archive altérée | Refus avant allocation d'une cible de restauration |
| Modes restore et restore-check | Volume neuf conservé dans le premier cas, cible jetable nettoyée dans le second |
| Scénarios Compose | Redémarrage, panne/reprise MongoDB et KMS, mauvais identifiants toujours validés |

La CI rejoue ces contrôles et conserve les rapports de test. Les archives
éventuellement jointes aux artefacts Docker contiennent uniquement les données
fictives du projet de test, jamais des données de développement.

## Limites et changement de contrat

Les anciens clients doivent désormais transmettre l'ETag lu pour modifier ou
supprimer. Les sauvegardes locales sont non chiffrées et la cohérence suppose
l'absence d'écrivain externe pendant le dump. Une restauration ancienne impose
de recharger les clients et leurs révisions. Le chiffrement externe, la
planification automatique, l'authentification/RBAC et l'historique métier restent
hors périmètre.

Aucune sauvegarde des données personnelles existantes, aucune activation de
volume de récupération et aucune migration du développement n'ont été exécutées.
Seules des bases jetables ont été utilisées. La revue commune de sortie de
stabilisation et la qualification hors ligne restent à conduire.

Procédures : [[../operations/backup-restore]] et [[../architecture/knowledge-concurrency]].
