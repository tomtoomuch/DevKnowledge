# DevKnowledge — Plan directeur de développement et de mise en production

**Version :** 1.0  
**Type de projet :** application métier distribuée, microservices, IA locale et MLOps  
**Environnement initial :** poste de développement local sous Windows, Docker Desktop  
**Objectif :** réaliser une application professionnelle de gestion et d'exploitation de connaissances techniques, utilisable comme projet de portfolio.

---

## 1. Vision et objectifs

DevKnowledge centralise des connaissances techniques : notes de cours, commandes terminal, extraits de code, documentations, procédures Docker, solutions de bugs et bonnes pratiques.

L'application doit permettre de :

- enregistrer, classer, rechercher et modifier des connaissances ;
    
- retrouver des informations par recherche textuelle et sémantique ;
    
- interroger un modèle LLM local avec un système RAG qui s'appuie exclusivement sur les connaissances autorisées et enregistrées ;
    
- exposer certaines capacités à des agents compatibles avec le protocole MCP ;
    
- tracer et évaluer les performances du système IA ;
    
- industrialiser les tests, les images Docker et les déploiements ;
    
- superviser l'ensemble des services ;
    
- séparer les environnements de développement, de validation et de production.
    

### Principes directeurs

1. Chaque microservice possède une responsabilité claire.
    
2. Le frontend ne communique qu'avec la passerelle Node.js / Express.
    
3. Les API internes ne sont pas exposées directement à Internet.
    
4. Chaque base de données possède un propriétaire logique unique.
    
5. Les données métier constituent la source de vérité du RAG.
    
6. Les modèles locaux sont versionnés et évalués.
    
7. La sécurité, les tests, la documentation et la supervision sont développés dès le début.
    
8. Aucun passage à la phase suivante sans validation des critères de sortie de la phase courante.
    

---

## 2. Architecture cible

### 2.1. Couche d'accès

|Composant|Technologie|Responsabilité|
|---|---|---|
|Frontend|Angular|Interface utilisateur, navigation, recherche et édition|
|API Gateway|Node.js / Express|Point d'entrée unique, routage, contrôle d'accès, limitation de débit|
|Fournisseur d'identité|Keycloak, à confirmer|OIDC, authentification, gestion des identités et des rôles|

### 2.2. Couche métier et IA

|Microservice|Technologie|Responsabilité|
|---|---|---|
|Knowledge API|Python / FastAPI|CRUD, validation et règles métier|
|Search API|Python / FastAPI|Recherche textuelle, filtres et classement|
|RAG API|Python / FastAPI|Orchestration de la recherche documentaire et de la génération|
|Embedding Worker|Python|Extraction, découpage, calcul des embeddings et indexation|
|LLM Runtime|Ollama ou runtime équivalent|Inférence des modèles locaux|
|MCP Server|Python / SDK MCP officiel|Exposition contrôlée de tools, resources et prompts|
|ML Pipeline|Python|Préparation des données, évaluation et entraînement éventuel|
|Model Registry|MLflow|Suivi des expériences, métriques et versions de modèles|

### 2.3. Couche de persistance

Les cinq espaces de données sont distingués par fonction. Ils ne correspondent pas nécessairement à cinq moteurs de bases de données différents.

|Identifiant|Usage|Technologie initialement envisagée|
|---|---|---|
|DB1|Connaissances et métadonnées métier|SQLite|
|DB2|Profils locaux, rôles applicatifs et audit|SQLite|
|DB3|État des tâches et données d'exploitation|SQLite|
|DB4|Index vectoriel du RAG|Qdrant|
|DB5|Métadonnées d'expériences ML|Base relationnelle compatible avec MLflow|

Les poids des modèles, les documents volumineux et les artefacts ML nécessiteront des volumes persistants ou un stockage d'artefacts distinct. Ils ne doivent pas être confondus avec les métadonnées de DB5.

**Évolution possible :** PostgreSQL pourra remplacer SQLite lorsque la concurrence d'écriture, la disponibilité ou les besoins d'exploitation le justifieront.

### 2.4. Couche d'exploitation

|Composant|Technologie envisagée|Responsabilité|
|---|---|---|
|Conteneurisation|Docker et Docker Compose|Exécution et orchestration locale|
|CI/CD|GitHub Actions|Tests, contrôles, construction et déploiement|
|Runner local|Runner isolé, si nécessaire|Exécution de tâches CI/CD locales ou spécifiques|
|Métriques|Prometheus|Collecte et stockage des métriques|
|Tableaux de bord|Grafana|Visualisation et alertes|
|Logs|Loki et Alloy|Centralisation et exploration des journaux|
|Sécurité logicielle|Outils de lint, scans de dépendances et d'images|Détection précoce des défauts et vulnérabilités|

