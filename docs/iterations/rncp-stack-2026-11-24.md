# Qualification PostgreSQL/RNCP — 24 novembre 2026

## Résultat et périmètre

Lot [DOC-42](https://linear.app/documentation-perso/issue/DOC-42), sur la branche `codex/rncp-full-stack-qualification`, dépendant de la [PR #22](https://github.com/tomtoomuch/DevKnowledge/pull/22). La recette utilise le véritable circuit Gateway → Superviseur → JWT KMS → PostgreSQL, avec MongoDB et SQLite réels. Les six services sont isolés, sans port publié ; toutes les données RNCP sont fictives (`RNCP-TEST`).

**Qualification technique du circuit et de la reprise ; activation réelle non autorisée par ces résultats.** Une référence orpheline MongoDB/SQL est reproductible. [DOC-43](https://linear.app/documentation-perso/issue/DOC-43) porte la politique et le mécanisme de cohérence à établir avant activation. Aucune donnée réelle n'est migrée. L'installation locale conserve son Compose standard à cinq services.

## Couverture

- Lecture des deux versions fictives, séparation des preuves entre versions et chemins Gateway limités.
- Sessions du Superviseur, permissions lecteur/éditeur, origine HTTP, refus du cookie navigateur par le KMS et auteur SQL issu de l'identité authentifiée malgré des en-têtes falsifiés.
- Transaction de création d'une preuve et de son association ; refus des titres blancs, types inconnus et compétences manquantes sans écriture partielle.
- Validation d'une connaissance MongoDB active, refus des doublons, références absentes et fiches déjà supprimées.
- Révocation après rétrogradation d'un éditeur ; ancienne session refusée et nouvelle session sans droit d'écriture.
- Arrêts séparés de PostgreSQL, MongoDB et du Superviseur, refus explicite puis reprise ; redémarrage des services et rejeu des migrations.
- Sauvegarde commune après arrêt des trois services écrivains, restauration dans des volumes distincts, puis lecture des mêmes connaissances/preuves avec la session persistante.
- Exécution hors ligne sur réseaux internes avec les images déjà préparées, sans build ni pull. Cela ne qualifie pas un build hors ligne.

## Correctifs issus de la recette

Un titre composé uniquement d'espaces répondait 201. La validation rejette désormais la valeur avec 422 avant l'écriture SQL. La readiness du KMS optionnel vérifie également PostgreSQL : une panne produit 503 sans divulguer les détails de connexion, tandis que la liveness reste indépendante. Le KMS standard n'importe pas le pilote PostgreSQL.

Le lanceur historique du POC lit explicitement les sorties Docker en UTF-8, pour éviter une erreur de décodage Windows CP1252 observée pendant cette campagne.

## Cohérence et sauvegarde

Le scénario `tests/rncp/cross_store_race.py` bloque l'insertion du lien après validation MongoDB par un verrou PostgreSQL. Une suppression HTTP autorisée intervient alors ; le lien SQL est ensuite créé avec succès. L'audit en lecture seule détecte cet orphelin. Le scénario retire uniquement son lien fictif avant la sauvegarde ; ce nettoyage n'est pas une stratégie de réparation métier.

Dans une pile RNCP déjà configurée, l'outil interne `python -m app.rncp.audit` utilise les identifiants du KMS sans les afficher. Il parcourt les références par lots de 500, retourne les compteurs et au maximum 100 identifiants invalides. Codes de sortie : 0 cohérent, 2 références invalides, 1 dépendance indisponible. Arrêter les écrivains avant une certification de cohérence ; une lecture pendant des écritures reste une photographie non atomique entre moteurs. Aucun document métier n'est affiché et aucune donnée n'est réparée automatiquement.

La recette arrête Gateway, KMS et Superviseur avant le checkpoint. Elle compare les nombres et empreintes des lignes des onze tables SQL (dix métier et journal des migrations), les documents/index/options MongoDB via le dispositif existant, et les empreintes des fichiers SQLite copiés à l'arrêt. Après restauration, elle vérifie aussi l'intégrité SQLite et le fonctionnement des API. C'est une preuve sur données fictives, pas une procédure générale de bascule des bases réelles.

## Reproduire et lire les preuves

Depuis la racine, avec Python 3.11+ et Docker Compose prenant en charge les overlays `!reset` :

```text
python poc/rncp-postgres/run.py
python scripts/check_rncp_stack.py
python scripts/check_rncp_stack.py --offline
```

Le lanceur ne lit pas `.env` et n'accepte aucun nom de projet de déploiement. Il utilise `tests/stabilization.env` et crée uniquement des projets `devknowledge-rncp-stack-<aléatoire>`. Le nettoyage avec volumes est limité à ces projets et au volume MongoDB de restauration créé par la recette. Les images de test ont des tags distincts de l'installation locale.

Les rapports sont dans `test-results/devknowledge-rncp-stack-*/summary.json` : `success`, `checks`, `activation_gates`, empreintes du checkpoint et résultats du nettoyage. Les journaux et sauvegardes contiennent uniquement les fixtures de ce lanceur. Le POC publie `test-results/rncp-postgres/result.json`. La CI dédiée publie ces répertoires et exécute successivement le POC, la validation Compose, la pile complète et le rejeu hors ligne.

Campagne locale : 221 tests unitaires KMS réussis (15 tests d'intégration exclus de cette commande), 11 tests du POC PostgreSQL réussis, actionlint et `git diff --check` sans erreur. Les rapports de pile complète `devknowledge-rncp-stack-f6104541409d` et de rejeu hors ligne `devknowledge-rncp-stack-b7da42ba02ab` couvrent chacun 18 groupes de contrôles, avec restauration et nettoyage. Un avertissement de dépréciation Starlette sur les cookies de test demeure sans échec.

## Limites avant mise en service

- Résoudre DOC-43, y compris une suppression de connaissance après création du lien, les interruptions et les rejeux.
- Séparer les rôles PostgreSQL d'administration/migration et d'exécution : l'overlay utilise encore le même compte. Les droits MongoDB limités ne prouvent pas ceux de PostgreSQL.
- Qualifier les secrets, rétentions, chiffrement et procédure opérationnelle de sauvegarde/restauration des bases réelles.
- Contenu officiel RNCP, permissions métier spécifiques et interface Angular : DOC-25. Aucune conformité RNCP n'est déduite des fixtures.
- Images système par tags et dépendance psycopg optionnelle non verrouillée par empreinte ; build entièrement hors ligne non qualifié.
- La revue/fusion des PR reste distincte de la qualification. Toute promotion vers `dev` relève de DOC-24.
