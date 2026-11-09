# Sauvegarde locale et restauration — STAB-08

Les sauvegardes sont manuelles, locales et sans synchronisation distante,
conformément à l'ADR-002. Python et Docker Compose sont requis. Les commandes
utilisent le projet `devknowledge` et le `.env` du dépôt par défaut ; préciser
`--project NOM --env-file CHEMIN` pour un autre environnement.

## Sauvegarder

Depuis la racine du dépôt, choisir un **nouveau dossier** :

```powershell
python scripts/mongodb_backup.py backup backups/avant-travail
```

MongoDB doit être démarré. La commande interrompt temporairement les services
Gateway/KMS qui étaient en marche, puis les redémarre même si le dump échoue.
Un service initialement arrêté reste arrêté. Pour une sauvegarde cohérente de
ce MongoDB autonome, ne pas exécuter d'autres outils d'écriture directe pendant
l'opération. L'outil compare aussi l'état avant et après le dump et refuse de
certifier une base modifiée entre ces deux lectures.

Le dossier contient `database.archive.gz` (BSON compressé, via `mongodump`) et
`manifest.json` : date UTC, version MongoDB, SHA-256 de l'archive, empreinte et
nombre de documents par collection, index et options de collection. Les
documents supprimés logiquement, révisions, UUID et dates BSON sont inclus.
Les vues et bases système ne sont pas prises en charge. Les utilisateurs MongoDB
ne sont pas inclus ; ils sont reprovisionnés depuis la configuration locale lors
de la restauration.

Un dossier existant n'est jamais écrasé. Un dump interrompu peut laisser une
archive `.partial`, sans manifeste valide : elle ne sera pas restaurée par l'outil.
Si le processus est tué avant son bloc de reprise, vérifier `docker compose ps`
et redémarrer explicitement les services qui étaient en marche.

Les identifiants administrateur servent uniquement aux outils de maintenance.
Le mot de passe est lu dans l'environnement du conteneur et placé dans un fichier
temporaire de permissions 0600, supprimé après usage ; il n'est ni passé en
argument aux outils MongoDB ni consigné dans le manifeste.

**Le contenu des sauvegardes n'est pas chiffré.** Le dossier `backups/` est ignoré
par Git. Conserver les archives dans un emplacement local privé ; le chiffrement
doit être défini avant une éventuelle copie externe. SHA-256 détecte une altération
accidentelle, mais n'authentifie pas un fichier provenant d'un tiers.

## Vérifier une restauration

```powershell
python scripts/mongodb_backup.py restore-check backups/avant-travail
```

L'archive est vérifiée avant toute allocation. La commande crée un conteneur
sans réseau et un volume neufs, restaure uniquement la base configurée, puis
compare documents, types BSON, index et options au manifeste. Elle recrée et
vérifie le compte applicatif limité. Le conteneur et le volume sont supprimés
après ce contrôle. Les données sources ne sont pas touchées.

La base doit porter le même nom que dans le `.env` choisi et le serveur cible
doit avoir la même version majeure MongoDB. Un changement de version majeure
relève d'une migration séparée.

## Produire un volume de récupération

```powershell
python scripts/mongodb_backup.py restore backups/avant-travail
```

La même validation est exécutée, puis le conteneur est arrêté et supprimé.
Le **nouveau volume** est conservé et son nom `devknowledge-restored-...` est
retourné. L'outil n'accepte aucun nom de volume existant comme cible et n'utilise
pas `mongorestore --drop`. En cas d'échec avant validation, le volume neuf est
supprimé ; l'archive d'origine est conservée.

## Activer explicitement la récupération

Cette étape est une intervention distincte sur le développement : les commandes
de sauvegarde/restauration ne l'exécutent pas. Conserver le volume d'origine et,
si possible, sauvegarder son état avant de basculer. Fermer les clients ouverts ;
après restauration ils doivent relire les ressources et leurs ETag.

Avec le même projet et le même `.env` que lors de la restauration :

```powershell
$env:RESTORED_MONGODB_VOLUME = "devknowledge-restored-IDENTIFIANT_RETOURNE"
docker compose -f compose.yaml -f compose.recovery.yaml config --quiet
docker compose stop api-gateway api-kms mongodb
docker compose -f compose.yaml -f compose.recovery.yaml up -d --force-recreate
docker compose -f compose.yaml -f compose.recovery.yaml ps
```

Vérifier la readiness et les connaissances via la Gateway avant de reprendre le
travail. **Conserver cette surcharge pour les démarrages suivants** : démarrer
sans elle sélectionne à nouveau le volume d'origine. Ne supprimer aucun volume
d'origine dans cette procédure ; un éventuel retour arrière doit tenir compte
des nouvelles écritures effectuées après récupération.

Références : [mongodump](https://www.mongodb.com/docs/database-tools/mongodump/),
[mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/).
