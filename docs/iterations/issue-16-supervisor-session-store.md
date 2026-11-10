---
title: "Issue 16 — magasin de sessions du Superviseur compatible KMS"
date: "2026-11-10"
status: "Implémenté en bibliothèque, désactivé dans le runtime"
tags: [devknowledge, supervisor, authentication, mongodb, migration]
---

# Connexion et révocation : contrat de persistance historique

Cette étape prépare également un gestionnaire HTTP interne **non monté**
`backend/collector/src/supervisor-session-handler.js` pour
`POST /internal/v1/auth/login` et `POST /internal/v1/auth/logout`.
Ce gestionnaire exige la clé `SUPERVISOR_GATEWAY_KEY`, valide strictement
le schéma JSON et refuse tout appel sans autorisation ; le Gateway devra
le relayer sans jamais transmettre les secrets au navigateur.
Le token opaque généré par login n'est renvoyé qu'au Gateway, qui devra
créer le cookie sécurisé `dk_session` ; logout révoque le token opaque.
La défense en profondeur par origine réseau sera appliquée lors du montage.
**Aucun endpoint n'est aujourd'hui exposé par le démarrage normal.**

Cette étape prépare un magasin de sessions dans
`backend/collector/src/identity-sessions.js` avec trois méthodes :
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

## Validation indispensable avant bascule

- Tests scrypt compatibles avec un hash produit par Python.
- Login/logout sur MongoDB jetable avec sessions KMS historiques, concurrence
  et changement de révision, puis contrôle de réversibilité.
- Parité cookies `dk_session` Secure/HttpOnly/SameSite et limites de débit.
- Gestion des comptes, verrouillage du dernier ADMIN et `If-Match`.
- Rotation de secrets, sauvegarde/restauration et tests Docker offline.
- Passage de Gateway et KMS sur le nouveau circuit JWT, en dernier.

Ne pas utiliser le compte shadow à privilèges `find` pour ce magasin :
il ne pourrait pas créer ni révoquer de sessions. La migration ne doit
**pas** modifier ou effacer les volumes MongoDB existants.
