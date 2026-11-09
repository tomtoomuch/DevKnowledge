# Frontend Angular — DevKnowledge

Interface locale du CRUD de connaissances. Le navigateur communique
uniquement avec la Gateway Express. L'authentification locale est obligatoire
en exploitation, et les permissions sont appliquées côté KMS.

## Docker Compose (recommandé)

Les chemins sont relatifs au fichier Compose, pas au dossier d'où est invoquée
la commande. Tous les contextes et Dockerfiles sont déclarés explicitement
dans `compose.yaml`. Pour vérifier les chemins sans démarrer de conteneur,
utiliser depuis la racine :

    python scripts/check_dockerfiles.py --compose compose.yaml --env-file .env

Si un Dockerfile est annoncé absent, vérifier la branche active avec
`git branch --show-current`, puis `git fetch origin` et
`git ls-files frontend/ui-app/Dockerfile backend/api-gateway/Dockerfile backend/knowledge-service/Dockerfile`.
Depuis un sous-dossier, revenir à la racine avant de lancer Compose ;
ne pas utiliser une configuration `COMPOSE_FILE` pointant vers un autre dépôt.

Avec la configuration .env locale existante, depuis la racine :

    docker compose config --quiet
    docker compose up -d --build
    docker compose ps

À la première installation, les conteneurs démarrent mais les connaissances
restent privées jusqu'à la création de l'administrateur. Depuis la racine :

    docker compose exec api-kms python -m app.auth.bootstrap_admin --username admin

La commande demande deux fois un mot de passe de 12 à 256 caractères, sans
l'inscrire dans l'historique Git Bash ou dans .env. Ne l'exécuter qu'une
seule fois sur une base vierge d'utilisateurs. Elle refuse de s'exécuter si
un compte existe déjà ou si le marqueur de bootstrap est présent.

