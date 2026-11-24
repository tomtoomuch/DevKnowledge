---
title: "Issue 16 — magasin de sessions du Superviseur compatible KMS"
date: "2026-11-10"
updated: "2026-11-24"
status: "Implémenté en bibliothèque, désactivé dans le runtime"
tags: [devknowledge, supervisor, authentication, mongodb, migration]
---

# Connexion et révocation : contrat de persistance historique

> Étape historique, complétée le 24 novembre 2026 : le circuit actif (CRUD comptes, sessions, Gateway et jetons KMS) est désormais implémenté et qualifié localement. Les mentions de routes non montées ou de modes désactivés ci-dessous décrivent cette étape préparatoire. Voir [l’état courant et la procédure](../operations/identity-migration.md). L’installation existante n’a pas été basculée.


## Reprise locale du 24 novembre 2026

Suivi : [DOC-40](https://linear.app/documentation-perso/issue/DOC-40), sous-tâche de [DOC-23](https://linear.app/documentation-perso/issue/DOC-23), et [PR #21](https://github.com/tomtoomuch/DevKnowledge/pull/21). Les sources de `40a8882` sont reprises sur le checkout `chat` basé sur `a26ba97`, après le renommage du dossier `collector` en `supervisor`. Les modifications restent locales et non publiées.

Corrections apportées pendant cette reprise :

- Compte historique sans `revision` : la garde MongoDB vérifie l'absence du champ avec `$exists: false`. Chercher `revision: 1` refusait ces comptes, alors que le KMS interprète leur révision comme 1. Une révision introduite entre lecture et écriture fait échouer la connexion.
- Les mots de passe sont bornés à 256 points de code Unicode, comme Python, au lieu de 256 unités UTF-16. Une fixture scrypt calculée par Python couvre 256 caractères non-BMP.
- Le champ JSON `session_cookie` de logout doit être une chaîne ; un tableau ne passe plus par coercition implicite.

### Résultats locaux

- **56 tests réussis** sous Windows avec Node 24.16.0, dont les tests HTTP, les deux fixtures Python/scrypt, les contrats de permissions et la vérification que login/logout restent absents du serveur normal et du mode shadow.
- **7 tests réussis** sur MongoDB 8.0 réel avec l'image Node 26 : empreinte seule en base, reconnexion puis révocation, comptes historiques sans révision et RBAC historique, expiration/changement de révision/désactivation, refus de connexion, courses avant écriture et après insertion, login/logout HTTP avec le vrai magasin.
- Configuration Compose et chemin Dockerfile vérifiés ; workflow GitHub Actions contrôlé avec `actionlint`.
- Projet de test `devknowledge-supervisor-session-20261124` nettoyé. Les conteneurs applicatifs existants restent arrêtés ; les volumes applicatifs n'ont pas été utilisés.

Rapports locaux ignorés par Git : `test-results/supervisor-session-20261124/unit.tap` et `integration.log`. La CI versionnée ajoute la suite MongoDB au job Docker et conserve ses journaux ; **cette nouvelle CI distante n'a pas encore été exécutée**.

### Reproduction

Depuis `backend/supervisor`, `node --test` exécute les tests sans base et ignore la suite MongoDB si `SUPERVISOR_TEST_MONGODB_URI` est absente. Depuis la racine, avec un nom de projet de test dédié :

```bash
docker compose -p devknowledge-supervisor-session-test -f backend/supervisor/tests/compose.integration.yaml up --build --abort-on-container-exit --exit-code-from supervisor-tests supervisor-tests
docker compose -p devknowledge-supervisor-session-test -f backend/supervisor/tests/compose.integration.yaml down --volumes
```

Le Compose de test utilise des identifiants fictifs, un réseau interne sans ports publiés et MongoDB en tmpfs. Le compte administrateur est réservé au banc de test : cette preuve ne qualifie pas les droits limités du futur compte d'exploitation. La reconnexion testée n'est pas un test de redémarrage Docker, de restauration ou du flux complet Gateway/KMS.

## Contrat préparé

Cette étape prépare également un gestionnaire HTTP interne **non monté**
`backend/supervisor/src/supervisor-session-handler.js` pour
`POST /internal/v1/auth/login` et `POST /internal/v1/auth/logout`.
Ce gestionnaire exige la clé `SUPERVISOR_GATEWAY_KEY`, valide strictement
le schéma JSON et refuse tout appel sans autorisation ; le Gateway devra
le relayer sans jamais transmettre les secrets au navigateur.
Le token opaque généré par login n'est renvoyé qu'au Gateway, qui devra
créer le cookie sécurisé `dk_session` ; logout révoque le token opaque.
La défense en profondeur par origine réseau sera appliquée lors du montage.
**Aucun endpoint n'est aujourd'hui exposé par le démarrage normal.**

Cette étape prépare un magasin de sessions dans
`backend/supervisor/src/identity-sessions.js` avec trois méthodes :
`login({username,password})`, `logout(cookie)` et `lookupSession(cookie)`.

Le service utilise les conventions **exactes** du KMS existant :
- `username_key` normalisé par suppression des espaces extérieurs et passage
  en minuscules ASCII, contrôle du format `[a-z0-9_.-]{3,40}`.
- Mot de passe scrypt au format `scrypt$32768$8$3$<sel hex>$<digest hex>`
  avec N=32768, r=8, p=3, maxmem=64 MiB et digest de 64 octets.
- Jeton de session opaque généré sur 32 octets aléatoires ; **seul SHA-256**
  du jeton est conservé comme `sessions._id`.
- `sessions.user_id`, `created_at`, `expires_at` (8 heures) et
  `identity_revision` inchangés ; `users.last_login_at` actualisé.
- Vérification du compte ACTIVE, de sa révision, de sa suppression logique
  et de ses rôles avant de retourner un `Principal`.
- Révocation via suppression de `sessions._id` ; un changement de révision
  rend immédiatement les sessions historiques invalides.

Le magasin est **isolé** ; le gestionnaire HTTP existe mais n'est pas relié au serveur ni activé par Compose.
Le mode shadow reste read-only et continue à employer le
`createMongoSessionLookup` de la PR #17. Les opérations de connexion/logout
nécessiteront un compte MongoDB à droits d'écriture limités, une stratégie
d'audit et des endpoints internes Gateway → Superviseur **avant** activation.

## Validation du flux complet encore nécessaire avant bascule

- Aller-retour entre le KMS Python réel et le Superviseur Node avec les mêmes sessions ; les fixtures Python et les tests MongoDB ci-dessus ne suffisent pas à qualifier ce flux complet.
- Redémarrage Docker, reprise et réversibilité avec sessions historiques.
- Parité cookies `dk_session` Secure/HttpOnly/SameSite et limites de débit.
- Gestion des comptes, verrouillage du dernier ADMIN et `If-Match`.
- Rotation de secrets, sauvegarde/restauration et tests Docker offline.
- Passage de Gateway et KMS sur le nouveau circuit JWT, en dernier.

Ne pas utiliser le compte shadow à privilèges `find` pour ce magasin :
il ne pourrait pas créer ni révoquer de sessions. La migration ne doit
**pas** modifier ou effacer les volumes MongoDB existants.
