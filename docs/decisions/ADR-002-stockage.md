# ADR-002 — Stratégie de stockage des connaissances

- **Statut :** Acceptée
    
- **Date :** 2026-10-28
    

## Contexte

DevKnowledge doit permettre de stocker, organiser et retrouver des connaissances techniques personnelles : notes de cours, extraits de code, commandes, procédures, documentations et solutions à des problèmes rencontrés.

L'application doit fonctionner hors ligne et conserver la maîtrise des données par l'utilisateur.

## Décision

### Stockage principal

MongoDB constitue la source de vérité pour les connaissances structurées et les métadonnées.

Les données sont conservées localement, dans un volume persistant. La suppression ou la reconstruction de l'index vectoriel ne doit pas entraîner la perte des connaissances originales.

### Recherche sémantique

ChromaDB est utilisé comme index vectoriel pour la recherche sémantique.

Les embeddings sont générés localement par un service dédié. L'index vectoriel peut être reconstruit à partir des connaissances conservées dans MongoDB.

### Sauvegardes

Les sauvegardes sont facultatives et initiées ou configurées par l'utilisateur.

La stratégie devra prévoir :

- des sauvegardes locales régulières ;
    
- une possibilité de sauvegarde externe chiffrée ;
    
- une procédure documentée de restauration ;
    
- des tests de restauration périodiques.
    

Aucune synchronisation distante automatique n'est imposée.

### Réseau et confidentialité

Les services communiquent au moyen du réseau Docker local. Les ports exposés à la machine hôte sont limités au nécessaire.

Aucune connaissance personnelle ne doit être transmise à un service cloud sans décision explicite de l'utilisateur.

## Conséquences

- MongoDB conserve les connaissances de référence.
    
- ChromaDB conserve les vecteurs et les données nécessaires à la recherche sémantique.
    
- Les volumes Docker doivent être persistants.
    
- La perte de l'index vectoriel doit être récupérable sans perte des connaissances originales.
    
- La sauvegarde et la restauration doivent être testées avant une utilisation réelle.
    
- La stratégie de chiffrement des sauvegardes externes sera définie avant leur mise en place.
    

## Alternatives écartées

- **Stockage exclusivement vectoriel :** écarté, car l'index ne doit pas être l'unique source de vérité.
    
- **Stockage cloud obligatoire :** écarté, car il contredit le fonctionnement local prioritaire.
    
- **Synchronisation bidirectionnelle automatique :** reportée, car elle exige une stratégie explicite de gestion des conflits.