---

## 3. Calendrier directeur

Le calendrier proposé est de 20 semaines, auxquelles pourra s'ajouter une période de stabilisation. Il s'agit d'une estimation, pas d'une date de livraison garantie.

|Phase|Période indicative|Résultat attendu|
|---|---|---|
|P0 — Cadrage et conception|Semaine 1|Architecture et exigences validées|
|P1 — Socle technique|Semaines 2–3|Dépôt, Docker, services de base et tests|
|P2 — Persistance et API métier|Semaines 4–5|CRUD opérationnel et testé|
|P3 — Frontend et authentification|Semaines 6–7|Application utilisable avec OIDC|
|P4 — Recherche documentaire|Semaines 8–9|Recherche textuelle et sémantique|
|P5 — RAG et modèles locaux|Semaines 10–12|Assistant IA fondé sur les sources|
|P6 — Serveur MCP|Semaine 13|Outils accessibles aux clients MCP autorisés|
|P7 — MLOps|Semaines 14–15|Indexation et évaluation reproductibles|
|P8 — Sécurité et supervision|Semaines 16–17|Contrôles, métriques, logs et alertes|
|P9 — CI/CD et environnements|Semaines 18–19|Pipeline et déploiements DEV/STAGE/PROD|
|P10 — Mise en production|Semaine 20 et après|Livraison, restauration testée et documentation d'exploitation|

---

# PHASE P0 — Cadrage et conception

**Durée :** 1 semaine  
**Objectif :** éviter de développer des services dont les responsabilités se chevauchent.

### Fonctionnalités et travaux

- Définir les types de connaissances pris en charge.
    
- Définir les profils d'utilisateurs et les droits d'accès.
    
- Écrire les cas d'utilisation principaux.
    
- Définir les contrats d'API et les formats d'erreur.
    
- Définir les cinq espaces de persistance.
    
- Définir les flux RAG et MCP.
    
- Définir les exigences de sécurité et de confidentialité.
    
- Définir les critères de qualité et de mise en production.
    

### Livrables

- `docs/architecture.md`
    
- `docs/adr/` : décisions d'architecture justifiées
    
- `docs/api-contracts.md`
    
- `docs/security.md`
    
- `docs/roadmap.md`
    

### Critères de sortie

- Chaque service a une responsabilité définie.
    
- Chaque base possède un propriétaire.
    
- Les flux publics et internes sont documentés.
    
- Le périmètre de la première version est maîtrisé.
    

---

# PHASE P1 — Socle technique

**Durée :** 2 semaines  
**Objectif :** obtenir un environnement local reproductible.

## Microservice : frontend Angular

Travaux :

- Initialiser l'application Angular.
    
- Configurer le routage.
    
- Créer les pages de base : accueil, liste des connaissances, détail et recherche.
    
- Définir une organisation cohérente des composants et services Angular.
    

## Microservice : API Gateway Express

Travaux :

- Initialiser le projet Node.js.
    
- Configurer les routes `/api/v1`.
    
- Ajouter Helmet, la validation des entrées et une gestion centralisée des erreurs.
    
- Limiter la taille des requêtes.
    
- Créer les routes de santé `/health/live` et `/health/ready`.
    
- Prévoir le routage vers les API internes.
    

## Microservices Python

Initialiser les squelettes FastAPI de la Knowledge API et de la RAG API.

À ce stade, les deux services peuvent retourner des réponses de test. Le RAG ne doit pas encore être fonctionnel.

## Infrastructure Docker

- Créer un Dockerfile par service.
    
- Créer un premier `compose.yaml`.
    
- Séparer les réseaux publics et internes.
    
- Préparer les volumes persistants.
    
- Utiliser des fichiers `.env.example` sans secrets.
    
- Exclure les secrets, bases locales et fichiers volumineux de Git.
    

### Tests

- Tests unitaires des endpoints de santé.
    
- Vérification des ports exposés.
    
- Vérification du démarrage et de l'arrêt des conteneurs.
    
- Vérification du comportement lorsque l'un des services est indisponible.
    

### Livrables

- Arborescence du dépôt.
    
- Docker Compose initial.
    
- README de démarrage.
    
- Tests de santé verts.
    

### Critères de sortie

