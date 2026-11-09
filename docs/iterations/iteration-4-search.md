# Itération 4 — recherche globale des connaissances

## Objectif

Rendre la recherche Angular utile sur toute la bibliothèque, et non seulement
sur la page affichée. Intégration dans le CRUD générique existant, sans
changement du modèle d'identité ni exposition directe du KMS.

## Contrat HTTP

GET /api/v1/knowledges?skip=0&limit=20&q=mot&knowledge_type=CODE_SNIPPET&status=DRAFT&is_favorite=true

- q : facultatif, 1 à 100 caractères ; espaces extérieurs ignorés.
  La saisie vide ou composée d'espaces uniquement retourne 422.
- La recherche est littérale, partielle et insensible à la casse ;
  les champs interrogés sont title, description et content.
- is_favorite : booléen optionnel ; true ou false.
- Les critères sont combinés par AND ; les trois champs textuels sont
  combinés par OR.
- Tri historique conservé : created_at décroissant, puis UUID croissant.
- Suppressions logiques exclues et total compté avant skip/limit.
- Aucun changement aux routes de création, lecture unitaire,
  modification conditionnelle (If-Match) et suppression logique.

## Architecture

Angular (formulaire de recherche avec saisie différée et pagination)
→ Gateway Express (transfert inchangé des paramètres)
→ FastAPI (validation)
→ repository PyMongo (filtrage, décompte, tri).

Le frontend ignore les réponses à des requêtes déjà remplacées par
une recherche ou un filtre plus récent, et remet la page à zéro en cas
de changement de filtre. Les valeurs de recherche sont échappées par
re.escape avant passage à MongoDB, pour éviter une injection regex.

## Tests et vérifications

- Tests KMS unitaires : validation HTTP, recherche combinée, paramètres
  invalides, champs textuels, favoris, pagination.
- Tests MongoDB réel jetable : recherche littérale, suppression logique,
  recherche dans les trois champs, favoris et total.
- Contrat HTTP Gateway : test du passage des nouveaux paramètres.
- Tests Angular : transmission de q/is_favorite et omission si absents.

Aucun nettoyage de volume de développement.

## Limites

La recherche utilise une expression régulière non ancrée : elle est
non indexée et peut devenir coûteuse sur un corpus important. Elle n'est
ni une recherche tokenisée, ni un moteur de pertinence, ni un index
RAG. L'interface reste accessible uniquement en local, sans
authentification tant que l'ADR-003 n'a pas été validé.
