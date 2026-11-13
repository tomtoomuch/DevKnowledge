# Monitoring centralisé : Supervisor

## Architecture

Toute requête du navigateur passe par
`Navigateur -> Gateway Express -> KMS FastAPI` (API) et
`Navigateur -> Gateway Express -> Angular/Nginx` (HTML/assets).
Le point d'entrée unique
des métriques côté navigateur est `GET /api/v1/monitoring/services`, en
lecture seule. La Gateway vérifie la session et la permission
`knowledge.read`; le KMS refait ces vérifications pour la défense en
profondeur, puis récupère l'instantané du collecteur.

Le service **supervisor** (anciennement `gpu-monitor`) fonctionne en
permanence dans `compose.yaml`, même sans GPU. Il effectue les sondes
applicatives sur des destinations fixes et uniquement internes :

- Frontend/Nginx : le Supervisor appelle la sonde interne
  `http://api-gateway:${GATEWAY_PORT}/health/frontend` ;
  **la Gateway** appelle le frontend à travers `dmz`
  (`http://frontend:80/health/frontend`). Le Supervisor n'est pas
  connecté au réseau DMZ ;
- Gateway : `http://api-gateway:${GATEWAY_PORT}/health` ;
- KMS : `http://api-kms:8000/health` ;
- MongoDB : contrôlée via `http://api-kms:8000/health/ready`, laquelle
  réalise le ping avec le client MongoDB existant du KMS ;
- Supervisor : succès de l'assemblage de sa propre réponse.

Le collecteur n'utilise ni identifiant MongoDB, ni socket Docker, ni
port publié sur l'hôte. Son endpoint `GET /snapshot` est interne
(`supervisor:9109`), avec un JSON limité et validé par le KMS, sans
transmission des URL privées, exceptions et autres secrets au navigateur.
La disponibilité MongoDB est `unknown` lorsque le KMS n'est pas
interrogeable, pas artificiellement `unavailable`.

Le tableau de bord affiche les cinq services (frontend, Gateway, KMS,
MongoDB, supervisor), ainsi que les métriques NVIDIA si elles sont activées.
Les vérifications ont lieu à l'ouverture de l'onglet, toutes les
30 secondes tant qu'il est visible, et lors de l'actualisation manuelle.
Aucun historique n'est conservé à ce stade.

## GPU facultatif

Le Compose de base déploie le supervisor sans accès GPU. Sur les
machines NVIDIA prises en charge (NVIDIA Container Toolkit, Docker
Desktop avec WSL2, pilote compatible), la surcouche `compose.gpu.yaml`
ajoute l'accès GPU à **ce même supervisor**. Elle ne lance pas
un second microservice.

```bash
docker compose --env-file .env -f compose.yaml -f compose.gpu.yaml up -d --build
```

Pour l'instance de test isolée déjà utilisée :

```bash
FRONTEND_PORT=4201 GATEWAY_PORT=3001 \
docker compose -p devknowledge-gpu-test --env-file ../DevKnowledge/.env \
  -f compose.yaml -f compose.gpu.yaml up -d --build
```

Le service supervisor interroge `nvidia-smi` sans shell et transmet
utilisation %, VRAM utilisée/totale (MiB), température (°C) et nom/index
du GPU. Une sonde indisponible est `unavailable` ou `unknown`, un GPU
désactivé est `disabled`. Le statut du GPU ne modifie pas le calcul
de santé applicative.

## Validation

```bash
cd backend/supervisor && npm test
cd ../knowledge-service && python -m pytest tests/test_supervisor_client.py tests/test_monitoring.py
```

Sur le poste, vérifier `docker compose ps` (cinq services avec le
supervisor, sans port Gateway publié), puis ouvrir le frontend sur
`http://127.0.0.1:4201`. Après connexion, l'onglet Réseau du
navigateur doit montrer `GET /api/v1/monitoring/services` en 200,
avec `services` et `gpu.status`. La Gateway doit refuser 401 en
absence de cookie ; elle ne donne jamais accès direct au supervisor.

Pour résoudre un problème de connexion de l'instance jetable,
consulter [Authentification et ports](auth-gateway.md).

## Frontend Angular : présentation séparée des mesures

L'onglet Monitoring est organisé en trois composants Angular standalone :

- `MonitoringComponent` : charge le snapshot depuis la Gateway, gère
  les autorisations, l'état des requêtes et la période de rafraîchissement ;
- `MonitoringServiceCardsComponent` : représente les cinq états de santé,
  détails de sondes, y compris les états dégradés/inconnus ;
- `MonitoringGpuPanelComponent` : affiche le GPU NVIDIA détecté, ses jauges
  d'utilisation/VRAM et sa température (ou un message de sonde désactivée).

Les sous-composants n'effectuent aucun appel HTTP. Le service Angular
`MonitoringService` appelle seulement `/api/v1/monitoring/services`.

## Topologie réseau et limites des sondes

Le Compose définit `dmz` (frontend + Gateway) et `internal`
(Gateway + KMS + MongoDB + Supervisor, avec `internal: true`).
Le Supervisor ne consulte pas Nginx directement, puisque les deux services
ne partagent aucun réseau. Le contrôle des pairs à l'intérieur d'un réseau
est provisoirement fondé sur leurs adresses IP internes et le DNS Docker.
Les jetons d'identité entre microservices seront traités séparément ;
ils ne sont pas encore en place.
