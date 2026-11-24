# Authentification et ports locaux

## Point d'entrée

Le navigateur utilise uniquement la Gateway Express, normalement sur `http://127.0.0.1:4200`. La Gateway sert Angular/Nginx sur le réseau DMZ, puis relaie les URL `/api/v1/auth/*` et `/api/v1/users*` vers le Superviseur. Les connaissances, catalogues, relations et le monitoring passent vers le KMS avec un jeton interne.

Nginx refuse `/api/` et ne reçoit ni cookies, ni jetons, ni en-têtes d'identité. Frontend, KMS, MongoDB et Superviseur ne publient aucun port hôte. Les chemins API inconnus ne doivent jamais servir la page Angular.

Le Superviseur est l'autorité des comptes, mots de passe, sessions et rôles. Il vérifie le cookie `dk_session` à chaque demande protégée et émet un jeton KMS d'audience et de portée limitées. Le KMS vérifie à nouveau ce jeton. Le circuit normal ne transmet jamais le cookie navigateur au KMS et n'utilise aucun repli d'identité historique.

La Gateway conserve les contrôles d'Origin, SameSite, limitation des tentatives de connexion et refus des en-têtes d'identité forgés. Le Compose normal impose l'authentification et le circuit Superviseur ; les tests historiques anonymes utilisent un override explicite distinct.

## Installation et premier compte

Pour une instance existante, suivre d'abord [la migration et ses sauvegardes](identity-migration.md). Les nouveaux comptes de base et secrets doivent être provisionnés avant redémarrage ; ne pas remplacer ou supprimer les volumes.

Pour une installation neuve, depuis la racine :

```bash
python scripts/bootstrap_supervisor.py --username admin
```

Pour un autre projet Compose, préciser `--project <nom-existant>` et éventuellement `--env-file <fichier>`. La saisie du mot de passe est masquée et sa transmission utilise stdin, jamais les arguments du processus. Un second bootstrap est refusé dès qu'un compte existe. Ne pas effacer les comptes, le marqueur `auth_bootstrap` ou le volume pour contourner ce refus.

Le navigateur conserve le cookie `dk_session` avec `HttpOnly`, `Path=/api/v1`, `SameSite=Strict` et une durée de huit heures. `AUTH_COOKIE_SECURE=true` ajoute Secure pour un accès HTTPS. Les URL Angular et le format public des comptes restent compatibles avec le circuit précédent.

## Diagnostic

- 401 : session absente, expirée ou révoquée, compte désactivé, ou mauvais identifiants.
- 403 : droit insuffisant ou écriture cross-origin refusée.
- 409 : doublon, protection du dernier ADMIN/de l'administrateur courant, ou verrou administratif occupé. Voir la récupération du verrou dans le guide de migration.
- 412/428 : révision de compte dépassée ou précondition `If-Match` absente.
- 429 : trop de tentatives de connexion ; attendre la fenêtre indiquée.
- 503 sur l'identité : Superviseur ou MongoDB indisponible ; aucune bascule vers le KMS historique.
- 502/504 sur le métier : relais KMS indisponible ou délai dépassé.

Inspecter les services avec `docker compose ps` et leurs logs, sans publier les ports internes ni journaliser cookies, mots de passe ou clés.

Les cookies HTTP ne sont pas isolés par numéro de port. Pour deux projets parallèles, utiliser des noms d'hôtes distincts (`localhost` et `127.0.0.1`, par exemple) et conserver la même origine pendant chaque session.

## Réseaux et santé

La Gateway possède les interfaces `dmz` et `internal`. Le réseau interne est isolé et les gardes IP/DNS refusent les pairs inattendus. La clé de service Gateway/Superviseur et les jetons signés complètent ces gardes. Le Superviseur n'accepte l'identité que depuis Gateway, le KMS n'accepte ses API que depuis Gateway ; les sondes de santé ont leurs règles propres.

`/health/ready` de la Gateway vérifie le KMS, `/health/frontend` vérifie Nginx ; la vue de monitoring agrège l'état des services. Le démarrage Compose attend aussi que le Superviseur soit sain. [Contrat détaillé](../architecture/gateway-kms.md).
