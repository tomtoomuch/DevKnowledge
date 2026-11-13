# Architecture générale de DevKnowledge

## 1. Objectif

DevKnowledge est une application métier locale destinée à organiser, classer, rechercher et exploiter les connaissances accumulées au cours de formations et de travaux pratiques.

L'application doit pouvoir conserver des notes, des extraits de code, des commandes, des solutions à des erreurs, des procédures techniques et des références documentaires.

Son assistant IA doit s'appuyer sur le corpus autorisé de l'utilisateur, citer ses sources et signaler explicitement lorsque les informations disponibles sont insuffisantes.

## 2. Principes d'architecture

- **Local-first :** l'application doit fonctionner localement sans dépendre d'un service cloud pour ses fonctions essentielles.
    
- **Séparation des responsabilités :** chaque service possède un périmètre métier explicite.
    
- **Point d'entrée unique :** le navigateur communique avec l'API Gateway, et non directement avec les microservices ou les bases de données.
    
- **API internes contrôlées :** les services communiquent par des interfaces documentées.
    
- **Sécurité par défaut :** authentification, autorisation, validation des entrées et gestion des secrets.
    
- **Traçabilité :** les décisions d'architecture, les tests et les procédures sont documentés dans Git.
    
- **IA vérifiable :** les réponses de l'assistant doivent présenter les références utilisées et reconnaître les limites du corpus.
    

## 3. Technologies envisagées

| Composant         | Technologie       | Responsabilité                                        |
| ----------------- | ----------------- | ----------------------------------------------------- |
| Frontend          | Angular           | Interface utilisateur                                 |
| API Gateway       | Node.js / Express | Point d'entrée HTTP, contrôle d'accès et routage      |
| User Service      | Python / FastAPI  | Profils, préférences et rôles applicatifs             |
| Knowledge Service | Python / FastAPI  | Gestion des connaissances                             |
| RAG Service       | Python / FastAPI  | Recherche documentaire et orchestration IA            |
| MCP Server        | Python / Fast MCP | Exposition contrôlée d'outils et de ressources        |
| Embedding Worker  | Python            | Calcul des embeddings et indexation                   |
| Base métier cible | PostgreSQL        | Données métier relationnelles, connaissances et RNCP (migration à définir) |\n| Base actuelle et IA | MongoDB         | Stockage actuel des connaissances, futur magasin de métadonnées et LLM |\n| Métriques locales | SQLite 3         | Historique de santé et de GPU du Superviseur |
| Index vectoriel   | ChromaDB          | Recherche sémantique                                  |
| Runtime IA        | Ollama            | Inférence des modèles locaux                          |
| MLOps             | MLflow            | Suivi et évaluation des expérimentations              |

**Décision de stockage du 10 novembre 2026 (ADR-005) : PostgreSQL est retenu comme moteur définitif des futurs domaines métier relationnels.** MongoDB est conservé pour les métadonnées et le LLM. Les données métier actuellement dans MongoDB n'ont pas encore été migrées ; SQLite 3 est utilisé pour les métriques du Superviseur. ChromaDB et Ollama restent des objectifs ultérieurs.\n\nCes technologies constituent la cible initiale. Leur version et leur configuration seront fixées au moment de l'implémentation.

## 4. Architecture logique

```mermaid
---
config:
  layout:elk
---
flowchart TB
    USER["Utilisateur"]
    UI["Frontend Angular"]
    GW["API Gateway<br/>Node.js / Express"]
    AUTH["Fournisseur d'identité<br/>OIDC / OAuth 2.0"]

    subgraph SERVICES["Services internes"]
        US["User Service"]
        KS["Knowledge Service"]
        RAG["RAG Service"]
        MCP["MCP Server"]
        EMB["Embedding Worker"]
    end

    subgraph DATA["Stockage"]
        MDB[("MongoDB")]
        VDB[("ChromaDB")]
        MLF["MLflow et artefacts"]
    end

    OLL["Ollama"]
    MODELS[("Modèles persistants")]

    USER --> UI
    UI --> GW
    UI -.-> AUTH
    GW -.-> AUTH
    GW --> US
    GW --> KS
    GW --> RAG
    GW --> MCP
    US --> MDB
    KS --> MDB
    RAG --> KS
    RAG --> VDB
    KS --> EMB
    EMB --> VDB
    RAG --> OLL
    MCP --> KS
    MCP --> RAG
    OLL --- MODELS
    RAG -.-> MLF
```

Le diagramme représente la cible fonctionnelle. Les composants seront déployés progressivement.

## 5. Règles de communication

- Angular appelle exclusivement l'API Gateway pour accéder aux fonctions métier.
    
- La Gateway applique les contrôles d'accès et route les requêtes.
    
- Le Knowledge Service est responsable des opérations sur les connaissances.
    
- Le RAG Service utilise le Knowledge Service et ChromaDB pour retrouver les informations pertinentes.
    
- Le RAG Service appelle Ollama pour générer une réponse à partir du contexte sélectionné.
    
- Le MCP Server expose uniquement les outils explicitement autorisés.
    
- Aucun service ne doit contourner les contrôles métier en accédant directement aux données d'un autre service.
    

## 6. Déploiement progressif

1. Socle de développement et services minimaux.
    
2. Persistance métier et CRUD des connaissances.
    
3. Identité et autorisations.
    
4. Indexation et recherche sémantique.
    
5. Assistant RAG et modèle local.
    
6. Intégration MCP.
    
7. Évaluation IA et MLOps.
    
8. Sécurité, observabilité et sauvegardes renforcées.
    
9. CI/CD et préparation à la production.
    

## 7. Points restant à valider

- Fournisseur d'identité local.
    
- Organisation exacte des bases MongoDB.
    
- Stratégie de sauvegarde distante.
    
- Versions des composants et compatibilité matérielle.
    
- Modèle local à utiliser selon les capacités de la machine.
## Architecture déployée : réseaux DMZ et interne (novembre 2026)

En complément de la cible future représentée ci-dessus, le Compose
actuel utilise exactement deux réseaux :

- `dmz` : frontend Angular/Nginx et API Gateway Express ;
- `internal` (`internal: true`) : API Gateway Express, Knowledge Service,
  MongoDB et Supervisor.

La Gateway est le seul service présent sur les deux réseaux. **Seule la
Gateway publie son port sur localhost** : toutes les communications
extérieures, y compris les ressources Angular, passent par elle.
La Gateway reste responsable des
contrôles d'accès avant relais, le KMS maintient le stockage interne de
l'identité et le RBAC de défense en profondeur. Le Supervisor fournit des
sondes de santé et la télémétrie GPU facultative, sans publier de port.

Les gardes d'adresses IP internes de KMS et Supervisor sont provisoires :
l'identification cryptographique des pairs (jetons interservices ou mTLS)
sera définie dans une itération de sécurité ultérieure.

Voir [la topologie réseau et les flux](gateway-kms.md) et
[le monitoring](../operations/monitoring.md).
