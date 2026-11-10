# Itération : API RNCP protégée et PostgreSQL optionnel — 10 novembre 2026

## État de livraison

**Branche** : `feature/postgres-rncp-foundation` — [PR #19](https://github.com/tomtoomuch/DevKnowledge/pull/19), non fusionnée, en brouillon.

Cette itération étend la fondation PostgreSQL (10 tables métier RNCP du MLD v0.2) avec des routes API spécifiques, à **activation explicite**, utilisant le contrat de session/permissions du KMS et la liste blanche du Gateway. Le KMS standard et le Compose standard **ne changent pas de source de vérité métier**.

### Routes autorisées

| Méthode | Route interne relayée par Gateway | Permission |
|---|---|---|
| GET | `/api/v1/rncp/frameworks/{code}/versions/{version}` | `knowledge.read` |
| GET | `/api/v1/rncp/competencies/{uuid}/evidence` | `knowledge.read` |
| POST | `/api/v1/rncp/competencies/{uuid}/evidence` | `knowledge.create` |
| POST | `/api/v1/rncp/competencies/{uuid}/knowledge-links` | `knowledge.create` |

Ces permissions sont **provisoires** (réutilisation du RBAC existant). Les permissions propres au domaine certification et le cycle complet d'introspection Gateway/Superviseur sont des lots distincts, à valider avant bascule définitive.

### Garde-fous techniques

- `RNCP_API_ENABLED` est **désactivé par défaut** : pas d'import du driver PostgreSQL ni d'enregistrement du routeur dans le KMS normal.
- Un KMS explicitement activé refuse de démarrer si `AUTH_MODE=disabled` ou `KMS_NETWORK_GUARD` n'est pas `required`.
- Le Gateway n'accepte que les quatre formes de routes RNCP déclarées ; aucune base de données n'est accessible directement du navigateur.
- La création d'une preuve insère dans une transaction PostgreSQL la preuve et son association à une compétence, avec l'auteur identifié.
- La création d'un lien connaissance/compétence exige une référence **active** de `knowledge_items` MongoDB ; le doublon est refusé (409), l'absence de connaissance active (422), la compétence manquante (404), un manque d'autorisation (403).
- L'API en mode jeton interne dépend du contrat de l'ADR-004, non d'un nouveau mécanisme inventé.
- **Risque de cohérence à traiter :** une suppression MongoDB entre la vérification et l'insertion SQL est possible. Pas de transaction ACID couvrant deux moteurs ; prévoir outbox, réconciliation et logique de retrait du lien avant mise en service.

### Docker

L'overlay `compose.rncp.yaml` n'est **pas** activé par défaut. Il définit :

- `postgres-rncp` sur le réseau Docker `internal: true`, port 5432 **non publié** et volume `postgres-rncp` indépendant ;
- `rncp-migrate`, job unique exécutant les scripts 001/002 depuis l'image KMS prévisualisation ;
- un KMS de prévisualisation `api-kms-rncp-preview:local` avec psycopg et activation du routeur.

L'overlay exige de nouveaux identifiants PostgreSQL distincts. **Ne pas lancer sur le projet Compose `dev`**. Même dans une pile jetable, il faut vérifier les données et sauvegardes avant d'activer cette écriture.

### Tests et preuves

[CI RNCP dédiée](https://github.com/tomtoomuch/DevKnowledge/actions/runs/42812756292) : **11 tests réussis** avec PostgreSQL 17 réel et FastAPI TestClient. Les références MongoDB sont simulées uniquement pour le test de validité des UUID actifs. La restauration `pg_dump`/`pg_restore` d'une base distincte est vérifiée avec les comptes source/restauré, y compris les écritures supplémentaires.

Les tests Gateway/Jest vérifient que les requêtes RNCP sans session ou sans droit d'écriture sont refusées avant proxy et que les chemins non autorisés restent fermés. La CI générale valide les services existants indépendamment.

**Restent à tester sur une pile isolée avant toute activation réelle** : connectivité simultanée KMS/MongoDB/PostgreSQL, secrets d'exploitation, migrations sur un volume redémarré, émission d'un jeton Superviseur puis validation KMS, interruptions entre Mongo et SQL, révocation des droits, sauvegarde cohérente multi-stores et parcours Angular. Aucun domaine MongoDB existant n'a été migré.

[ADR-005](../decisions/ADR-005-strategie-stockage.md) — PostgreSQL définitif pour le relationnel métier, MongoDB conservé pour les métadonnées et futurs traitements LLM, SQLite pour les métriques.