Ouvrir [http://127.0.0.1:4200](http://127.0.0.1:4200) (paramètre FRONTEND_PORT pour le port hôte)
et se connecter avec le compte créé.
Le conteneur Nginx sert les fichiers Angular et relaie /api/ vers
api-gateway sur le port GATEWAY_PORT au sein du réseau Compose. Les conteneurs KMS et MongoDB
ne sont pas exposés à Internet. Ne jamais utiliser down --volumes pour
arrêter le projet contenant tes données de développement.

## Développement Angular

Démarrer d'abord la Gateway, puis avec Node.js compatible Angular 20 :

    cd frontend/ui-app
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
  texte libre q (1–100 caractères après nettoyage), is_favorite (booléen) et
  tag_id (UUID).
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

Les huit types proposent désormais des champs spécialisés facultatifs, validés par le
KMS et persistés dans le sous-document `knowledge_items.details`. Il reste possible
de conserver des fiches génériques sans détails (compatibilité historique).
Un éditeur dynamique permet d'activer, modifier ou retirer ces détails. Les champs
obligatoires de certains types sont vérifiés lors de l'activation des détails ;
la modification du type réinitialise les détails incompatibles.

Le catalogue `knowledge_types` est initialisé séparément et accessible en lecture
via la Gateway sur `GET /api/v1/knowledge-types`. Il ne s'agit pas de huit
collections métier distinctes : le modèle logique 3NF est projeté dans un
sous-document MongoDB atomique. Les entités liées (étapes, modules de cours,
dépendances, technologies, sources), pièces jointes, historique, preuves RNCP
et assistant RAG restent à développer.

Le lot tags (itération 7, PR #9) ajoute le catalogue `tags` et son association
à `knowledge_items.tag_ids`. Les identifiants sont conservés lors des changements
de type ; la sélection ne remplace pas les détails spécialisés. Les tags
peuvent être créés depuis l'éditeur par ADMIN/EDITOR, puis associés à une
connaissance lors de son enregistrement. Le filtre par tag s'applique à
l'ensemble des connaissances non supprimées, avant pagination. Le catalogue
est volontairement immuable à ce stade et l'interface propose les 100 premiers
tags : au-delà, il faudra ajouter recherche et pagination du catalogue.

La recherche texte (titre, description, contenu) et les filtres favoris,
type et statut opèrent **sur l'ensemble des connaissances non supprimées**,
avant pagination. La recherche est insensible à la casse, littérale (pas
de syntaxe regex) et peut être combinée aux autres filtres. L'API limite
les recherches à 100 caractères. Son implémentation actuelle utilise un
balayage regex de la collection et **n'est pas indexée** : une recherche
textuelle spécialisée devra remplacer ce mécanisme pour les gros corpus. Les statuts DRAFT / VALIDATED / ARCHIVED sont des conventions UI
temporaires, pas une certification de leur valeur métier.

Les comptes et rôles locaux sont actifs. Les administrateurs disposent de
tous les droits de connaissance et de l'API de création des utilisateurs.
EDITOR lit, crée et modifie, mais ne supprime pas ; READER lit seulement.
Les contrôles serveur restent obligatoires ; les boutons masqués dans Angular
ne sont qu'un confort d'interface. Ne jamais publier les ports en dehors de
127.0.0.1 ; une exposition distante exige HTTPS et une revue de sécurité.

## Recette des spécialités (itération 6)

1. Créer une fiche de type extrait de code ; activer les détails spécialisés,
   saisir `code` et `programming_language`, enregistrer, relire et modifier.
2. Répéter pour une commande terminal (`command`, `shell`), une norme
   (`reference_code`), et les cinq autres modèles (champs facultatifs).
3. Vérifier que les valeurs `false` des options de sécurité et les entiers sont
   conservés, sans devenir des chaînes de caractères.
4. Vérifier la réponse 422 en cas de détails manquants ou incohérents, et 412
   si deux sessions modifient simultanément la même connaissance.
5. Changer de type : les détails de l'ancien modèle sont retirés à
   l'enregistrement, sans modification des champs génériques historiques.
6. Désactiver les détails dans l'éditeur : ils sont supprimés du document
   lors de l'enregistrement, avec incrément de révision.
7. Ouvrir une ancienne connaissance générique : sa lecture et sa modification
   doivent fonctionner même si le sous-document `details` est absent.

## Recette des tags (itération 7)

1. ADMIN/EDITOR : ouvrir une fiche en création et saisir un tag `Python`.
   Cliquer sur « Ajouter le tag », cocher le tag et enregistrer la fiche.
2. Vérifier le nom du tag sur la fiche, filtrer la bibliothèque par ce tag
   et confirmer que la pagination/les totaux correspondent aux résultats.
3. Réutiliser le même tag sur une autre connaissance (sans recréer le tag).
4. Retirer le tag et enregistrer ; sa définition de catalogue doit rester
   disponible, mais la connaissance ne doit plus apparaître dans le filtre.
5. Confirmer la réponse 409 pour `python` lorsque `Python` existe,
   422 pour un UUID inconnu ou un doublon dans `tag_ids`, et 412
   pour deux modifications concurrentes avec une ancienne révision.
6. Vérifier que READER ne peut pas créer de tag, ni modifier les tags
   d'une fiche ; vérifier que les connaissances historiques sans `tag_ids`
   restent consultables.

## Recette des technologies et versions (itération 7B)

1. Sur une fiche en création, ajouter une technologie `Python` (catégorie
   `Langage`), puis créer une version `3.14`, avec date facultative.
2. Vérifier que la sélection de la version retire l'association générique
   à `Python` ; en revanche `Docker` peut rester associé génériquement.
3. Enregistrer la fiche et retrouver les deux références dans la vue détail.
4. Filtrer la bibliothèque par `Docker` générique puis par version `Python
   3.14`. Le filtrage se fait sur toutes les connaissances avant pagination.
5. Tester un nom de technologie en doublon (409), la même version en doublon
   pour le même parent (409), les références absentes (422), et l'association
   générique+version d'une même technologie (422).
6. Vérifier qu'un PATCH avec un ETag dépassé échoue en 412. Ajouter/retirer
   les associations avec un ETag actuel ; vérifier l'incrément de révision.
7. Vérifier les permissions : READER ne peut ni créer des entrées de catalogue
   ni modifier les connaissances ; les anciens documents sans listes
   `technology_ids` et `technology_version_ids` restent consultables.

**Limites :** 100 technologies et 100 versions maximum chargées
initialement dans l'éditeur. Les références non encore chargées s'affichent
par UUID ; l'API possède la pagination nécessaire à une interface de
recherche avancée. Les catalogues sont immuables : pas de renommage ni
de suppression dans cette itération. La création d'une référence de catalogue
est immédiate, même si l'édition de la fiche est ensuite abandonnée.

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

## Administration locale des comptes

Une fois connecté en tant qu'ADMIN, utiliser **Utilisateurs** dans la barre
latérale (ou **Gestion des utilisateurs** dans l'en-tête sur mobile).
La page permet de consulter les 100 premiers utilisateurs et leurs rôles,
puis de créer un nouveau compte local avec un rôle initial parmi
READER, EDITOR et ADMIN. Aucun mot de passe n'est affiché ou sauvegardé
par Angular, et le formulaire vide ses champs secrets après l'envoi.
La modification des rôles, les réinitialisations de mot de passe et la
révocation globale restent hors périmètre.
