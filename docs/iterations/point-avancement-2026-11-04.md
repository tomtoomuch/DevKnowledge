---
title: "DevKnowledge — Point d'avancement au 4 novembre 2026"
date: "2026-11-04"
status: "Revue documentaire et statique — stabilisation à engager"
tags: [devknowledge, avancement, audit, stabilisation]
---

# Point d'avancement — 4 novembre 2026

## 1. Référence et périmètre

- **Dépôt :** [tomtoomuch/DevKnowledge](https://github.com/tomtoomuch/DevKnowledge)
- **Branche examinée :** `chat`
- **Commit de référence avant mise à jour de la documentation :** `5afcdb71c6266b8a4435c892d9d4f38eb1df49a4` (2 novembre 2026)
- **Branches au début de la revue :** `chat` et `dev` identiques ; `chat` à 4 commits de `main`.
- **Méthode :** inspection du dépôt GitHub, du code, du Compose et des rapports d'itération. **Les suites de tests n'ont pas été réexécutées dans cette revue.**
- **Objectif :** figer un état connu avant d'entreprendre ensemble une itération de stabilisation. Aucune correction applicative n'est incluse dans cette mise à jour documentaire.

## 2. Synthèse exécutive

**Le CRUD générique des connaissances est livré et documenté ; le socle n'est pas encore considéré comme stabilisé.**

L'application actuelle comprend une API Gateway Express, un Knowledge Service FastAPI et MongoDB 8 via Docker Compose. Le CRUD KMS expose cinq opérations HTTP sous `/api/v1/knowledges` ; la Gateway ne route pas encore ces opérations. MongoDB conserve les connaissances dans `knowledge_items`, avec suppression logique et index chronologique.

Le MLD de référence [[DevKnowledge_MLD_3NF_v0.2]] est un **modèle logique candidat à la 3NF**, constitué de **56 tables prévues** ; ce chiffre ne représente ni 56 collections existantes ni 56 CRUD réalisés. Le référentiel de types, les huit spécialisations, les identités/RBAC, la certification RNCP, les preuves et le RAG ne sont pas encore implémentés.

## 3. État des composants au commit examiné

| Périmètre | État vérifié dans le dépôt | Réserve |
| --- | --- | --- |
| Architecture | Socle local-first, Express / FastAPI / MongoDB, décisions ADR | Cible microservices plus large à construire |
| Gateway Express | `/health`, tests Jest, Dockerfile | Pas de proxy `/api/v1/knowledges`, pas d'authentification |
| Knowledge Service FastAPI | Routes de création, liste, lecture, PATCH et DELETE logique | API actuellement accessible directement sur `127.0.0.1:8000` |
| Schémas et règles métier | Pydantic v2, huit codes de type, UUID, dates UTC, validations et pagination | `status` libre borné, cycle de vie métier à définir |
| MongoDB | `knowledge_items`, repository asynchrone, index `active_chronological`, suppression logique | Provisionnement de l'utilisateur applicatif non automatisé dans Compose |
| Docker Compose | Trois services et healthchecks ; MongoDB non publié sur l'hôte | Écarts de configuration détaillés ci-dessous |
| Tests KMS | Unitaires, intégration MongoDB isolé, HTTP Uvicorn sous Compose de test | Résultats historiques, pas de nouvelle exécution lors de cette revue |
| CI/CD | Aucune définition `.github/workflows` dans l'arborescence `chat` | Aucun workflow Actions observé pour cette branche |
| Frontend Angular | Non présent dans le dépôt examiné | Hors périmètre du socle livré |
| Identité / RBAC | Modèle `users`, `roles`, `permissions`, `user_roles`, `role_permissions` dans le MLD | Pas de service ni d'application de droits |
| RAG / Ollama / ChromaDB / MCP | Cible documentée | Non implémentés |
| RNCP 37827 et preuves | Référentiel et relations prévus au MLD | Pas d'import ni de suivi métier opérationnel |

### Contrat CRUD présent

| Opération | Route KMS | Résultat attendu |
| --- | --- | --- |
| Créer | `POST /api/v1/knowledges` | 201 |
| Lister | `GET /api/v1/knowledges` | 200, pagination et filtres |
| Consulter | `GET /api/v1/knowledges/{knowledge_id}` | 200 / 404 |
| Modifier | `PATCH /api/v1/knowledges/{knowledge_id}` | 200 / 404 |
| Supprimer logiquement | `DELETE /api/v1/knowledges/{knowledge_id}` | 204 / 404 |

La suppression conserve le document en base avec `deleted_at` renseigné. Les routes non authentifiées constituent une **limite assumée de l'itération**, non un état de sécurité prêt pour une exposition réseau.

## 4. Tests : distinguer historique et résultats actuels

Résultats **rapportés lors de la livraison du 2 novembre 2026** dans [[iteration-1-kms-crud]] :

| Campagne historique | Résultat consigné | Couverture consignée |
| --- | --- | --- |
| KMS unitaire sur Windows | 113 tests réussis, 4 intégrations désélectionnées | 99,62 % (259/260 instructions) |
| KMS complète sur Docker | 117 tests réussis, dont 4 intégrations | 100 % (260/260 instructions) |
| Gateway Jest | 2 tests réussis | 100 % de `app.js` |
| `pip check` | OK | Sans objet |
| `docker compose config --quiet` | OK | Sans objet |
| Environnement de développement | 3 services `healthy` au moment du rapport | Sans objet |

**Au 4 novembre : aucune de ces commandes n'a été relancée dans le cadre de ce point d'avancement.** Ces taux mesurent le périmètre exécuté à cette date, non la couverture de l'ensemble de l'architecture cible. Les dépendances Python et images ne sont pas complètement verrouillées : un rebuild futur peut résoudre d'autres versions.

## 5. Points de stabilisation confirmés par inspection statique

| ID | Priorité proposée | Constat | Emplacement | Action à évaluer ensemble |
| --- | --- | --- | --- | --- |
| STAB-01 | P1 | `.env.example` utilise `MONGODB_APP_USER` ; `compose.yaml` lit `MONGODB_APP_USERNAME` | `.env.example`, `compose.yaml` | Unifier l'interface de configuration et tester une installation neuve |
| STAB-02 | P1 | Compose initialise le compte root MongoDB, mais aucun mécanisme de création du compte applicatif n'est versionné | `compose.yaml`, absence de script d'initialisation | Provisionner un compte limité et vérifier l'authentification sur volume jetable |
| STAB-03 | P2 | Compose passe `HOST` et `PORT` à la Gateway, le serveur lit `GATEWAY_HOST` et `GATEWAY_PORT` | `compose.yaml`, `backend/api-gateway/src/server.js` | Aligner les noms et tester une valeur personnalisée |
| STAB-04 | P2 | Le healthcheck de production du KMS appelle `/health` et non `/health/ready` | `compose.yaml` | Vérifier readiness MongoDB et liveness séparément |
| STAB-05 | P2 | Pas de workflow GitHub Actions versionné | `.github/workflows` absent | Ajouter lint/validation/tests et une politique de merge |
| STAB-06 | P2 | La Gateway ne transmet pas le CRUD ; KMS reste accessible localement sur le port 8000 | `backend/api-gateway/src/app.js`, `compose.yaml` | Définir et tester la frontière d'entrée unique, sans ouvrir les ports |
| STAB-07 | P3 | Dépendances Python en plages, outils de tests dans `requirements.txt` de production | `backend/knowledge-service/requirements.txt`, Dockerfile | Reproductibilité, séparation prod/test et procédure offline |
| STAB-08 | P3 | Absence de contrôle de concurrence optimiste et de sauvegarde/restauration éprouvée | Service CRUD, ADR stockage | Définir stratégie et tests avant données importantes |

**Priorités proposées, non tickets validés.** P1 : peut empêcher une installation neuve reproductible ; P2 : fiabilité/architecture/automatisation ; P3 : dette technique à cadrer. Les constats d'absence ne prouvent pas une panne sur un volume local déjà préparé.

## 6. Écarts connus vis-à-vis du MLD

- `knowledge_items.knowledge_type_id` du MLD : implémenté provisoirement comme code `knowledge_type` d'une enum Pydantic, sans collection `knowledge_types`.
- `created_by_user_id` obligatoire dans le MLD : nullable dans le CRUD actuel tant qu'aucune identité authentifiée n'est disponible.
- `deleted_at` ajouté au schéma physique pour la suppression logique, absent du MLD v0.2.
- Les huit spécialisations, l'historique `knowledge_versions`, les liens RNCP et les preuves restent à développer.

Ces différences sont documentées par l'itération 1 et **ne doivent pas être corrigées par une migration implicite pendant la stabilisation**.

## 7. Prochain jalon et conditions de sortie

Le travail proposé est décrit dans [[iteration-2-stabilisation]]. Le jalon sera considéré comme achevé lorsque :

1. Une **installation neuve sur volumes jetables** fonctionne avec une configuration documentée, sans dépendre de données déjà initialisées.
2. `npm test`, les tests KMS unitaires et la suite Docker isolée sont **réexécutés avec résultats et environnement consignés**.
3. Liveness/readiness, arrêt/redémarrage et indisponibilité temporaire de MongoDB sont vérifiés.
4. Une CI GitHub versionnée exécute au minimum les tests adaptés à chaque changement ; ses statuts sont consultables.
5. Les écarts de configuration P1/P2 sont corrigés ou explicitement arbitrés ; aucune donnée locale n'a été supprimée.
6. Les limites de sécurité et le périmètre reporté restent clairement documentés avant l'étape utilisateurs/RBAC.

## 8. Règles de travail

- **Branche de travail :** `chat`. Aucun changement volontaire dans `dev` ou `main`.
- **À ce jalon :** point d'avancement, roadmap et plan d'itération ; aucune modification du code applicatif.
- **Protection des données :** ne jamais exécuter `docker compose down --volumes` contre les volumes de développement. Réserver le nettoyage destructeur à l'environnement de test identifié.
- **Traçabilité :** distinguer systématiquement observations du dépôt, résultats de test historiques, tests effectivement relancés, décisions à prendre.
- **Échange :** traiter les points de stabilisation progressivement avec revue des modifications et vérification de régression.

## 9. Documents associés

- [[iteration-1-kms-crud]] : rapport de livraison et métriques du 2 novembre.
- [[iteration-2-stabilisation]] : plan de stabilisation, tâches et critères d'acceptation.
- [[../architecture/kms-knowledge-crud]] : contrat HTTP, représentation MongoDB et guide de tests.
- [[../DevKnowledge_MLD_3NF_v0.2]] : modèle logique et arbitrages métier.
- [[../roadmap]] : trajectoire de développement mise à jour.
