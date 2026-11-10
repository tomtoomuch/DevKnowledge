---
title: "Issue 16 — Superviseur MongoDB : mode shadow de lecture des sessions"
date: "2026-11-10"
status: "Préparation — activation manuelle uniquement"
tags: [devknowledge, supervisor, security, mongodb, rbac]
---

# Introspection MongoDB dans le Superviseur (mode shadow)

Cette itération ajoute une **connexion MongoDB autonome et optionnelle** au
processus `collector` (futur Superviseur), sans toucher au propriétaire actuel
des comptes (KMS) ni à la configuration des routes Gateway.

- `SUPERVISOR_IDENTITY_MODE=disabled` (défaut) : identique au comportement
  historique, aucun client MongoDB d'identité créé et aucun endpoint
  d'autorisation monté.
- `SUPERVISOR_IDENTITY_MODE=shadow` : le démarrage exige une connexion MongoDB
  disponible et les deux secrets de service valides. Il expose uniquement sur
  le réseau Docker interne `POST /internal/v1/sessions/authorize`,
  authentifié par `X-Service-Key`, avec vérification de l'origine réseau
  `api-gateway`. Le Gateway **ne l'appelle pas encore automatiquement**.
- Toute autre valeur entraîne un échec de démarrage.

L'adaptateur ne modifie pas les collections. Il recherche l'empreinte SHA-256
du cookie opaque dans `sessions`, vérifie expiration, révision et statut du
compte, puis détermine les droits par `role_codes` ou les collections RBAC
historiques. Une session absente, révoquée ou invalide ne produit aucun token.

## Configuration préalable

Le Superviseur exige un utilisateur MongoDB distinct, doté uniquement
de privilèges `find` sur les collections d'identité nécessaires :
`users`, `sessions`, `user_roles`, `roles`, `role_permissions`,
`permissions`. **Ne pas réutiliser le compte root ni le compte KMS
readWrite.** Préparer la sauvegarde MongoDB avant toute modification des
habilitations.

Variables requises en mode shadow (sans versionner les secrets) :

```dotenv
SUPERVISOR_IDENTITY_MODE=shadow
MONGODB_SUPERVISOR_USERNAME=<utilisateur MongoDB lecture seule>
MONGODB_SUPERVISOR_PASSWORD=<mot de passe généré séparément>
SUPERVISOR_GATEWAY_KEY=<64 caractères hexadécimaux aléatoires>
SUPERVISOR_KMS_TOKEN_KEY=<64 caractères hexadécimaux aléatoires différents>
```

Les secrets de service se génèrent indépendamment, par exemple avec
`python -c "import secrets; print(secrets.token_hex(32))"`.
Configurer `MONGODB_AUTH_SOURCE` comme base d'authentification où le compte
a réellement été créé. Vérifier les permissions en lecture seule et la
connectivité interne avant d'activer `shadow`. Ne pas journaliser les secrets.

## Vérifications

1. Avec le mode désactivé : les healthchecks et les métriques SQLite
   continuent de fonctionner ; `POST /internal/v1/sessions/authorize`
   renvoie 404.
2. En mode shadow : tester un compte actif, une session valide, une session
   expirée, un changement de révision, une révocation et les rôles anciens.
3. Rejeter l'appel sans clé de service, avec clé erronée, ou depuis un
   autre pair Docker que `api-gateway`.
4. Simuler une panne MongoDB : le service ne doit ni retourner de token,
   ni exposer de chaîne de connexion ou de secret.
5. Tester le redémarrage Docker, la persistance du volume MongoDB et le
   maintien des métriques SQLite.

## Ce que cette étape ne fait PAS

**Le Gateway utilise toujours l'introspection KMS et le KMS accepte encore
l'ancien mécanisme de session.** L'étape shadow n'est donc ni une migration
de l'identité, ni un déploiement des tokens obligatoires.
La synchronisation et la mutation des comptes, la bascule des routes
login/logout/users vers le Superviseur, et le relais des tokens Gateway → KMS
restent à développer, tester et documenter avant toute activation du
mode `KMS_SERVICE_TOKEN_MODE=required`.

Le Dockerfile installe le pilote MongoDB lors du **build** de l'image :
pour un fonctionnement complètement hors ligne, construire et conserver
cette image ainsi que ses dépendances en amont. Les versions devront être
verrouillées par lockfile avant la qualification reproductible finale.
Ne jamais utiliser `docker compose down -v` sur l'environnement courant.
