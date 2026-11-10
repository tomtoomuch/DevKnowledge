# Communication obligatoire : Angular → Gateway → KMS

## Contrat des flux

Le navigateur ne peut contacter que le serveur Angular/Nginx lié à
`127.0.0.1:${FRONTEND_PORT:-4200}` (`4201` sur l'instance GPU de test).
Les requêtes API `/api/v1/**` de Nginx sont relayées uniquement vers
`api-gateway:${GATEWAY_PORT:-3000}` sur le réseau Docker **dmz**.
La Gateway appartient aux réseaux **dmz** et **internal** et relaie les
routes autorisées vers le KMS uniquement sur **internal**. Son port n'est
pas publié sur l'hôte.

```text
Navigateur --HTTP localhost:4200/4201--> Angular/Nginx
                                              | dmz
                                              v
                                         Gateway Express
                                              | internal
                            +-----------------+------------------+
                            |                 |                  |
                         KMS FastAPI       Collector          MongoDB
                            |             (sondes HTTP)     (client KMS)
                            +-----> MongoDB    |
                            +<----- Collector  +-----> Gateway /health/frontend
                                                         |
                                                         +----dmz----> Nginx
```

Le KMS et le Collector ont leurs gardes provisoires de pairs réseau :
sur `/api/v1`, KMS n'accepte que la Gateway ; ses sondes
`/health` et `/health/ready` acceptent également le Collector,
ainsi que l'adresse loopback pour le healthcheck local. Le Collector
n'accepte `/snapshot` que depuis le KMS ; son `/health` est réservé
à son propre healthcheck loopback. Les appels inattendus reçoivent 404.
MongoDB n'expose pas de route HTTP ; son accès requiert les identifiants
MongoDB applicatifs.

Ces contrôles d'origine utilisent les adresses IP obtenues par le DNS
interne Docker. Uvicorn ignore les en-têtes proxy entrants pour déterminer
l'adresse du pair : ils ne prouvent **pas** l'identité cryptographique
du service appelant et ne protègent pas contre un conteneur compromis
ayant des privilèges réseau élevés. Le déploiement futur introduira un
mécanisme d'authentification service-à-service avec renouvellement
des secrets et vérification de chaque appel. Les gardes échouent de
façon sécurisée si la résolution DNS interne échoue.

## Authentification et autorisation

La Gateway porte la responsabilité du contrôle d'accès HTTP externe :
vérification du cookie de session opaque `dk_session`, interrogation
du référentiel d'identité interne du KMS et vérification des permissions
avant tout relais API. Les identifiants et sessions persistent encore
dans le KMS/MongoDB ; le KMS effectue à son tour le contrôle RBAC
comme défense en profondeur. La création du premier administrateur
se fait uniquement par CLI, jamais par une route publique.

Voir [le guide Authentification et ports](../operations/auth-gateway.md).

## Relais HTTP

Les chemins sont déclarés explicitement dans Express, en particulier
`/api/v1/knowledges`, `/api/v1/auth/*`, les catalogues et
`GET /api/v1/monitoring/services`. Les routes métier CRUD acceptent
seulement la collection et un segment d'identifiant, avec les méthodes
et les contrôles d'accès requis. La Gateway ne relaie pas les routes
arbitraires du KMS.

Seuls les en-têtes autorisés transitent ; le cookie de session `dk_session`
est le seul cookie transmis, jamais les autres cookies, le jeton bearer
ou des identités déclarées par le navigateur. Taille du corps plafonnée
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

Dans `ps`, **seul le frontend** a un port hôte lié à `127.0.0.1`.
Le KMS, MongoDB, le Collector et la Gateway n'ont aucun port publié.
Pour inspecter un service de manière autorisée, employer
`docker compose exec` sur son conteneur ; ne pas publier directement
ses ports. L'ancienne superposition `compose.debug.yaml` de
publication du KMS a été retirée.

La CI vérifie la topologie, la propagation HTTP par la Gateway, les
refus d'accès et les scénarios de reprise. La validation des identités
interservices cryptographiques est prévue pour une itération ultérieure.
