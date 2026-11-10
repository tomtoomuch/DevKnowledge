# DevKnowledge — POC SQL Server 2025 / PostgreSQL 17 (DOC-38)

Tests **réels** sur deux images Docker officielles, avec des données RNCP
**fictives**. Ce POC ne modifie aucune collection MongoDB, aucun volume
`dev` et aucun service du `compose.yaml` applicatif.

- `mcr.microsoft.com/mssql/server:2025-latest` (Developer, test uniquement)
- `postgres:17`
- Un réseau `internal: true`, aucun port publié, noms de projet Compose
  uniques `dkpoc-...` ; volumes temporaires nommés par projet.
- Identifiants forts générés aléatoirement à l'exécution, jamais commités.
- Six tables en correspondance avec le MLD RNCP v0.2 : référentiels,
  blocs, compétences, connaissances, preuves, liens connaissances/compétences.
- Contrôles : clés étrangères, unicité, JSON, jointures RNCP/preuves,
  rollback, conflit de révision, backup et restauration dans une nouvelle base.

Depuis Git Bash, après démarrage de Docker Desktop :

```bash
python poc/storage/run.py --engine sqlserver
python poc/storage/run.py --engine postgres
```

Les comptes temporaires ne sont pas réutilisés. Les résultats JSON sont
dans `test-results/storage-poc/` et publiés comme artefacts de CI. Il ne
faut **jamais** mélanger ce fichier Compose à celui de DevKnowledge ni
lui fournir les variables/volumes de l'application. Le mot de passe SQL
Server dans les exemples externes ne doit pas être appliqué au projet réel.

Le temps mesuré englobe parfois `docker compose exec` et l'initialisation.
Ce n'est **pas** un benchmark de débit/latence SQL directement comparable.
Le choix définitif SQL Server/PostgreSQL reste soumis à une évaluation plus
large (mémoire, licence, drivers FastAPI, charge et sécurité).

### Intégrité et limites

Les jeux de données sont artificiels (`RNCP-TEST`, non le contenu réel du
référentiel RNCP 37827). Les sauvegardes et restaurations sont exécutées
dans le conteneur temporaire, distinctes des données persistantes `dev`.
Aucune intégration applicative KMS/Angular ni migration ne sont prévues
dans ce POC initial. MongoDB demeure la source de vérité actuelle.
