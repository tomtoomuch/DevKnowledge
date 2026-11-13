---
title: "ADR-004 — Superviseur : autorité d’identité, RBAC et confiance interservices"
date: "2026-11-10"
status: "Proposé — migration sur feature/supervisor-identity"
tags: [architecture, adr, identite, sécurité, rbacs, superviseur]
---

# ADR-004 — Autorité de sécurité centralisée dans le Superviseur

## Contexte et invariants

Le microservice `supervisor` ne gérait jusqu'ici que des sondes de santé
et des métriques GPU. L'identité locale, les rôles, sessions et
permissions étaient gérés par `api-kms`, qui conserve aussi les connaissances.

L'architecture cible impose les invariants suivants :

1. **Toutes** les requêtes provenant de l'extérieur — y compris les
   pages Angular — passent **obligatoirement d'abord** par le **Gateway Express**.
2. Le **Superviseur** devient propriétaire des identités, comptes,
   rôles, permissions, sessions et habilitations entre microservices.
3. Le Gateway consulte le Superviseur **pour chaque requête protégée**
   afin de vérifier la session et les droits d'accès ; aucune identité
   envoyée directement par le navigateur n'est reconnue comme fiable.
4. Le Superviseur émet des **tokens internes de courte durée** avec
   émetteur, audience, identité et portée ; un service métier ne reçoit
   qu'un token destiné à sa propre audience et contrôle la signature
   et les permissions nécessaires à chaque opération.
5. Le KMS ne crée ni ne modifie de comptes en production et n'accepte
   plus les cookies de navigateur comme autorité d'identification.
6. Aucun port du Superviseur, du KMS, de MongoDB ou du frontend n'est
   exposé sur l'hôte. Le seul port publié appartient au Gateway.
7. Le volume `mongodb:/data/db` reste inchangé. Les utilisateurs et
   sessions historiques doivent rester lisibles pendant la migration.

## Flux retenus

```text
Navigateur
  └── Gateway Express (seul point d'entrée externe)
        ├── GET/HEAD pages/assets -> Nginx/Angular privé, sur dmz
        ├── POST /api/v1/auth/login -> Superviseur, sur internal
        ├── POST /api/v1/auth/logout -> Superviseur, sur internal
        ├── GET  /api/v1/auth/me -> introspection Superviseur
        ├── /api/v1/users/* -> Superviseur, contrôle RBAC users.manage
        └── /api/v1/knowledges/* -> KMS avec token interne d'audience api-kms

Superviseur -> MongoDB : collections identité, rôles, sessions et audit
KMS        -> MongoDB : connaissances et index métiers
KMS        -> Superviseur : monitoring snapshot interne (dans ce lot)
```

L'identification est distincte de l'autorisation RBAC : un utilisateur
authentifié n'a aucun droit implicite. Le Gateway bloque en premier,
le Superviseur vérifie les permissions au moment de l'introspection,
et le KMS impose **à nouveau** la portée du token reçu.

## Protocole de confiance et compromis

L'itération de transition utilise un secret de service
`SUPERVISOR_GATEWAY_KEY` pour authentifier les demandes
interne Gateway -> Superviseur et un token HMAC-SHA256 d'audience
`api-kms` pour les requêtes Gateway -> KMS, avec secret distinct
`SUPERVISOR_KMS_TOKEN_KEY`, durée au plus 60 s,
`iss`, `aud`, `sub`, `scope`, `iat`, `exp` et `jti`.
La validation stricte de ces claims et une comparaison de signature
à temps constant sont obligatoires.

**Précision cryptographique (décision 2026-11-10) : un hash n'est pas
un chiffrement.** Les sessions restent des tokens opaques aléatoires
de 32 octets ; **seule leur empreinte SHA-256** est stockée
dans `sessions._id`. Un JWT de service est **signé** par
HMAC-SHA-256, sans confidentialité : ses claims peuvent être lus
par son destinataire et ne doivent contenir ni mot de passe, ni
cookie, ni secret personnel. Si le chiffrement d'un véritable
secret devient nécessaire, le traiter séparément avec
**AES-256-GCM**, une gestion de clés et une politique de rotation.

La phase de transition ajoute :
- `backend/supervisor/src/service-tokens.js` : fonction
  d'émission **non exposée en HTTP** et nécessitant un
  `Principal` déjà vérifié par le Superviseur ; un token
  donne exactement **une** permission métier `knowledge.*`;
- `app/auth/service_tokens.py` dans le KMS : vérification de
  l'algorithme HS256, du secret, de la signature, de `iss`,
  `aud=api-kms`, `sub` UUID, `scope`, `iat`, `exp`
  (durée maximale de 60 secondes) et `jti` ;
- `KMS_SERVICE_TOKEN_MODE=required` : **mode préparé, non
  activé** dans Compose avant le basculement des sessions
  et du routage depuis le Gateway. Dans ce mode, les cookies
  navigateur et les en-têtes non signés ne constituent plus
  une preuve d'identité.

Un secret HMAC de **32 octets aléatoires encodés en 64 caractères
hexadécimaux** est attendu pour
`SUPERVISOR_KMS_TOKEN_KEY`, par exemple généré localement avec
`python -c "import secrets; print(secrets.token_hex(32))"`.
**Ne jamais versionner sa valeur ni la journaliser.** La
distribution sécurisée de cette clé et sa rotation restent une
étape de déploiement avant l'activation du mode obligatoire.
Les tests utilisent une clé fixe **uniquement pour la recette**.