Tous les services démarrent, les contrôles de santé fonctionnent et le frontend n'accède pas directement aux API internes.

---

# PHASE P2 — Persistance et API métier

**Durée :** 2 semaines  
**Objectif :** disposer d'une base métier fonctionnelle avant d'ajouter l'IA.

## Microservice : Knowledge API

### Modèle de connaissance

Champs proposés :

- `id`
    
- `title`
    
- `content`
    
- `category`
    
- `tags`
    
- `createdAt`
    
- `updatedAt`
    
- `sourceType`
    
- `sourceReference`
    

Les champs techniques d'indexation seront ajoutés lorsque le RAG sera développé.

### Fonctionnalités

- Créer une connaissance.
    
- Lire une connaissance.
    
- Lister les connaissances avec pagination.
    
- Modifier une connaissance.
    
- Supprimer une connaissance.
    
- Filtrer par catégorie et tags.
    
- Valider strictement les données reçues.
    
- Utiliser des requêtes SQL paramétrées.
    
- Versionner les migrations de base de données.
    

### Persistance

DB1 sera initialement implémentée en SQLite. Le service sera le seul propriétaire de cette base et le seul à la modifier.

DB2 et DB3 seront créées selon les besoins identifiés, sans y dupliquer prématurément les données de DB1.

### Tests

- Tests unitaires de validation.
    
- Tests d'intégration CRUD.
    
- Tests de contraintes et de données invalides.
    
- Tests de pagination.
    
- Tests des codes HTTP.
    
- Tests avec une base temporaire.
    
- Tests de migration.
    

### Livrables

- Modèle de données.
    
- Migrations.
    
- API documentée.
    
- Suite de tests.
    
- Exemples de requêtes dans la documentation.
    

### Critères de sortie

Le CRUD est entièrement testé, les erreurs sont cohérentes et les données restent disponibles après redémarrage du conteneur.

---

# PHASE P3 — Frontend et authentification

**Durée :** 2 semaines  
**Objectif :** rendre l'application utilisable avec un contrôle d'accès.

## Frontend Angular

Fonctionnalités :

- Page d'accueil.
    
- Liste paginée des connaissances.
    
- Formulaire de création.
    
- Édition et suppression.
    
- Filtres par catégorie et tags.
    
- Gestion des états de chargement et d'erreur.
    
- Affichage accessible des résultats.
    

## API Gateway Express

Fonctionnalités :

- Routage vers la Knowledge API.
    
- Validation des paramètres et des requêtes.
    
- Gestion des sessions et des autorisations.
    
- Limitation de débit.
    
- Contrôle des origines et configuration CORS stricte.
    
- Normalisation des erreurs renvoyées au frontend.
    

## Identité : fournisseur OIDC

Keycloak est une option cohérente pour un environnement local conteneurisé.

Travaux :

- Définir le client OIDC.
    
- Configurer les URI de redirection.
    
- Mettre en place Authorization Code avec PKCE.
    
- Définir les rôles applicatifs.
    
- Tester les sessions expirées et les refus d'accès.
    

L'architecture de session doit être choisie explicitement. Pour limiter l'exposition des jetons dans le navigateur, privilégier une approche BFF avec session serveur et cookie sécurisé lorsque le déploiement le permet.

### Tests

- Tests des parcours de connexion et déconnexion.
    
- Tests des accès anonymes.
    
- Tests des rôles et autorisations.
    
- Tests des erreurs d'authentification.
    
- Tests de bout en bout des principaux parcours.
    

### Critères de sortie

Un utilisateur autorisé peut gérer ses connaissances via Angular. Un utilisateur non authentifié ou sans permission ne peut pas effectuer les opérations protégées.

---

# PHASE P4 — Recherche documentaire

**Durée :** 2 semaines  
**Objectif :** retrouver efficacement les connaissances avant d'introduire la génération.

## Microservice : Search API

Fonctionnalités :

- Recherche textuelle.
    
- Recherche par titre, catégorie et tags.
    
- Classement des résultats.
    
- Pagination.
    
- Filtres selon les autorisations.
    
- Réponse structurée avec identifiants et références des sources.
    

## Base vectorielle : DB4

- Déployer Qdrant dans un conteneur.
    
- Créer la collection d'indexation.
    
- Définir les identifiants de documents et de chunks.
    
- Définir les métadonnées utiles au filtrage.
    
- Préparer une stratégie de reconstruction de l'index.
    

## Embedding Worker

Fonctionnalités initiales :

