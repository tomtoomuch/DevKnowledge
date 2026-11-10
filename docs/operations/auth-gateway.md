# Authentification et ports — Gateway obligatoire

## Topologie du navigateur

Le navigateur ouvre **uniquement** le frontend Angular/Nginx, lié à
`127.0.0.1:${FRONTEND_PORT:-4200}` sur le poste. Le port de test 4201 est
uniquement un autre port de cette **interface web**, pas un accès direct au KMS.
Nginx sert les ressources statiques Angular et reverse-proxy les URLs relatives
`/api/v1/**` vers `api-gateway:${GATEWAY_PORT:-3000}` **sur le réseau Docker**.
Il n'existe plus de publication `127.0.0.1:3000/3001` pour la Gateway dans
`compose.yaml`. KMS, MongoDB et collector n'ont pas non plus de port publié.

```text
Navigateur --HTTP localhost:4200/4201--> Nginx + Angular
                                            |
                                            +-- /api/v1/* --> Gateway Express
                                                               |
                                                               +--> KMS FastAPI (privé)
                                                               |      +--> MongoDB (privé)
                                                               |      +--> Collector (privé)
                                                               |
                                                               +--> KMS /auth/me (session)
```

L'authentification et le filtrage des autorisations HTTP au **point d'entrée
externe** sont sous responsabilité de la Gateway Express, avec contrôle de
l'Origin, limitation des tentatives de connexion, vérification de la session
`dk_session` et du RBAC avant chaque relais. Le KMS joue encore le rôle
**interne de référentiel d'identité** : il conserve les comptes, hache/vérifie
les mots de passe et persiste les sessions dans MongoDB ; il revalide également
les permissions en défense en profondeur. La séparation complète du stockage
d'identité vers un service dédié reste une étape distincte. **Ne pas confondre
la responsabilité de la Gateway comme frontière d'authentification et le
stockage technique interne des identifiants dans KMS.**

Aucun appel direct Angular → KMS, MongoDB ou collector n'est autorisé.
`AUTH_MODE=required` est fixé explicitement pour Gateway et KMS dans le
Compose normal. Seules les piles CI jetables désactivent les deux contrôles
via un override spécialisé. Un navigateur sans session obtient 401 depuis
la Gateway ; un rôle insuffisant obtient 403. En cas d'indisponibilité du
référentiel d'identité, la Gateway refuse l'accès (503), sans laisser
passer de requêtes non authentifiées.

## Premier administrateur dans une instance de test indépendante

**Un volume MongoDB neuf ne contient pas tes comptes de `dev`.** Si tu
utilises `-p devknowledge-gpu-test`, il faut créer une fois un compte
administrateur dans **cette instance**, sans réinitialiser le volume.

Depuis le worktree `DevKnowledge-chat` :

```bash
docker compose -p devknowledge-gpu-test --env-file ../DevKnowledge/.env \
  -f compose.yaml -f compose.gpu.yaml exec api-kms \
  python -m app.auth.bootstrap_admin --username admin
```

Choisir un mot de passe de 12 à 256 caractères, puis le confirmer dans
l'invite masquée. Ne jamais partager ce mot de passe ni l'inscrire dans
`.env`, Git ou la commande shell. Sous Git Bash/mintty, si Docker refuse
le TTY interactif, préfixer exactement la commande par `winpty`.

S'il existe déjà un compte, le bootstrap **refuse** de s'exécuter.
Il ne faut pas supprimer les utilisateurs, le verrou
`auth_bootstrap` ou le volume MongoDB pour contourner ce refus.

Après création, ouvrir `http://127.0.0.1:4201`, se connecter, puis ouvrir
Monitoring. Le navigateur envoie les requêtes relatives
`/api/v1/auth/login`, `/api/v1/auth/me` et
`/api/v1/monitoring/services` **via Nginx et la Gateway**.
La cookie `dk_session` est HttpOnly, Path=/api/v1 et SameSite=Strict.

## Diagnostic des erreurs

- **401 sur POST /api/v1/auth/login** : utilisateur absent ou mauvais mot
  de passe ; sur un volume neuf, vérifier l'initialisation ci-dessus.
- **403** : Origin/cookie cross-site rejeté par Gateway ou rôle insuffisant ;
  utiliser la même origine `localhost:4201` pour toute la session.
- **429** : trop de tentatives ; attendre la fin de la limitation.
- **502/503/504** : problème de Gateway/KMS/dépendance interne ; inspecter
  les conteneurs et les logs sans publier les ports internes.
- **401 sur GET /api/v1/auth/me** : absence de cookie valide, session expirée
  ou compte désactivé. La Gateway refuse l'accès avant les ressources privées.

**Attention aux cookies entre environnements parallèles :** les cookies HTTP
ne sont pas isolés par numéro de port. Deux applications ouvertes sur
`http://localhost:4200` et `http://localhost:4201` partagent le même
cookie `dk_session` : une connexion peut invalider celle de l'autre.
Pour la recette locale, choisir des noms d'hôtes distincts : par exemple
`http://localhost:4200` pour `dev` et `http://127.0.0.1:4201`
pour `devknowledge-gpu-test`. Ne pas mélanger les deux noms d'hôte
au sein d'une même session.

Ne pas utiliser `docker compose down --volumes` sur la pile de développement
réelle. Les données de `dev` et de l'instance isolée restent distinctes.

## Cloisonnement réseau DMZ et interne

Le Compose définit exactement deux réseaux **gérés par Compose** :
`dmz`, réseau bridge d'accès entre le frontend et la Gateway, et
`internal`, réseau bridge avec `internal: true` pour la Gateway,
le KMS, MongoDB et le Collector. La Gateway a deux interfaces réseau.
La DMZ est un réseau Docker *edge*, pas un réseau `external: true`
préexistant ni un port publié de la Gateway. Seul le frontend publie
son port sur `127.0.0.1`.

Les sondes du frontend passent par la Gateway et la DMZ ; les appels du
Collector au KMS sont limités aux deux endpoints de santé. KMS n'accepte
les API privées que depuis la Gateway (gardes d'adresses IP internes,
à remplacer par une authentification cryptographique entre services).
Les appels rejetés retournent 404 sans divulguer les services internes.

Voir [le contrat Gateway-KMS](../architecture/gateway-kms.md).
