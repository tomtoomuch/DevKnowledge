# Qualification locale de la migration identité — 24 novembre 2026

Le circuit Gateway → Superviseur pour l'identité et Gateway → KMS avec jeton interne a été implémenté et qualifié sur la base `chat` à `a26ba97ac705668d627833ad908874babbaf72e1`. Le candidat est publié pour revue depuis `codex/doc-41-identity-migration`. Ce rapport consigne les preuves locales ; les résultats de CI distante sont suivis dans la PR et DOC-41. Il ne constitue pas une activation sur l'installation existante.

Suivi : [DOC-41 — Migration identité](https://linear.app/documentation-perso/issue/DOC-41), [DOC-40 — Sessions compatibles KMS](https://linear.app/documentation-perso/issue/DOC-40), parent [DOC-23](https://linear.app/documentation-perso/issue/DOC-23). La promotion reste suivie dans [DOC-24](https://linear.app/documentation-perso/issue/DOC-24).

## Changement livré

Le Superviseur possède les comptes, sessions et rôles MongoDB. La Gateway conserve les contrats HTTP de l'interface et ne transmet au KMS que des JWT internes de courte durée avec permission et audience. Les routes d'identité et le bootstrap KMS sont désactivés en mode obligatoire. Les deux services utilisent des comptes MongoDB distincts, limités à leurs collections.

Les anciennes sessions, empreintes de mots de passe, associations RBAC et comptes sans révision sont acceptés sans réécriture de masse. Les mutations utilisent des révisions conditionnelles, révoquent les sessions et protègent le dernier administrateur. Une panne du Superviseur ferme l'accès sans bascule vers l'ancienne autorité.

## Vérifications exécutées

| Vérification | Résultat |
| --- | --- |
| Gateway, tests Jest | 84 tests réussis |
| Superviseur, tests Node sans MongoDB | 56 tests réussis |
| Superviseur, intégration MongoDB réelle | 12 tests réussis |
| KMS, suite complète avec MongoDB réelle | 234 tests réussis ; un avertissement de dépréciation existant |
| Scripts de maintenance, unittest | 21 tests réussis |
| Recette identité complète sur cinq conteneurs | Réussie |
| Recette identité avec images préparées, sans build ni téléchargement | Réussie |
| Recette de stabilisation historique normale et hors ligne | Réussie |
| Workflow GitHub Actions, actionlint | Réussi |
| Espaces et conflits de patch, git diff --check | Réussi |

La recette identité couvre bootstrap unique, session KMS historique, login/logout, droits et refus cross-origin, en-têtes forgés, CRUD des comptes, doublons, ETags et erreurs 428/412, changements de rôle/statut/mot de passe, suppression logique, refus d'auto-démotion, absence des routes d'identité KMS, refus des cookies et faux JWT par KMS, portée des JWT vérifiée côté Python, indisponibilité du Superviseur, redémarrage et persistance.

Elle vérifie également les refus d'accès MongoDB entre les collections des deux services, l'intégrité de la sauvegarde SQLite, la sauvegarde/restauration MongoDB (documents, index, droits des nouveaux comptes), puis le redémarrage de l'application sur un volume restauré avec réutilisation d'une ancienne session et lecture du contenu métier créé pendant la recette.

## Preuves locales

- `test-results/devknowledge-identity-test-52b135d5f2ea/summary.json` : campagne complète finale, `success: true`, 19 contrôles, identifiants des images, réseaux réellement internes et absence de ports publiés vérifiés sur les conteneurs.
- `test-results/devknowledge-identity-test-a06a1de17e15/summary.json` : campagne hors ligne, `success: true`, redémarrage sur restauration et session historique acceptée.
- `test-results/kms-migration-integration.log` : suite KMS complète.
- `test-results/supervisor-migration-integration.log` : intégration du Superviseur.
- `test-results/stabilization.json` et `test-results/stabilization-offline.json` : campagnes du circuit historique conservé pour régression.

Les deux rapports identité confirment le nettoyage des projets source, projets restaurés et volumes de restauration créés par les recettes. Les cinq conteneurs de l'installation `devknowledge` sont restés arrêtés ; ses volumes et son `.env` n'ont pas été modifiés.

## Limites et mise en service

La qualification utilise des données synthétiques sur des volumes jetables. Le mode hors ligne réutilise des images préparées ; il ne prouve pas une construction intégralement déconnectée. La page Angular est servie par la Gateway, mais tous les écrans n'ont pas fait l'objet d'une revue visuelle manuelle. La matrice Windows/Linux distante doit être exécutée après publication.

La [procédure de migration](../operations/identity-migration.md) couvre le provisionnement contrôlé d'une installation existante, la vérification préalable d'une restauration, le bootstrap neuf, la reprise après verrou abandonné et le retour arrière. L'activation sur les données existantes et la promotion des branches sont distinctes de cette qualification locale. La signature asymétrique et la rotation avec plusieurs clés restent des travaux de durcissement de DOC-23.