- Récupérer les connaissances modifiées.
    
- Normaliser les textes.
    
- Découper les documents en segments.
    
- Calculer les embeddings avec un modèle local.
    
- Indexer les segments dans Qdrant.
    
- Tracer les versions du modèle d'embedding.
    

### Tests

- Recherche de termes connus.
    
- Recherche de concepts exprimés différemment.
    
- Tests de filtrage.
    
- Tests de mise à jour et de suppression.
    
- Tests de reconstruction de l'index.
    

### Critères de sortie

La recherche textuelle et la recherche sémantique renvoient des résultats pertinents. L'index peut être reconstruit à partir des données métier.

---

# PHASE P5 — RAG et modèles locaux

**Durée :** 3 semaines  
**Objectif :** fournir un assistant qui répond à partir du corpus autorisé.

## Microservice : LLM Runtime

Travaux :

- Installer Ollama ou un runtime équivalent.
    
- Choisir un modèle compatible avec les ressources matérielles.
    
- Conserver les modèles dans un volume persistant.
    
- Vérifier la disponibilité du runtime.
    
- Mesurer la consommation mémoire et la latence.
    
- Séparer le modèle génératif du modèle d'embedding.
    

## Microservice : RAG API

### Étape 1 — Retrieval

- Recevoir la question.
    
- Calculer son embedding.
    
- Rechercher les passages candidats.
    
- Ajouter une recherche textuelle si nécessaire.
    
- Filtrer selon les droits d'accès.
    

### Étape 2 — Context Builder

- Dédupliquer les passages.
    
- Classer les résultats.
    
- Limiter le nombre de chunks.
    
- Respecter le budget de contexte du modèle.
    
- Préparer les références des sources.
    

### Étape 3 — Génération

- Construire un prompt avec les extraits sélectionnés.
    
- Demander au modèle de distinguer les faits issus des sources des informations manquantes.
    
- Produire une réponse structurée.
    
- Associer les citations aux passages utilisés.
    

### Étape 4 — Gestion de l'insuffisance

- Définir un seuil de pertinence initial.
    
- Refuser de produire une réponse factuelle lorsque les sources sont insuffisantes.
    
- Signaler explicitement les limites du corpus.
    
- Ne jamais prétendre qu'une réponse est prouvée si les citations ne la soutiennent pas.
    

### Étape 5 — Interface utilisateur

Angular doit afficher :

- la question ;
    
- la réponse ;
    
- les sources utilisées ;
    
- les passages justificatifs ;
    
- les erreurs et l'insuffisance documentaire.
    

### Tests

- Questions dont la réponse est connue.
    
- Questions absentes du corpus.
    
- Documents contradictoires.
    
- Tentatives d'injection de prompt dans des documents.
    
- Vérification des citations.
    
- Mesure de la latence.
    
- Tests de non-régression du retrieval.
    

### Critères de sortie

Le RAG retourne des réponses vérifiables, cite correctement ses sources et signale les cas où les connaissances enregistrées ne suffisent pas.

---

# PHASE P6 — Serveur MCP

**Durée :** 1 semaine  
**Objectif :** permettre à des clients compatibles MCP d'exploiter les capacités autorisées de DevKnowledge.

## Microservice : MCP Server

Technologie : Python avec le SDK MCP officiel.

Transport envisagé : Streamable HTTP pour les échanges avec des clients distants sur le réseau autorisé.

### Tools

Première version :

- `search_knowledge`
    
- `get_knowledge`
    
- `create_knowledge`
    
- `update_knowledge`
    
- `ask_rag`
    

L'outil de suppression pourra être ajouté après validation des mécanismes d'autorisation et de confirmation.

### Resources

- Fiche d'une connaissance.
    
- Documentation technique enregistrée.
    
- Procédure ou extrait de code.
    
- Références aux résultats documentaires du RAG.
    

### Prompts

- Analyser une erreur technique à partir des connaissances disponibles.
    
- Préparer une procédure de déploiement.
    
- Expliquer une commande ou un concept à partir du corpus.
    

### Sécurité

- Valider chaque argument.
    
- Appliquer les permissions du demandeur.
    
- Restreindre les outils accessibles.
    
- Ne pas exposer directement les bases.
    
- Limiter les durées et volumes de réponse.
    
- Journaliser les appels sans enregistrer inutilement des contenus sensibles.
    

### Tests

- Découverte des tools, resources et prompts.
    
- Validation des schémas d'entrée.
    
- Tests des erreurs et des autorisations.
    
