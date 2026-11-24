# Migration de l'identité vers le Superviseur

État au 24 novembre 2026 : implémentation complète du circuit de l'issue GitHub #16, qualifiée localement et proposée à la revue dans DOC-41. La pile locale a été basculée le 24 novembre après sauvegarde et restauration vérifiée ; les recettes automatisées utilisent exclusivement des volumes jetables. Voir le rapport lié en fin de page pour distinguer qualification et activation.

## Circuit et responsabilités

- Le navigateur appelle uniquement Express Gateway, y compris pour les pages Angular.
- Login, logout, `/api/v1/auth/me` et le CRUD `/api/v1/users` passent de Gateway vers le Superviseur. Les URL et réponses Angular sont conservées.
- La Gateway transmet le cookie opaque uniquement au Superviseur, avec `SUPERVISOR_GATEWAY_KEY`, jamais à Nginx ni au KMS. Elle transforme la réponse de login en cookie `HttpOnly; SameSite=Strict; Path=/api/v1`, avec `Secure` si `AUTH_COOKIE_SECURE=true`. Aucun jeton de session n'est rendu dans le corps JSON.
- Pour chaque requête métier, le Superviseur relit la session, la révision du compte et ses droits. Il délivre un JWT HS256 limité à une permission, à l'audience `api-kms` et à 60 secondes maximum. La Gateway remplace tout en-tête Authorization navigateur par ce jeton ; le KMS vérifie signature, audience, durée et portée.
- Le KMS n'enregistre plus les routes de comptes/sessions ni leurs index lorsque `KMS_SERVICE_TOKEN_MODE=required`. Son bootstrap administrateur refuse ce mode.
- MongoDB accorde au compte KMS uniquement les sept collections métier et au compte Superviseur uniquement les huit collections d'identité. Les comptes doivent être distincts du compte historique `readWrite` et du compte root.
- Les contrôles IP/DNS internes restent une protection supplémentaire. Une panne du Superviseur donne 503, sans retour automatique au KMS historique.

Le Compose normal impose `GATEWAY_IDENTITY_AUTHORITY=supervisor`, `SUPERVISOR_IDENTITY_MODE=active` et `KMS_SERVICE_TOKEN_MODE=required`. Le mode historique reste disponible dans le code pour les tests et un retour arrière explicitement préparé. Le mode `shadow` est toujours une bibliothèque de transition en lecture seule, pas le mode normal du Compose.

## Compatibilité des données et administration

Les UUID des comptes et rôles, hachages scrypt, empreintes SHA-256 des sessions, dates d'expiration, révisions et anciennes associations RBAC sont conservés. Les comptes sans champ `revision` restent à la révision effective 1. Aucune réécriture de masse n'est requise.

Les mutations de comptes imposent `If-Match`, révoquent les sessions et préservent la suppression logique. Les modifications administratives sont sérialisées dans `identity_admin_mutex` ; la dernière identité ADMIN active et l'administrateur courant sont protégés. Les rôles modernes restent projetés atomiquement dans `users.role_codes`, avec synchronisation du graphe historique `user_roles`.

Le verrou ne peut pas être repris automatiquement après expiration : cela empêcherait de garantir l'unicité d'un écrivain suspendu. Après un arrêt brutal pendant une mutation, les écritures administratives peuvent répondre 409. Pour récupérer : arrêter **tous** les processus Gateway, Superviseur et KMS historiques susceptibles d'écrire ; sauvegarder ; vérifier le compte visé, ses rôles et révisions ; retirer uniquement `owner`, `acquired_at` et `expires_at` du document `_id: "admin"` dans `identity_admin_mutex` avec une session MongoDB administrative ; redémarrer le Superviseur. Ne jamais libérer ce verrou avec un écrivain encore actif.

## Installation neuve

1. Préparer `.env` à partir de `.env.example`, avec des mots de passe distincts d'au moins 20 caractères pour les deux nouveaux comptes et deux secrets de service distincts de 64 caractères hexadécimaux. Ne pas écraser un fichier existant.
2. Sur un volume vierge, l'initialisation MongoDB crée les rôles restreints. `docker compose up -d --build` lance le circuit normal.
3. Créer le premier administrateur : `python scripts/bootstrap_supervisor.py --username admin`. Le mot de passe est demandé sans écho et transmis par stdin. Un second bootstrap est refusé dès qu'un compte existe.
4. Se connecter via l'URL Gateway locale. Aucun bootstrap ni inscription publique HTTP n'est exposé.

