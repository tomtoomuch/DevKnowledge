# Monitoring — état de santé des services

## Architecture et sécurité

Tous les appels Angular passent par la Gateway Express. Le seul endpoint utilisé par l'onglet Monitoring est GET /api/v1/monitoring/services. La Gateway relaie exclusivement cette route GET vers le KMS ; le KMS valide la session locale (cookie dk_session) et la permission knowledge.read. Aucune connexion MongoDB n'est effectuée depuis Angular ni depuis la Gateway. Les réponses sont marquées Cache-Control: no-store.

Le KMS utilise son propre client MongoDB pour exécuter un ping. Aucune API Docker ou socket Docker n'est exposée : il s'agit d'une disponibilité applicative et non d'un inventaire des états de conteneurs Docker.

## Sémantique du tableau de bord

- API Gateway : healthy lorsque la requête de monitoring a traversé la Gateway et atteint le KMS.
- Knowledge Service : healthy si l'API répond et MongoDB répond au ping ; degraded dans le cas contraire.
- MongoDB : healthy si le ping réussit ; unavailable en cas d'erreur du pilote ; unknown si aucun client n'est initialisé.
- Si le relais Gateway retourne 502/504, Angular indique une Gateway joignable, un KMS indisponible et un état MongoDB inconnu. Une erreur de réseau ou d'authentification laisse tous les états inconnus : aucune santé n'est inventée.

Le frontend actualise les mesures à l'ouverture de l'onglet, toutes les 30 secondes tant que l'onglet est visible, et sur demande. L'horodatage affiché est celui du contrôle renvoyé par l'API. Les réponses ne sont pas conservées après destruction du composant.

Seuls les services déjà déployés dans le Compose courant sont listés. RAG, ChromaDB, Ollama, MCP et autres services seront ajoutés avec leurs propres sondes et règles d'autorisation lorsqu'ils existeront.

## Vérification

Depuis le frontend connecté, ouvrir Monitoring et confirmer que les trois services apparaissent. Couper temporairement MongoDB dans un environnement de test isolé et vérifier que l'état n'est pas présenté comme sain. Tester l'absence de session et les rôles sans knowledge.read. Sur la Gateway, la route doit refuser POST et les chemins arbitraires. Les tests sont dans backend/api-gateway/tests/kms-proxy.test.js, backend/knowledge-service/tests/test_monitoring.py et frontend/ui-app/src/app/services/monitoring.service.spec.ts.


## Mesures GPU NVIDIA (profil facultatif)

Le monitoring GPU suit exactement le circuit imposé par l'architecture :

```text
Angular -> Gateway Express -> KMS FastAPI -> gpu-monitor (réseau Docker privé)
                                               -> nvidia-smi (pilote NVIDIA)
```

Le navigateur ne connaît que `GET /api/v1/monitoring/services` sur la Gateway. Le KMS interroge un collecteur HTTP interne et fixe (`gpu-monitor:9109`), jamais une URL fournie par le client. Ce collecteur n'est **pas publié sur l'hôte**, ne reçoit aucune session et n'utilise ni socket Docker ni commandes arbitraires. Il n'a pas de dépendances npm externes. Seule la permission de lecture existante est utilisée.

Cette première version concerne les **GPU NVIDIA** avec pilotes, `nvidia-smi` et prise en charge GPU par Docker / NVIDIA Container Toolkit. Une carte AMD, Intel ou Apple n'est pas surveillée par ce collecteur. Le démarrage normal du projet n'exige **aucun GPU** et n'active pas la collecte.

La charge et les compteurs sont des instantanés, actualisés toutes les 30 secondes dans l'onglet ouvert, sans stockage historique :

- `utilization_pct` : activité GPU en % ;
- `memory_used_mib` et `memory_total_mib` : mémoire vidéo allouée et totale en MiB ;
- `temperature_c` : température en °C ;
- `index` et `name` : identifiant local et nom de chaque GPU ; plusieurs cartes sont prises en charge.

Si le matériel ne publie pas un capteur, sa valeur est `null` et Angular affiche **Non disponible**, sans inventer une valeur nulle. Si la collecte est désactivée, l'état est **Non configuré**. Si elle est activée mais indisponible, le GPU apparaît **Collecteur indisponible** ; cela ne transforme pas artificiellement le statut de la Gateway ou de MongoDB en erreur.

### Activer (Git Bash / Docker Desktop)

1. Vérifier qu'une carte NVIDIA est accessible sur l'hôte avec `nvidia-smi` et que l'accès GPU aux conteneurs est pris en charge par Docker/WSL2. Le test Docker avec `--gpus all` doit réussir ; les images nécessaires doivent déjà être disponibles si l'environnement est hors ligne.
2. Depuis la racine DevKnowledge, avec le fichier `.env` habituel, lancer :

```bash
docker compose --env-file .env -f compose.yaml -f compose.gpu.yaml --profile gpu up -d --build
```

3. Se connecter au frontend, puis ouvrir **Monitoring**. La section « GPU NVIDIA » doit afficher les cartes détectées et leurs métriques.

Le fichier `compose.gpu.yaml` ajoute un conteneur `gpu-monitor` optionnel et active `GPU_MONITOR_ENABLED=true` uniquement dans le KMS lorsque cette configuration est utilisée. Il ne modifie pas le socle standard. L'intégration utilise les réservations de périphériques NVIDIA documentées pour Compose, la capacité `utility` étant nécessaire à `nvidia-smi`. Le démarrage peut échouer en absence de GPU / pilote / runtime compatible : ce n'est pas une défaillance du mode sans GPU.

### Mode entièrement hors ligne

Après constitution des images locales requises, le lancement peut se faire sans reconstruction ni téléchargement :

```bash
docker compose --env-file .env -f compose.yaml -f compose.gpu.yaml --profile gpu up -d --no-build --pull never
```

La validation du mode GPU **réel** nécessite une machine équipée. Les tests unitaires utilisent une sortie simulée de `nvidia-smi` afin de s'exécuter sur les runners CI dépourvus de GPU.

Pour revenir au fonctionnement standard, retirer le profil optionnel et relancer le socle habituel après arrêt de la pile précédente (la commande `down` interrompt aussi les autres conteneurs ; effectuer cette opération en connaissance de cause).

### Tests

```bash
cd backend/gpu-monitor && npm test
cd ../knowledge-service && python -m pytest tests/test_gpu_metrics.py tests/test_monitoring.py
```

La CI exécute également `npm test` du collecteur et vérifie que la superposition Compose est syntaxiquement valide, sans requérir de matériel GPU.