L'implémentation présente des primitives de signature et de vérification,
**pas encore un circuit d'authentification complet**. Le Superviseur
doit d'abord reprendre le stockage des sessions, vérifier le RBAC,
authentifier le Gateway comme service, puis émettre les tokens après
introspection. Le KMS ne doit pas passer en mode obligatoire avant cette
migration complète.

**Limite explicitement acceptée pour la phase locale de transition :**
le vérificateur KMS possède la même clé HMAC que l'émetteur Superviseur,
donc un KMS compromis pourrait signer des tokens. Une phase dédiée
doit remplacer le HMAC par Ed25519/ES256 asymétrique avec publication
des seules clés publiques aux services et rotation `kid` sans interruption.
L'authentification forte service-à-service (mTLS ou JWT d'identité de
service avec audience) est également prévue à l'issue de cette phase.
Ne pas qualifier le secret partagé de mTLS ou d'identité cryptographique
asymétrique.

Le cookie opaque `dk_session` ne transite **jamais jusqu'au KMS**.
Les tokens internes ne sont jamais retournés au navigateur, inscrits
dans les logs ou transmis à Nginx. Une indisponibilité du Superviseur
rend l'accès protégé indisponible (**fail closed**, 503).

## Données, compatibilité et sauvegarde

Les identifiants `users._id` restent identiques, les hachages scrypt
historiques sont conservés, le cookie reste `dk_session`, et les
liens métiers `created_by_user_id` ne changent pas. Les index et
collections de la gestion d'identités restent dans le volume MongoDB
persistant existant ; le stockage des secrets n'est pas mélangé à
la collection de comptes.

Conserver la suppression logique, la révocation des sessions au
changement de révision, le verrou contre la désactivation du dernier
ADMIN actif et le contrôle `If-Match` sur les écritures administratives.

Ne pas recréer d'admin automatiquement sur une base non identifiée
et ne pas supprimer les volumes. Tester sauvegarde, rétablissement,
redémarrage Compose, session existante, rôles historiques et KMS
en mode jeton obligatoire avant fusion.

## Découpage de migration

1. **Service Superviseur** : renommer Supervisor, préserver le monitoring,
   transférer le dépôt de comptes et de sessions, intégrer le contrôle RBAC.
2. **Gateway** : faire de Superviseur la source des sessions, et relayer
   les opérations de compte exclusivement à ce service.
3. **KMS** : authentifier les tokens internes et retirer les routes d'identité
   dans le Compose normal ; préserver le modèle métier.
4. **Tests et recette** : scénarios auth, changement de rôles, révision,
   révocation, faux tokens, erreurs de signature/audience, contrôle
   d'accès au niveau métier, persistance, panne du Superviseur.
5. **Durcissement post-migration** : authentification service-to-service
   asymétrique et rotation, secrets par service et droits MongoDB
   limités aux seules collections de sa responsabilité.

## Journalisation centralisée — capacité cible du Superviseur

Le Superviseur assurera la **collecte centralisée par microservice**,
l'indexation, la consultation et la rétention des événements, sans
créer de second point d'entrée public.

Deux catégories distinctes sont obligatoires :

- **Observabilité** : erreurs d'exécution, durée des requêtes,
  disponibilité, redémarrages et corrélation entre services.
  Le stockage peut être asynchrone, avec file tampon bornée et
  politique d'abandon explicite en cas de saturation.
- **Audit de sécurité** : connexions, échecs, refus RBAC, changements
  de comptes et de rôles, révocations et opérations administratives.
  L'intégrité, la non-altération, la conservation et le comportement
  en cas d'échec du stockage doivent être déterminés séparément.

Chaque événement aura au minimum : `timestamp_utc`,
`service_id`, `severity`, `event_code`, `trace_id`,
`schema_version` et des attributs structurés **autorisés**.
Les journaux ne contiendront jamais mots de passe, cookies, tokens
ou en-têtes de sécurité en clair ; les identifiants utilisateurs ne
devront être conservés que si justifiés par l'audit et la politique
de rétention.

```text
Gateway / KMS / services IA -> ingestion interne authentifiée Superviseur
                                 (identité + audience + logs.write)
                                  |
                                  +-- stockage/rétention centralisés
                                  |
Navigateur Angular -> Gateway -> API Superviseur de consultation RBAC
                                  (logs.read / security_audit.read)
```

**Les métriques de santé et GPU utilisent un autre magasin : SQLite3**,
introduit dans le lot `feature/supervisor-metrics-sqlite` (PR #14).
L'interface d'ingestion et la persistance des journaux sont
**planifiées, non encore implémentées** : le stockage des métriques
ne doit pas être présenté comme une couverture complète des audits.

Consulter [[decisions/ADR-005-strategie-stockage]] et
[[operations/metrics-sqlite]] pour la séparation des domaines de données.

## Sécurité et risques documentés

- Un **token interne** autorise un appel mais ne rend pas les
  transactions MongoDB atomiques ; les exigences d'atomicité restent
  dans les services et la base.
- Un réseau Docker `internal: true` limite l'exposition mais ne
  constitue pas une identité de service ; les secrets ou certificats
  assurent cette authentification.
- Les données d'identité et les sessions sont sensibles : archives
  hors production protégées et rotation des secrets documentée.
- Les implémentations historiques ne doivent pas être conservées
  comme **routes de repli actives** en production après migration :
  sinon l'autorité du Superviseur serait contournable.