## Bascule d'une installation existante

Cette opération est distincte de la qualification du code. Elle conserve exactement le nom du projet Compose et les volumes de données existants. Ne pas lancer `down --volumes` sur cette installation.

1. Conserver la révision et la configuration précédentes pour le retour arrière. Planifier une interruption des écritures. Préparer les nouvelles variables dans la configuration locale ; utiliser de nouveaux noms de comptes, notamment si un lecteur shadow existe déjà.
2. Construire les images candidates avant l'interruption. En fonctionnement déconnecté, toutes les images doivent déjà être présentes.
3. Sauvegarder avec `scripts/mongodb_backup.py backup <nouveau-dossier> --project <projet-existant> --env-file <configuration>`. Le script arrête et redémarre uniquement les écrivains initialement actifs, y compris désormais le Superviseur. Interdire les écrivains externes pendant cette opération.
4. Exécuter `python scripts/provision_identity_owners.py --project <projet-existant> --env-file <configuration> --backup <dossier>`. Ce programme arrête les écrivains, exige que la sauvegarde corresponde encore aux documents source et vérifie sa restauration isolée, puis crée les nouveaux rôles/comptes. Il refuse les rôles existants inattendus, ne change aucun mot de passe existant et laisse les écrivains arrêtés.
5. Démarrer les images qualifiées avec le même projet Compose. Le script de provisionnement n'est pas rejoué automatiquement sur un volume MongoDB existant.
6. Vérifier une session existante, login/logout, lecture et écriture de connaissances, administration, révocation et monitoring. Conserver la sauvegarde et les anciens identifiants pour la fenêtre de retour arrière ; retirer ensuite explicitement le compte applicatif historique trop large lorsque le retour arrière n'est plus nécessaire.

Les comptes MongoDB sont provisionnés dans `MONGODB_DATABASE` : `MONGODB_AUTH_SOURCE` doit désigner cette même base pour cette configuration. La restauration MongoDB rétablit documents/index/options et recrée les comptes de service depuis la configuration locale ; elle vérifie leurs refus d'accès croisé. Elle ne restaure jamais directement dans un volume existant.

## Retour arrière et rotation

Avant une promotion, conserver les anciennes images et la configuration historique Gateway → KMS avec le compte MongoDB historique. En cas de retour arrière, arrêter d'abord les nouveaux écrivains puis lancer uniquement l'ancienne pile. Les comptes et sessions utilisent le même schéma ; ne jamais exploiter simultanément les deux autorités. Une restauration de données, si nécessaire, passe par un nouveau volume vérifié et une procédure distincte.

Pour une rotation coordonnée des secrets de service, arrêter les trois services, remplacer les deux clés par des valeurs distinctes et redémarrer Superviseur, KMS et Gateway avec une configuration cohérente. Il n'y a pas de chevauchement `kid` ni de rotation sans interruption ; les anciens JWT deviennent invalides au changement de clé. Les sessions navigateur sont conservées. La signature asymétrique et la rotation à clés multiples restent un lot de durcissement de l'ADR-004.

## Reproduction de la qualification

```bash
python scripts/check_identity_migration.py
python scripts/check_identity_migration.py --offline
```

Le script crée un projet au nom unique avec cinq services, des volumes neufs, deux réseaux internes et aucun port hôte. Il qualifie les comptes historiques, la suppression des routes KMS d'identité, RBAC, les écritures conditionnelles, la révocation, les droits de bases, l'indisponibilité du Superviseur, le redémarrage, la sauvegarde SQLite, la sauvegarde/restauration MongoDB et le redémarrage de l'application sur le volume restauré. Il nettoie uniquement ses ressources et écrit `test-results/devknowledge-identity-test-*/summary.json`.

`--offline` interdit builds et téléchargements et utilise les images préparées ; il ne constitue pas une construction complète hors ligne ni une déconnexion physique de l'hôte. La recette HTTP inclut le chargement de la page Angular, sans remplacer une revue visuelle manuelle de tous les écrans. La CI est configurée pour exécuter ces deux campagnes et publier leurs rapports ; consulter le résultat de la révision candidate dans la PR et DOC-41.

Résultats et limites : [qualification du 24 novembre 2026](../iterations/identity-migration-2026-11-24.md).
