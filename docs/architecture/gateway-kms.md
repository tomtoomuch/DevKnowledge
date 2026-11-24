# Communication obligatoire : Angular → Gateway → Superviseur / KMS

## Contrat des flux — Gateway point d'entrée unique

**Tout trafic extérieur (frontend Angular inclus) arrive d'abord au
Gateway Express.** Son port interne `GATEWAY_PORT` (3000 par défaut)
est l'unique port publié localement, sous
`127.0.0.1:${FRONTEND_PORT:-4200}`.

```text
Navigateur --HTTP localhost:4200/4201--> Gateway Express
                                             |
                    +------------------------+-----------------------+
                    | dmz                    | internal              | internal
                    v                        v                       v
              Angular/Nginx             Superviseur               KMS FastAPI
              (HTML, JS, CSS)        (identité, sessions,       (métier, vérification
                                     émission des JWT)          des JWT internes)
                                             |                       |
                                             +------ MongoDB --------+
                                              comptes distincts

Seule la Gateway publie un port hôte.
```

Les ressources du frontend passent par un reverse-proxy **GET/HEAD**
dans Express vers `http://frontend:80` sur `dmz`. Aucun cookie
de session ni jeton utilisateur n'est transmis à Nginx. Les URL
`/api/v1/*` sont prises en charge par la Gateway elle-même puis
relayées au Superviseur pour l'identité et les comptes, ou au KMS avec un jeton interne pour le métier, sur `internal` après authentification et contrôle RBAC.
Les chemins inconnus sous `/api/` ou `/health/` retournent 404
sans tomber dans la page Angular.

Nginx reste privé, relié exclusivement à `dmz`, et rejette `/api/`.
L'interface Angular utilise uniquement des URL relatives
`/api/v1/*` vers le Gateway. Les autres microservices n'ont aucun
port publié sur l'hôte. La Gateway est seule à posséder les deux
interfaces réseau `dmz` et `internal`.

Le KMS et le Supervisor ont leurs gardes provisoires de pairs réseau :
sur `/api/v1`, KMS n'accepte que la Gateway ; ses sondes
`/health` et `/health/ready` acceptent également le Supervisor,
ainsi que l'adresse loopback pour le healthcheck local. Le Supervisor
n'accepte `/snapshot` que depuis le KMS ; son `/health` est réservé
à son propre healthcheck loopback. Les appels inattendus reçoivent 404.
MongoDB n'expose pas de route HTTP ; son accès requiert les identifiants
MongoDB applicatifs.

Ces contrôles d'origine utilisent les adresses IP obtenues par le DNS
interne Docker. Uvicorn ignore les en-têtes proxy entrants pour déterminer
l'adresse du pair : ils ne prouvent **pas** l'identité cryptographique
du service appelant et ne protègent pas contre un conteneur compromis
ayant des privilèges réseau élevés. Le circuit d'identité utilise également une clé partagée Gateway/Superviseur et des jetons HS256 émis par le Superviseur pour le KMS. Les gardes échouent de
façon sécurisée si la résolution DNS interne échoue.

## Authentification et autorisation

La Gateway porte la responsabilité du contrôle d'accès HTTP externe :
vérification du cookie de session opaque `dk_session`, interrogation
du référentiel d'identité du Superviseur et vérification des permissions
avant tout relais métier. Les identifiants et sessions persistent dans MongoDB sous l'autorité du Superviseur. Le KMS vérifie la signature, l'audience, l'expiration et la permission du jeton interne. Les routes d'identité KMS sont absentes en mode obligatoire. La création du premier administrateur se fait par `scripts/bootstrap_supervisor.py`, jamais par une route publique. Voir [la migration identité](../operations/identity-migration.md).

Voir [le guide Authentification et ports](../operations/auth-gateway.md).

## Relais HTTP

Les chemins sont déclarés explicitement dans Express, en particulier
`/api/v1/knowledges`, `/api/v1/auth/*`, les catalogues et
`GET /api/v1/monitoring/services`. Les routes métier CRUD acceptent
seulement la collection et un segment d'identifiant, avec les méthodes
et les contrôles d'accès requis. La Gateway ne relaie pas les routes
arbitraires du KMS et refuse de servir l'application Angular
pour les routes API inexistantes.

Seuls les en-têtes autorisés transitent ; le cookie de session `dk_session` est envoyé uniquement au Superviseur. Le KMS reçoit le jeton interne émis pour la requête, jamais le cookie, le bearer navigateur ou des identités déclarées par le navigateur. Taille du corps métier plafonnée
à 1 Mio ; délais, réponses de panne et validation suivent le contrat
du relais Node existant. Les requêtes de connexion sont ralenties et
les écritures cross-origin refusées.

`GET /health` vérifie la Gateway ; `GET /health/ready` demande la
readiness du KMS ; `GET /health/frontend` sonde Nginx depuis la Gateway
à travers la DMZ. Ces sondes techniques ne contiennent pas de secrets.
La surveillance agrégée se consulte, après authentification, par
`GET /api/v1/monitoring/services`.

## Vérification

```bash
docker compose --env-file .env config --quiet
docker compose --env-file .env ps
```

Dans `ps`, **seule la Gateway** présente un port hôte lié à
`127.0.0.1` (4200 vers 3000 par défaut).
Frontend, KMS, MongoDB et Supervisor n'ont aucun port publié.
Pour inspecter un service de manière autorisée, employer
`docker compose exec` sur son conteneur ; ne pas publier directement
ses ports. L'ancienne superposition `compose.debug.yaml` de
publication du KMS a été retirée.

La CI est configurée pour vérifier la topologie, la propagation HTTP par la
Gateway, les refus d'accès, les jetons interservices et les scénarios de reprise.
La signature asymétrique et la rotation à clés multiples restent un lot de
durcissement distinct de la migration qualifiée localement.
