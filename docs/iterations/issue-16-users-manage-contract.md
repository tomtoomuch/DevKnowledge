---
title: "Issue 16 — autorisation users.manage dans le Superviseur"
date: "2026-11-10"
status: "Contrat prêt, routage non activé"
tags: [devknowledge, security, supervisor, rbac]
---

# Autoriser les opérations administratives sans token KMS

Après le lot de lecture MongoDB (#18), le Superviseur peut répondre à
`POST /internal/v1/sessions/authorize` pour une session ayant la permission
`users.manage`.

La réponse contient `principal` avec les rôles et permissions, mais **aucun
`kms_token`** : la gestion des utilisateurs est une responsabilité cible du
Superviseur, et le KMS ne doit jamais recevoir de permission d'administration
de comptes dans un token d'audience `api-kms`.

Une session sans `users.manage` reçoit 403. Les permissions `knowledge.*`
continuent à émettre un JWT limité à leur portée.

Cette modification est compatible avec le client
`backend/api-gateway/src/supervisor-client.js`, qui n'exige un token KMS
que pour les permissions `knowledge.*`.

Le routage Gateway → Superviseur des endpoints `/api/v1/users`, la création
et la révocation des sessions et les opérations de compte restent à
implémenter. Le mode de production reste `SUPERVISOR_IDENTITY_MODE=disabled`
et KMS ne passe pas en `KMS_SERVICE_TOKEN_MODE=required`.

Tests : permissions autorisées/refusées, absence de token KMS pour
`users.manage` dans Superviseur et Gateway.
