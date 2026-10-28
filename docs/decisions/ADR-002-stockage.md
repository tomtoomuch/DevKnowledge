# ADR-002 — Stockage des connaissances

- **Statut :** Proposé
    
- **Date :** 2026-10-28
    
- **Décideur :** Projet DevKnowledge
    

## Contexte

DevKnowledge stockera des notes, des articles, des commandes, des extraits de code, des procédures et des références documentaires.

Les contenus peuvent avoir des métadonnées variables : catégories, tags, dates, sources, versions et relations entre connaissances.

L'application doit fonctionner localement et permettre la reconstruction de l'index de recherche sémantique à partir des données métier.

## Décision envisagée

Utiliser MongoDB comme stockage principal des documents de connaissances.

Le Knowledge Service sera le seul service responsable des opérations métier sur ces documents.

ChromaDB sera utilisé comme index vectoriel distinct. Il ne constituera pas la source de vérité.

## Alternatives étudiées

### SQLite

- Léger, simple à sauvegarder et adapté à un fonctionnement local.
    
- Approprié aux données relationnelles et aux petits déploiements.
    
- Moins naturel pour des documents aux structures variables et une architecture comportant plusieurs services.
    

### PostgreSQL

- Transactions, contraintes relationnelles et requêtes SQL puissantes.
    
- Convient aux données structurées et peut également proposer des capacités vectorielles.
    
- Demande un modèle relationnel plus explicite pour des contenus hétérogènes.
    

### MongoDB

- Modèle documentaire adapté aux structures de connaissances variables.
    
- Possibilité d'indexer les champs utilisés par les recherches métier.
    
- Nécessite une validation rigoureuse des documents et une conception attentive des index.
    

## Justification

MongoDB correspond à l'orientation documentaire de DevKnowledge et au modèle proposé dans le blueprint BrainBlox.

Ce choix ne dispense pas de définir un schéma logique, des règles de validation, des identifiants stables et des règles d'accès.

## Conséquences positives

- Stockage documentaire des connaissances.
    
- Métadonnées extensibles.
    
- Séparation entre données métier et index vectoriel.
    
- Possibilité de reconstruire l'index vectoriel depuis les données sources.
    

## Conséquences négatives

- Une base supplémentaire à administrer et à sauvegarder.
    
- Nécessité de gérer les migrations et l'évolution des documents.
    
- Cohérence entre le contenu métier et son indexation à organiser explicitement.
    

## Règles de conception

- Le Knowledge Service est propriétaire des connaissances.
    
- Les autres services utilisent son API plutôt que sa base.
    
- Les suppressions et modifications déclenchent une mise à jour ou une réindexation contrôlée.
    
- Les sauvegardes MongoDB et ChromaDB sont traitées séparément.
    
- La stratégie de sauvegarde distante sera documentée dans un ADR distinct.
    

## Conditions de validation

Valider ce choix après avoir défini un modèle de connaissance représentatif et testé les opérations de création, lecture, modification, suppression et recherche.

## Réévaluation

Réexaminer cette décision si les exigences de transactions, de relations ou de requêtes analytiques rendent une base relationnelle plus appropriée.