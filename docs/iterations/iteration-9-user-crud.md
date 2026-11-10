---
title: "DevKnowledge — Gestion complète des utilisateurs locaux"
date: "2026-11-10"
status: "PR #12 en brouillon ; tests CI et recette manuelle nécessaires"
tags: [devknowledge, identite, crud, rbac, comptes]
---

# CRUD des utilisateurs et gestion des sessions

## Modèle de données

La table logique `users` conserve les identifiants de comptes comme
`_id` MongoDB (UUID sérialisé), le pseudonyme, le hachage scrypt,
`account_status` (`ACTIVE`, `DISABLED`, `DELETED`), les dates et
la `revision` de concurrence.

Les collections `roles`, `permissions`, `user_roles` et
`role_permissions` sont maintenues. Une projection atomique
`users.role_codes` est désormais utilisée pour l'autorisation des
comptes créés ou modifiés, afin d'éviter qu'un changement de rôles
multi-documents ne laisse des droits partiellement modifiés pendant
une requête. Les anciennes fiches d'utilisateur sans `role_codes`
restent compatibles avec `user_roles`. La projection `user_roles`
continue d'être synchronisée mais sa mise à jour n'est pas transactionnelle
sur MongoDB autonome.

La collection `identity_admin_mutex` contient un verrou à bail
temporaire pour sérialiser les mutations administratives entre instances
du KMS : cela évite la révocation concurrente des derniers administrateurs
dans les conditions nominales. Le bail peut être repris après interruption ;
une transaction MongoDB multi-documents serait nécessaire pour des
garanties fortes en cas de pause dépassant ce bail.

## API via la Gateway

Toutes les routes ci-dessous requièrent `users.manage` dans la Gateway
et dans le KMS. Il n'existe **aucune inscription publique**.

| Route | Description | Principales réponses |
| --- | --- | --- |
| GET `/api/v1/users?skip=0&limit=100` | Lister les comptes non supprimés | 200, 401, 403 |
| GET `/api/v1/users/{uuid}` | Consulter un compte et sa révision | 200 + ETag, 404 |
| POST `/api/v1/users` | Créer un compte local, attribuer un ou plusieurs rôles | 201 + ETag, 409 doublon |
| PATCH `/api/v1/users/{uuid}` | Renommer, modifier les rôles, activer/désactiver | 200 + nouvel ETag, 412 révision, 409 protection |
| POST `/api/v1/users/{uuid}/password` | Réinitialiser le mot de passe | 204, 412 révision |
| DELETE `/api/v1/users/{uuid}` | Suppression logique avec confirmation UI | 204, 412 révision, 409 protection |

Le contrat suit la concurrence optimiste existante du KMS : requête
`If-Match: "N"` pour PATCH, rotation de mot de passe et DELETE.
Les comptes historiques sans `revision` sont lus en révision 1,
puis migrent lors de leur première modification.

Les mots de passe ne sont jamais renvoyés ni journalisés. Le serveur
utilise le hachage scrypt existant. Toute modification d'un compte
incrémente sa révision et invalide ses anciennes sessions, y compris
les cookies encore détenus par un navigateur. La suppression logique
révoque les sessions et efface le hachage du compte supprimé, mais
conserve l'UUID pour les liens et audits métiers.

Un administrateur ne peut pas se retirer son rôle ADMIN, désactiver
son propre compte ou le supprimer. Le KMS refuse également la
suppression/désactivation du dernier ADMIN actif. Le nom de connexion
supprimé reste réservé pour ne pas créer une confusion d'identité.

## Recette

1. Connecté en ADMIN, créer un compte READER et vérifier qu'il
   ne peut pas ouvrir la gestion des utilisateurs.
2. Lire le compte via GET, modifier le rôle en EDITOR et constater
   l'expiration de la session READER précédente.
3. Vérifier que le nouveau rôle peut créer une connaissance, mais
   qu'il ne possède pas `users.manage` ou `knowledge.delete`.
4. Renommer le compte et vérifier l'unicité de l'identifiant insensible
   à la casse (409), ainsi que la protection de révision (412).
5. Désactiver le compte et constater le refus de connexion ;
   le réactiver et confirmer la possibilité de se reconnecter.
6. Réinitialiser le mot de passe : le précédent échoue (401),
   le nouveau fonctionne et les anciennes sessions ne sont plus valides.
7. Vérifier le refus de désactiver/supprimer l'administrateur
   courant, même lorsque d'autres comptes existent.
8. Supprimer logiquement un autre compte : il n'est plus listé ;
   les connaissances créées sous son UUID restent référencées.
9. Redémarrer MongoDB et l'ensemble de Compose **sans supprimer les
   volumes**, confirmer que les comptes et leurs rôles sont conservés.
10. Effectuer la sauvegarde et le `restore-check` hors production.

La CI ajoute des tests d'intégration avec MongoDB jetable pour
les permissions, l'unicité, la révision, les sessions, les mots de passe,
la compatibilité des utilisateurs historiques, et des tests Angular/Gateway.

La gestion OIDC et le reset libre-service ne font pas partie de ce lot ;
ils nécessitent un protocole d'identité distinct. La suppression est
**logique**, et non un effacement définitif de données personnelles ;
une politique de rétention/RGPD spécifique reste à définir.
