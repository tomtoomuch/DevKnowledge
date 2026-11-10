---
title: "Issue 16 — Contrat sécurisé Gateway vers Superviseur (étape préparatoire)"
date: "2026-11-10"
status: "Implémentation partielle — non activée en production"
tags: [devknowledge, security, supervisor, gateway, migration]
---

# Contrat d'autorisation Gateway → Superviseur

La migration complète de l'autorité d'identité décrite dans
[[decisions/ADR-004-superviseur-identite-securite]] n'est **pas achevée**.

Cette étape ajoute `backend/api-gateway/src/supervisor-client.js`,
`backend/collector/src/supervisor-authorization.js` et leurs tests.
Le serveur Collector accepte un gestionnaire d'identité injecté explicitement
via son quatrième argument `authorizationHandler`. **La configuration
Compose actuelle ne l'injecte pas : la route reste donc absente par défaut.**
Cela formalise un échange interne authentifié, sans modifier le flux actif :

```text
Gateway → POST /internal/v1/sessions/authorize (Superviseur)
  en-têtes :
    X-Service-Key: <secret interne, 32 octets hexadécimaux>
    X-Request-ID: <nonce unique>
  corps JSON :
    session_cookie: "dk_session=<64 caractères hexadécimaux>"
    permission: "knowledge.read" | "knowledge.create" |
                "knowledge.update" | "knowledge.delete" | "users.manage"

200 :
  principal: { user_id, username, roles, permissions }
  kms_token: "<JWT HS256 audience api-kms>" (requis pour knowledge.*)
401/403 : refus d'authentification / autorisation
tout autre code ou réponse invalide : indisponibilité (fail closed)
```

Le Gateway ne fait pas confiance aux en-têtes d'identité envoyés par le navigateur.
Le Superviseur **devra** :
1. authentifier la demande interne avec une comparaison constante du secret ;
2. vérifier la session opaque par empreinte SHA-256 en MongoDB ;
3. vérifier compte actif, révision de l'identité, RBAC et portée demandée ;
4. produire un token KMS signé, de durée maximale 60 secondes, uniquement
   après validation de cette autorisation ;
5. ne jamais journaliser les mots de passe, cookies ou secrets.

Le KMS doit vérifier lui-même signature, audience, expiration et permission.
Le client Gateway ne considère pas la syntaxe d'un JWT comme preuve cryptographique.

## État du déploiement

**Le client n'est pas encore appelé par `app.js` ; l'endpoint interne
existe sous forme de gestionnaire testé mais n'est pas monté au démarrage
normal. Aucun secret, route publique ni modification de `compose.yaml`
n'est introduit à cette étape.**
Le routage historique continue donc d'être utilisé. Il serait incorrect
d'activer `KMS_SERVICE_TOKEN_MODE=required` maintenant.

## Suite indispensable avant basculement

- Portage du CRUD comptes/sessions/RBAC vers le Superviseur et MongoDB.
- Implémentation et tests du point d'entrée `/internal/v1/sessions/authorize`.
- Injection du token interne côté proxy Gateway → KMS et bascule
  des routes d'identité vers le Superviseur.
- Retrait de la session navigateur côté KMS et activation du mode obligatoire.
- Tests d'intégration Node/Python, données historiques, révocation, Docker offline,
  métriques SQLite, sauvegarde et restauration.

Ne jamais supprimer les volumes historiques et ne pas fusionner la migration
complète sans avoir validé ce dernier ensemble de tests.
