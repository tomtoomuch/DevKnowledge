# Dossier de revue de sortie — 9 novembre 2026

Ce dossier rassemble les preuves techniques de l'itération 2 et les décisions
restantes. Il prépare la revue commune ; il ne prononce pas sa clôture et ne
vaut pas autorisation de fusion.

## État proposé à la revue

| Critère | Preuve disponible | Limite ou décision restante |
| --- | --- | --- |
| Installation vierge et compte limité | Bootstrap Docker, contrôle du rôle readWrite, interdiction d'écrire dans une autre base | Développement existant non migré |
| CRUD et accès unique Gateway | Suites KMS/Gateway et cinq opérations HTTP sur les vrais services | Pas d'identité applicative ni de RBAC |
| Concurrence | Révision/ETag et filtre atomique MongoDB, courses PATCH/PATCH et PATCH/DELETE | Clients à adapter à If-Match ; relecture après restauration |
| Sauvegarde/restauration | BSON, empreintes, index et options comparés ; cible neuve isolée | Archives locales non chiffrées ; aucun écrivain externe pendant le dump |
| Robustesse | Redémarrage, panne/reprise MongoDB et KMS, identifiants incorrects | Aucun déploiement ni test de charge |
| Exécution hors ligne | Mode `--offline`, images locales, réseau interne vérifié, CRUD et restauration rejoués | Hôte non déconnecté ; build hors ligne non qualifié |
| Reproductibilité et CI | Verrous npm/Python, matrice KMS Windows/Linux, tests Docker et rapports | Images système par tags ; runner Docker Ubuntu 22.04 à remplacer avant son retrait annoncé |
| Données et configuration | Bases jetables et nettoyage ; `.env` exclu de Git ; contrôles de non-divulgation des mots de passe de test | Aucun audit exhaustif des secrets de l'historique Git |

## Qualification hors ligne

La qualification locale utilise Windows, Python 3.14.4, Docker Engine 29.9.2
et Compose 5.6.1. Les images applicatives sont celles préparées au commit
`5bf4f6fbee860d3eefd8e469ad8641d39e806c5d` ; le complément de qualification
modifie les scripts et la CI, sans modifier ces applications.

Résultat local observé : **11 groupes de contrôles réussis**, nettoyage réussi,
et **9 tests unitaires des scripts de maintenance/qualification réussis**.
La sonde sortante reçoit `ENETUNREACH` ; les trois conteneurs sont reliés
uniquement au réseau interne, sans route par défaut. Aucune donnée personnelle
n'entre dans ce scénario.

Le rapport `test-results/stabilization-offline.json` identifie les images
réellement exécutées et la plateforme, les contrôles et le nettoyage. La CI
reconstruit les images depuis la révision de la PR avant de rejouer le mode
hors ligne. Procédure et portée : [[../operations/offline-runtime]].

## Décisions pour la prochaine itération

1. Relire le changement de contrat `If-Match` et la procédure de récupération,
   puis décider de la fusion de la PR #4 vers `dev`.
2. Valider l'ADR-003 avant l'implémentation de l'identité : compte local ou
   session machine, usage mono/multi-utilisateur, durée de session et récupération.
   La proposition locale permet de conserver l'objectif hors ligne.
3. Fixer le périmètre du prochain lot métier après cet arbitrage ; classification
   et historique restent candidats. Angular, RNCP et RAG restent ultérieurs.

Les alertes historiques sur l'outillage npm de développement et le verrouillage
des images restent des travaux distincts. Aucune sauvegarde de données
personnelles, migration ou activation de volume récupéré n'a été réalisée ici.

## Rapports détaillés

- [[validation-stabilisation-2026-11-09]] : bootstrap, configuration et premières suites.
- [[validation-gateway-2026-11-09]] : relais Gateway et pannes.
- [[validation-stab08-2026-11-09]] : concurrence et sauvegardes.
- [PR #4 et validations associées](https://github.com/tomtoomuch/DevKnowledge/pull/4).
