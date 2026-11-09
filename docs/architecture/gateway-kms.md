# Relais Gateway → KMS — STAB-06

La Gateway est le point d'entrée HTTP par défaut du Compose local. Les cinq
opérations CRUD sont accessibles sur `http://127.0.0.1:3000/api/v1/knowledges`
avec les mêmes corps JSON, filtres, pagination et statuts métier que le KMS.
`GATEWAY_PORT` permet de changer ce port. MongoDB et le KMS ne publient aucun
port sur l'hôte dans `compose.yaml`.

## Contrat du relais

- Chemins admis : `/api/v1/knowledges` et `/api/v1/knowledges/{id}` ; l'identifiant
  est un segment alphanumérique avec tirets (UUID canonique). Les identifiants
  mal formés admis par ce routage sont validés par le KMS. Un slash final est
  retiré avant transmission pour éviter une redirection vers le service interne.
- Les méthodes, paramètres de requête et octets du corps sont transmis sans
  transformation JSON. Les réponses KMS, notamment 201, 204, 404, 405, 422 et
  503, conservent leur statut et leur corps. Aucune écriture n'est réessayée.
- Corps entrant limité à **1 Mio** (413 au-delà), compression entrante refusée
  (415). Ces limites sont propres à l'entrée Gateway ; le contrat KMS est inchangé.
- Destination fixée par `KMS_BASE_URL`, une origine HTTP(S) sans chemin ni
  identifiants. Compose impose `http://api-kms:8000`. Hors Docker, la valeur
  par défaut est `http://127.0.0.1:8000`.
- Seuls `Accept`, `Content-Type`, `Accept-Language` et `If-Match` sont transmis depuis le
  client. `Content-Length` est recalculé. Cookies, Authorization, identités
  déclarées, en-têtes Forwarded et en-têtes de connexion ne sont pas transmis.
- Les en-têtes de réponse admis sont `Content-Type`, `Content-Language`, `Allow`,
  `Retry-After`, `ETag` et `Cache-Control`, hors en-têtes désignés par `Connection`.
  Aucun cookie ou en-tête interne n'est réexposé.
- Délai maximal global vers le KMS : `KMS_TIMEOUT_MS`, par défaut **10 secondes**,
  entier entre 1 et 60 000 ms. Il couvre connexion et transfert de réponse.
  Une connexion impossible produit 502 ; un dépassement de délai produit 504.
  Ces erreurs ne contiennent pas d'adresse interne ou de détails techniques.
- Les redirections amont sont refusées (502), sans les suivre. Une interruption
  après le début d'une réponse coupe le flux : le client doit considérer cette
  réponse comme incomplète. La déconnexion du client ferme la requête amont.

Le relais utilise les modules HTTP(S) de Node ; aucune dépendance supplémentaire.
La réponse est transférée en flux avec la gestion de débit native des streams.
Référence : [API HTTP Node](https://nodejs.org/api/http.html).

## Santé et exposition

`GET /health` vérifie seulement la vivacité de la Gateway. `GET /health/ready`
relaie la readiness du KMS : 200 quand MongoDB est accessible, 503 quand le KMS
signale une panne MongoDB, 502 si le KMS est injoignable, 504 s'il ne répond pas
dans le délai. Le healthcheck Docker de la Gateway vise cette readiness.

La Gateway dépend du KMS `healthy` au démarrage, lui-même dépendant de MongoDB.
`depends_on` organise ce démarrage ; il ne redémarre pas automatiquement les
services quand une dépendance tombe. Les healthchecks rendent la panne visible
et les nouvelles requêtes fonctionnent après rétablissement de la dépendance.

Pour un accès direct de diagnostic au KMS/OpenAPI :

```bash
docker compose -f compose.yaml -f compose.debug.yaml up -d --build
```

OpenAPI devient alors accessible à `http://127.0.0.1:8000/docs`. Pour revenir à
l'exposition normale, recréer le KMS sans cette surcharge :

```bash
docker compose -f compose.yaml up -d --force-recreate api-kms
```

Les exemples historiques visant directement le port 8000 nécessitent désormais
ce mode de diagnostic ; les appels CRUD habituels doivent utiliser le port Gateway.

## Validation et limites

Les tests Gateway utilisent un serveur HTTP réel sur port éphémère. Ils couvrent
la transmission, les statuts, les en-têtes, les tailles, les chemins exclus, les
délais, les interruptions et la configuration. `python scripts/check_stabilization.py`
exécute aussi les cinq opérations via les vrais conteneurs, avec MongoDB isolé,
puis les coupures MongoDB et KMS et leur reprise. La CI rejoue ces scénarios.

Ce relais n'introduit **aucune authentification ou autorisation**. Il reste local,
le créateur demeure anonyme, et l'ADR-003 doit être tranché avant l'ajout d'identité.
STAB-08 ajoute les écritures conditionnelles obligatoires ([[knowledge-concurrency]]) et les outils de sauvegarde/restauration ([[../operations/backup-restore]]).