- Tests de connexion depuis un client MCP de référence.
    
- Tests d'indisponibilité des API dépendantes.
    

### Critères de sortie

Un client MCP autorisé peut découvrir et utiliser les outils prévus sans contourner les règles métier ni les autorisations.

---

# PHASE P7 — MLOps et gestion des modèles

**Durée :** 2 semaines  
**Objectif :** rendre l'indexation et l'évaluation reproductibles.

## Microservice : ML Pipeline

Fonctionnalités :

- Préparer un corpus de référence.
    
- Détecter les documents modifiés.
    
- Générer des jeux de questions d'évaluation.
    
- Évaluer le retrieval et les réponses.
    
- Comparer plusieurs modèles d'embedding ou modèles génératifs.
    
- Enregistrer les résultats et les versions utilisées.
    

## MLflow

DB5 sera utilisée pour les métadonnées d'expériences. Les artefacts volumineux seront stockés séparément.

Fonctionnalités :

- Enregistrer les paramètres et métriques.
    
- Comparer les expériences.
    
- Référencer les versions de modèles.
    
- Documenter les critères d'acceptation.
    
- Conserver un historique des évaluations.
    

## Publication contrôlée

Une version candidate doit passer les tests de qualité avant de devenir la version de référence.

La publication doit identifier :

- la version du modèle ;
    
- la version du modèle d'embedding ;
    
- les paramètres d'inférence ;
    
- les données d'évaluation ;
    
- les métriques obtenues ;
    
- la date de validation.
    

### Critères de sortie

Une expérience est reproductible, les résultats sont traçables et une nouvelle version peut être évaluée sans modifier arbitrairement la configuration de production.

---

# PHASE P8 — Sécurité et supervision

**Durée :** 2 semaines  
**Objectif :** préparer l'exploitation et faciliter le diagnostic.

## Supervision

### Prometheus

Collecter notamment :

- disponibilité des services ;
    
- latence des API ;
    
- taux d'erreur ;
    
- consommation CPU et mémoire ;
    
- temps d'inférence ;
    
- erreurs de retrieval ;
    
- temps d'indexation.
    

### Grafana

Créer des tableaux de bord pour :

- l'état général de la plateforme ;
    
- les API ;
    
- les bases et stockages ;
    
- les services IA ;
    
- les pipelines MLOps.
    

### Logs

Déployer Loki et Alloy, ou une solution équivalente.

Les journaux devront être structurés et corrélables par identifiant de requête. Les jetons, secrets et contenus sensibles ne devront pas être journalisés en clair.

## Sécurité

- Revue des permissions des conteneurs.
    
- Réduction des ports exposés.
    
- Contrôle des secrets.
    
- Scans des dépendances et images.
    
- Vérification des règles d'autorisation.
    
- Limitation de débit.
    
- Validation des entrées.
    
- Politique de conservation des logs.
    
- Sauvegardes et tests de restauration.
    
- Procédure de gestion des vulnérabilités.
    

### Critères de sortie

Les services critiques disposent de métriques, les erreurs sont diagnostiquables, les alertes principales sont définies et les contrôles de sécurité ont été testés.

---

# PHASE P9 — CI/CD et environnements

**Durée :** 2 semaines  
**Objectif :** industrialiser les tests, les images et les déploiements.

## Pipeline CI/CD

### Étape CI

- Vérification du style.
    
- Tests unitaires.
    
- Tests d'intégration.
    
- Tests de contrat API.
    
- Tests du protocole MCP.
    
- Vérification des dépendances.
    
- Analyse statique.
    
- Construction des images Docker.
    

### Étape de sécurisation

- Scan des images.
    
- Contrôle des secrets.
    
- Vérification des versions de dépendances.
    
- Production d'un inventaire des composants lorsque possible.
    
- Traçabilité des images produites.
    

### Étape de déploiement

- Déploiement en DEV.
    
- Tests de fumée.
    
- Promotion en STAGE.
    
- Validation fonctionnelle et sécurité.
    
- Approbation du déploiement PROD.
    
- Vérification après déploiement.
    
- Retour arrière si les critères de santé échouent.
    

## Runner CI/CD

Le runner local est facultatif. Il sera isolé et limité à ses besoins. L'accès au socket Docker ne sera pas accordé sans justification, car il peut donner un contrôle étendu sur l'hôte.

## Environnements

