# STAB-06 — validation Gateway du 9 novembre 2026

La stabilisation précédente a été fusionnée dans `dev` par la
[PR #2](https://github.com/tomtoomuch/DevKnowledge/pull/2), commit
`83048748b6d56c91eb8d14f1e4d6494eece94e79`, après quatre contrôles réussis.
Le relais est développé sur `chat` à partir de cette fusion.

## Résultat

Les connaissances sont accessibles à travers la Gateway. Le KMS est interne au
Compose par défaut ; `compose.debug.yaml` fournit un accès direct local optionnel.
Le [contrat du relais](../architecture/gateway-kms.md) décrit les chemins,
en-têtes, délais, limites de taille et codes d'erreur.

## Vérifications locales

- Gateway : **43 tests réussis**, deux suites Jest ; 100 % des lignes et 97,56 %
  des instructions de `app.js` et `kms-proxy.js` couvertes. Node 24.16.0 Windows.
- Compose normal et diagnostic : configuration acceptée. La configuration normale
  publie uniquement la Gateway sur loopback.
- Vrais conteneurs : CRUD complet via Gateway, filtres/pagination, suppression
  logique, identité anonyme et réponses 204/404/405/422 contrôlées.
- MongoDB arrêté : vivacité Gateway 200, readiness/CRUD 503, puis retour à 200
  après reprise sans redémarrer Gateway/KMS.
- KMS arrêté : vivacité Gateway 200, readiness/CRUD 502, puis reprise automatique.
- Bootstrap, rôles limités, index, redémarrage conservant les données et mauvais
  identifiants restent validés par `scripts/check_stabilization.py`.
- Huit groupes de vérifications réussis dans le rapport local
  `test-results/stabilization.json` ; nettoyage du projet jetable réussi.

La CI existante rejoue les tests Gateway, les tests KMS sur Linux/Windows,
les 117 tests KMS avec MongoDB et le scénario Compose étendu.
[Exécutions et artefacts](https://github.com/tomtoomuch/DevKnowledge/actions/workflows/ci.yml).

## Limites conservées

Aucune authentification/RBAC n'est ajoutée. La limite de corps entrant de 1 Mio
et le refus de compression s'appliquent à la Gateway. Les exemples directs sur
le port 8000 nécessitent désormais le mode de diagnostic.

Les données et conteneurs de développement n'ont pas été modifiés. STAB-08
(sauvegarde/restauration et concurrence) reste ouvert, ainsi que la revue de
sortie et la qualification hors ligne. La contrainte CI Ubuntu 22.04/MongoDB
reste celle décrite dans le rapport de stabilisation précédent.
