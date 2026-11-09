# Itération 5 — identité locale et RBAC (prototype)

## Objectif

DevKnowledge fonctionne sans fournisseur OIDC externe. Le KMS contrôle
l'accès à ses connaissances ; l'API Gateway ne relaie que le cookie de
session opaque et uniquement vers les routes prévues. L'interface Angular
distingue les utilisateurs authentifiés et affiche uniquement leurs
actions autorisées.

## Initialisation sans effacer les connaissances

1. Démarrer normalement avec `docker compose up -d --build`.
2. Créer **une fois** l'administrateur sur la base existante :

   `docker compose exec api-kms python -m app.auth.bootstrap_admin --username admin`

   Saisir et confirmer le mot de passe à l'invite (12 à 256 caractères).
   Ne pas placer le mot de passe dans la commande, le dépôt ou `.env`.
3. Ouvrir http://127.0.0.1:4200 et se connecter avec ce compte.
4. Ne jamais exécuter `docker compose down --volumes` pour un jeu de
   données réel. Le marqueur de bootstrap est conservé même si une erreur
   survient après son acquisition : récupérer manuellement sous contrôle
   de l'administrateur, et ne pas supprimer le marqueur sans audit.

## Collections MongoDB

- `users` : identifiants, scrypt salé, statut et dates d'audit.
- `roles`, `permissions` : référentiels locaux initialisés au démarrage.
- `user_roles`, `role_permissions` : relations RBAC.
- `sessions` : empreintes SHA-256 des jetons opaques et date d'expiration
  (TTL MongoDB, plus contrôle serveur systématique).
- `auth_bootstrap` : verrou de première initialisation. Jamais de
  mécanisme de réinitialisation HTTP.

## Matrice de permissions

| Rôle | Lire | Créer | Modifier | Supprimer | Gérer les comptes |
| --- | --- | --- | --- | --- | --- |
| ADMIN | Oui | Oui | Oui | Oui | Oui |
| EDITOR | Oui | Oui | Oui | Non | Non |
| READER | Oui | Non | Non | Non | Non |

Les permissions sont recalculées en base à chaque requête et non dérivées
d'en-têtes utilisateur. Les profils sont actuellement partagés au niveau de
la bibliothèque ; le filtrage par propriétaire et par projet reste à
concevoir, avant RAG et tout outil MCP.

## Contrats

- `POST /api/v1/auth/login` : `{"username":"...", "password":"..."}`,
  200 avec profil public + cookie HttpOnly SameSite=Strict, 401 sinon.
- `GET /api/v1/auth/me` : profil courant et permissions, 401 sinon.
- `POST /api/v1/auth/logout` : 204, révocation du jeton et effacement du
  cookie navigateur.
- `GET /api/v1/users` : liste d'utilisateurs, ADMIN seulement.
- `POST /api/v1/users` : création d'un compte avec `username`,
  `password` et `roles` parmi ADMIN/EDITOR/READER ; ADMIN seulement.
- Toutes les routes GET/PATCH/POST/DELETE des connaissances exigent
  une session valide et une permission adaptée.

Une interface graphique Angular d'administration (ADMIN uniquement) expose
la **consultation** des 100 premiers comptes avec rôles et la **création**
d'un compte avec un rôle initial. Elle ne permet pas encore la désactivation,
la modification des rôles ou la récupération d'un mot de passe. Les droits
restent vérifiés dans le KMS, indépendamment de l'interface.

## Sécurité et limites

Le mot de passe est haché avec scrypt, sel aléatoire par utilisateur,
paramètres intégrés au hachage. Le premier administrateur est créé par
CLI seulement. Les sessions durent 8 heures, sont stockées sous forme
d'empreintes, et sont révoquées explicitement à la déconnexion. Le KMS
revérifie le statut du compte et ses permissions à chaque demande.

La Gateway vérifie Origin sur les requêtes qui l'envoient et rejette
les requêtes signalées `Sec-Fetch-Site: cross-site`. Son ralentisseur
de connexions est en mémoire et ne convient pas à plusieurs instances.
Le cookie n'est pas Secure pour le HTTP localhost ; prévoir TLS,
`AUTH_COOKIE_SECURE=true`, une politique CSRF renforcée et une revue
sécurité avant toute exposition distante.

Une désactivation explicite de l'authentification (AUTH_MODE=disabled)
n'est utilisée que dans les conteneurs de tests jetables : Compose
normal impose AUTH_MODE=required. Elle ne doit jamais être activée
pour une application exposée, ni sur une base contenant des données
sensibles.

Non couverts : modification de mot de passe, récupération de compte,
désactivation via API, renouvellement de session, révocation de toutes
les sessions, OIDC et MFA.

## Validation

- Tests scrypt, permissions et cookie.
- Tests de la Gateway pour les en-têtes, cookies, origine et limitations.
- Test d'intégration MongoDB jetable de la création du premier compte,
  de l'authentification et des rôles, de la déconnexion et des refus.
- Tests HTTP Angular pour me, login et logout.
- Critères de sortie : CI entièrement réussie, recette manuelle sur
  une copie/sauvegarde des données locales, revue des mécanismes de
  récupération d'accès. Aucune fusion sans validation.

Le paramétrage scrypt initial est N=2^15, r=8, p=3 (32 Mio de mémoire),
conformément à une des configurations minimales documentées par OWASP ;
un réétalonnage est nécessaire avant une montée en charge.

Le proxy Angular de développement conserve le Host original afin que la
protection Origin de la Gateway soit compatible avec `npm start`.
Le protocole public est contrôlé par `GATEWAY_PUBLIC_SCHEME=http` en local ;
si un reverse proxy TLS est introduit, coordonner `https` et
`AUTH_COOKIE_SECURE=true`.

## Validation des Dockerfiles

Les trois chemins de construction du Compose principal sont explicites :
`frontend/Dockerfile`, `backend/api-gateway/Dockerfile` et
`backend/knowledge-service/Dockerfile`. Le script
`python scripts/check_dockerfiles.py --compose compose.yaml --env-file .env`
utilise `docker compose config --format json` pour vérifier l'existence du
contexte et du Dockerfile avant la construction, sans afficher les secrets.
Le même contrôle est intégré aux workflows pour le Compose principal et les
compositions de tests. Il faut exécuter ces commandes depuis la racine du
dépôt et utiliser la branche à jour ; `docker build .` à la racine n'est
pas supporté.
