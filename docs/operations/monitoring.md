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
