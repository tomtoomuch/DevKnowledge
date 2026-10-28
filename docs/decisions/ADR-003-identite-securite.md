# ADR-003 — Identité, authentification et sécurité

- **Statut :** À valider
    
- **Date :** 2026-10-28
    

## Contexte

DevKnowledge est une application locale qui conserve des connaissances personnelles et utilise un assistant IA.

Elle doit limiter l'accès aux données, protéger les secrets et empêcher que les contenus enregistrés puissent déclencher des actions non autorisées.

## Décisions proposées

### Identité et authentification

- Le fonctionnement courant doit rester possible hors ligne.
    
- L'authentification ne doit pas dépendre d'une validation distante à chaque démarrage.
    
- Une authentification locale est envisagée pour le premier prototype.
    
- Une intégration OIDC/OAuth 2.0 pourra être étudiée ultérieurement si un besoin de fédération d'identité est confirmé.
    

### Autorisations

- Les services appliquent le principe du moindre privilège.
    
- Les accès aux données passent par les interfaces prévues.
    
- Le serveur MCP ne dispose pas d'un accès direct et illimité aux bases de données.
    
- Chaque outil MCP doit être explicitement autorisé et limité à sa fonction.
    

### Secrets et journaux

- Les secrets ne sont pas versionnés dans Git.
    
- Les fichiers de configuration sensibles sont exclus du dépôt.
    
- Les journaux ne doivent pas exposer de mots de passe, jetons ou contenus personnels inutiles.
    

### Sécurité de l'assistant IA

- Les connaissances récupérées sont considérées comme des données, jamais comme des instructions système fiables.
    
- Les réponses doivent s'appuyer sur le corpus autorisé.
    
- Les sources utilisées doivent être citées lorsque cela est possible.
    
- L'assistant doit signaler lorsque les connaissances disponibles sont insuffisantes.
    
- Les actions ayant des effets de bord doivent faire l'objet de contrôles explicites.
    

## Points à confirmer

- Authentification locale obligatoire ou accès réservé à la session de la machine.
    
- Gestion des utilisateurs multiples.
    
- Chiffrement des données au repos et des sauvegardes.
    
- Durée de session et procédure de récupération d'accès.
    

## Conséquences

Ces choix seront précisés avant l'implémentation de l'authentification et l'exposition de fonctionnalités sensibles.