|Environnement|Usage|Politique|
|---|---|---|
|DEV|Développement quotidien|Changements fréquents, données de test|
|STAGE|Validation avant livraison|Configuration proche de la production, tests de migration et de restauration|
|PROD|Utilisation stable|Versions validées, sauvegardes, surveillance et retour arrière|

Ces environnements pourront être simulés localement au début, mais devront utiliser des configurations, secrets, volumes et jeux de données séparés.

### Critères de sortie

Une modification validée peut traverser les environnements sans reconstruction manuelle improvisée. Le déploiement, les migrations et le retour arrière sont documentés et testés.

---

# PHASE P10 — Mise en production

**Durée :** 1 semaine minimum, puis stabilisation continue.

## Préparation

- Geler une version candidate.
    
- Exécuter l'ensemble des tests.
    
- Vérifier les scans de sécurité.
    
- Contrôler les variables de configuration.
    
- Vérifier les volumes persistants.
    
- Exécuter une sauvegarde.
    
- Tester la restauration.
    
- Vérifier les comptes et permissions.
    
- Vérifier les modèles disponibles et leurs versions.
    
- Vérifier les procédures de redémarrage.
    
- Préparer une procédure de retour arrière.
    

## Déploiement

1. Déployer les services et configurations validés.
    
2. Appliquer les migrations de manière contrôlée.
    
3. Vérifier les healthchecks.
    
4. Tester les parcours métier.
    
5. Tester le RAG et ses citations.
    
6. Tester les outils MCP autorisés.
    
7. Vérifier les métriques et les journaux.
    
8. Confirmer la réussite des sauvegardes.
    
9. Documenter la version déployée.
    

## Critères d'acceptation de production

- Aucun défaut critique connu.
    
- Tests automatisés réussis.
    
- Authentification et autorisations vérifiées.
    
- Sauvegarde et restauration validées.
    
- Métriques et alertes opérationnelles.
    
- Modèles et index versionnés.
    
- Procédures de mise à jour et de retour arrière documentées.
    
- Aucune exposition publique non prévue.
    

Une mise en production locale ne signifie pas que le système est automatiquement prêt pour une exposition sur Internet. Celle-ci nécessitera notamment une revue réseau, TLS, gestion des secrets, durcissement de l'hôte, stratégie de sauvegarde hors machine et analyse des risques.

---

## 4. Vue synthétique par microservice

|Microservice|Phase de création|Phase de stabilisation|
|---|---|---|
|Angular|P1–P3|P8–P10|
|Express Gateway|P1–P3|P8–P10|
|Identity / OIDC|P3|P8–P10|
|Knowledge API|P1–P2|P8–P10|
|Search API|P4|P7–P10|
|Embedding Worker|P4|P7–P10|
|RAG API|P5|P7–P10|
|LLM Runtime|P5|P7–P10|
|MCP Server|P6|P8–P10|
|ML Pipeline|P7|P9–P10|
|MLflow|P7|P8–P10|
|DB1–DB5 et stockages|P2–P7|P8–P10|
|Prometheus / Grafana / logs|P8|P9–P10|
|CI/CD Runner|P9, si nécessaire|P10|

---

## 5. Méthode de travail pour chaque microservice

Chaque microservice suivra le même cycle de développement :

1. **Conception** : responsabilité, contrat API, données et dépendances.
    
2. **Squelette** : structure du projet, configuration, Dockerfile et healthchecks.
    
3. **Implémentation** : fonctionnalités minimales.
    
4. **Tests unitaires** : logique métier et cas limites.
    
5. **Tests d'intégration** : bases, services dépendants et contrats.
    
6. **Sécurité** : permissions, validation, secrets et erreurs.
    
7. **Observabilité** : logs, métriques et healthchecks.
    
8. **Documentation** : installation, configuration, tests et exploitation.
    
9. **CI/CD** : automatisation des contrôles.
    
10. **Validation** : critères de sortie satisfaits avant la suite.
    

### Définition commune de « terminé »

Une fonctionnalité n'est terminée que si son comportement est testé, ses erreurs sont gérées, sa configuration est documentée, ses permissions sont définies et son exécution est reproductible.

---

## 6. Priorités pour le portfolio

Les éléments les plus démonstratifs seront :

- une architecture de microservices claire ;
    
- des API FastAPI et Express testées ;
    
- une authentification OIDC correctement intégrée ;
    
- un RAG local avec citations vérifiables ;
    
- un serveur MCP avec outils contrôlés ;
    
- un pipeline MLOps mesurant la qualité ;
    
- une chaîne CI/CD avec contrôles de sécu