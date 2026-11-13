# Authentification et ports — Gateway obligatoire

## Topologie du navigateur — invariant obligatoire

**TOUTES les communications depuis l'extérieur, frontend compris,
traversent d'abord l'API Gateway Express.** C'est le seul service
avec un port Docker publié : par défaut
`127.0.0.1:${FRONTEND_PORT:-4200}` redirige vers son port interne
`GATEWAY_PORT=3000`. Le port 4201 d'une instance de test peut pointer
vers le Gateway d'un autre projet Compose ; il ne publie pas Nginx.

```text
Navigateur / client --localhost:4200--> API Gateway Express
                                           | dmz (GET/HEAD pages, CSS, JS)
                                           +-----> Frontend Angular/Nginx (privé)
                                           |
                                           | internal (/api/v1/* uniquement)
                                           +-----> KMS FastAPI (privé)
                                                      |
                                                      +-----> MongoDB
                                                      +-----> Supervisor
```

Le Gateway reverse-proxy les ressources Angular depuis Nginx sur la DMZ ;
Nginx ne publie aucun port hôte et **refuse `/api/`**. Toutes les
requêtes métier restent sur `/api/v1/*` et passent par le contrôle
d'authentification et de permissions du Gateway. Les chemins API inconnus
ne doivent jamais être redirigés vers le `index.html` Angular.
Les méthodes autres que GET/HEAD ne sont pas admises par le relais frontend.

Le Gateway conserve les contrôles d'Origin, limitation de connexion,
cookie `dk_session`, RBAC et délégation des vérifications au KMS.
KMS reste le magasin interne des comptes, rôles, mots de passe hachés
et sessions MongoDB ; il applique lui aussi les permissions.
Le relais de ressources **ne transmet jamais les cookies, Authorization
ni les en-têtes d'identité utilisateur à Nginx**, même pour une page
privée : la sécurité des connaissances reste sur les API.

Le Compose normal impose `AUTH_MODE=required` dans Gateway et KMS ;
seules les piles de test jetables utilisent un override désactivant
l'authentification. En cas d'identité invalide 401/403 ; en cas de
référentiel indisponible 503. Frontend, KMS, MongoDB et Supervisor
n'exposent pas de ports hôte.

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
`/api/v1/monitoring/services` **directement vers la Gateway**, qui
relaie uniquement les appels autorisés au KMS.
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
le KMS, MongoDB et le Supervisor. La Gateway a deux interfaces réseau.
La DMZ est un réseau Docker *edge*, pas un réseau `external: true`
préexistant. **Seule la Gateway publie un port hôte**, sur
`127.0.0.1`. Nginx est privé sur la DMZ.

Les sondes du frontend passent par la Gateway et la DMZ ; les appels du
Supervisor au KMS sont limités aux deux endpoints de santé. KMS n'accepte
les API privées que depuis la Gateway (gardes d'adresses IP internes,
à remplacer par une authentification cryptographique entre services).
Les appels rejetés retournent 404 sans divulguer les services internes.

Voir [le contrat Gateway-KMS](../architecture/gateway-kms.md).
