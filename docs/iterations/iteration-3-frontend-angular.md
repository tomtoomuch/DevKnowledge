# Itération 3 — frontend Angular du CRUD DevKnowledge

## Périmètre implémenté

- Interface standalone Angular, servie par Nginx, accès local.
- Connexion unique à l'API Gateway Express via /api/.
- Liste et pagination KMS ; filtres serveur type/statut ;
  recherche texte et favoris limités à la page chargée.
- Fiche détaillée, création, modification et suppression logique.
- Lecture ETag et condition If-Match, gestion des conflits 412.
- Tests unitaires du contrat HTTP côté Angular.
- Service frontend ajouté au Compose et job de CI pour build + tests.

## Écarts et travaux futurs

Le MLD à 56 tables est un modèle logique, pas le schéma MongoDB actuel.
Les huit spécialisations ne sont pas encore persistées et ne sont pas
présentées comme des formulaires métier complets. Pour recherche globale,
tags, versions, RNCP, preuves, RBAC et RAG, il faudra préalablement
implémenter les contrats API correspondants.

Le verrouillage npm et la qualification du premier build hors ligne
restent ouverts. Les build/tests doivent être confirmés dans la CI ;
une simple configuration ne prouve pas une exécution réussie.

Voir le guide frontend/README.md pour la recette manuelle.

Mise à jour : la limite de recherche à la page affichée est levée dans l'itération 4 ([[iteration-4-search]]).
