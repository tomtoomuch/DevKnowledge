# ADR-003 — Identité, authentification et sécurité

- **Statut :** Acceptée pour le prototype local (itération 5)
    
- **Date :** 2026-10-28
    

## Contexte

DevKnowledge est une application locale qui conserve des connaissances personnelles et utilise un assistant IA.

Elle doit limiter l'accès aux données, protéger les secrets et empêcher que les contenus enregistrés puissent déclencher des actions non autorisées.

## Décisions proposées

### Identité et authentification

- Le fonctionnement courant doit rester possible hors ligne.
    
- L'authentification ne doit pas dépendre d'une validation distante à chaque démarrage.
    
- Une authentification locale **est retenue et implémentée** pour le premier prototype.
- Première identité administrateur créée uniquement par CLI dans le conteneur KMS ; aucun bootstrap HTTP ni inscription publique.
- Identifiants et rôles conservés en MongoDB ; mots de passe hachés avec scrypt et sel aléatoire.
- Sessions opaques révocables, empreinte SHA-256 du jeton stockée en base, cookie HttpOnly, SameSite=Strict, durée de 8 heures.
- Cookies transmis uniquement via la Gateway ; les opérations du navigateur sont protégées par une vérification d'origine et la politique SameSite.
- Les permissions sont contrôlées par le KMS sur chaque route de connaissance. Aucun en-tête X-User-Id ou Authorization fourni par le navigateur n'est une identité fiable.
    
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
    

## Arbitrages reportés

Les étapes d'implémentation ne constituent pas une homologation de sécurité.
Le prototype reste lié à 127.0.0.1 ; HTTPS est obligatoire avant toute
exposition distante, avec AUTH_COOKIE_SECURE=true. La limitation des tentatives
de connexion est locale à une instance de Gateway, non distribuée. Le
changement de mot de passe, la révocation globale, la récupération d'accès,
le chiffrement au repos, l'administration complète des rôles et OIDC sont
des développements ultérieurs.

## Points à confirmer

- Authentification locale obligatoire ou accès réservé à la session de la machine.
    
- Gestion des utilisateurs multiples.
    
- Chiffrement des données au repos et des sauvegardes.
    
- Durée de session et procédure de récupération d'accès.
    

## Conséquences

Ces choix seront précisés avant l'implémentation de l'authentification et l'exposition de fonctionnalités sensibles.