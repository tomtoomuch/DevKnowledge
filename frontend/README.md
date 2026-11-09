# Frontend Angular — DevKnowledge

Première interface graphique locale du CRUD générique existant.
Le navigateur communique uniquement avec la Gateway Express.

## Docker Compose (recommandé)

Avec la configuration .env locale existante, depuis la racine :

    docker compose config --quiet
    docker compose up -d --build
    docker compose ps

Ouvrir http://127.0.0.1:4200 (paramètre FRONTEND_PORT pour le port hôte).
Le conteneur Nginx sert les fichiers Angular et relaie /api/ vers
api-gateway sur le port GATEWAY_PORT au sein du réseau Compose. Les conteneurs KMS et MongoDB
ne sont pas exposés à Internet. Ne jamais utiliser down --volumes pour
arrêter le projet contenant tes données de développement.

## Développement Angular

Démarrer d'abord la Gateway, puis avec Node.js compatible Angular 20 :

    cd frontend
    npm install
    npm start

Le proxy du serveur de développement envoie /api vers 127.0.0.1:3000.
Tests et construction :

    npm run build
    npm test

Le runner Vitest intégré à Angular 20 est expérimental. Le verrouillage
des dépendances npm (package-lock.json) reste à générer et valider sur un
environnement avec accès au registre ; le Dockerfile utilise
temporairement npm install. Un premier build nécessite l'accès aux
registres d'images et de paquets, avant qualification hors ligne.

## Contrat disponible

- GET /api/v1/knowledges : pagination, filtres combinables type/statut,
  texte libre q (1–100 caractères après nettoyage), is_favorite (booléen).
- GET /api/v1/knowledges/{uuid} : ETag en réponse.
- POST /api/v1/knowledges : création.
- PATCH /api/v1/knowledges/{uuid} : If-Match obligatoire.
- DELETE /api/v1/knowledges/{uuid} : If-Match obligatoire,
  suppression logique et réponse HTTP 204.

Les champs d'audit (date, identifiant, révision) restent côté serveur.
Le code 412 signifie qu'un tiers a modifié la connaissance : l'utilisateur
doit relire les changements et décider, sans nouvelle écriture automatique.
Le code 428 impose une nouvelle lecture de la révision. La suppression
est logique et n'est pas une purge physique.

## Périmètre et limites

Les huit types sont sélectionnables ; seules leurs propriétés génériques
(type, titre, contenu, description, langue, difficulté, statut, favori)
sont persistées. Les modèles spécialisés, tags, pièces jointes, historique,
preuves RNCP et assistant RAG ne sont pas encore exposés en CRUD.

La recherche texte (titre, description, contenu) et les filtres favoris,
type et statut opèrent **sur l'ensemble des connaissances non supprimées**,
avant pagination. La recherche est insensible à la casse, littérale (pas
de syntaxe regex) et peut être combinée aux autres filtres. L'API limite
les recherches à 100 caractères. Son implémentation actuelle utilise un
balayage regex de la collection et **n'est pas indexée** : une recherche
textuelle spécialisée devra remplacer ce mécanisme pour les gros corpus. Les statuts DRAFT / VALIDATED / ARCHIVED sont des conventions UI
temporaires, pas une certification de leur valeur métier.

Il n'y a pas encore d'authentification ni de rôles actifs : ne jamais publier
l'interface sur 0.0.0.0 ou via un reverse proxy accessible publiquement.

## Recette manuelle

1. Créer une connaissance, choisir l'un des huit types et enregistrer.
2. Filtrer par type, ouvrir la fiche et consulter sa révision.
3. Modifier le contenu et vérifier l'incrément de la révision.
4. Modifier simultanément depuis une seconde session : l'ancienne session
   doit recevoir un conflit 412, sans écrasement silencieux.
5. Recharger volontairement la fiche pour comparer la nouvelle version.
6. Vérifier une recherche depuis la deuxième page, les filtres favoris,
   type et statut combinés, puis la disparition des éléments supprimés.
7. Confirmer la suppression logique, puis constater la disparition.
8. Couper la Gateway : un message d'erreur doit apparaître sans fausse
   confirmation d'enregistrement.
