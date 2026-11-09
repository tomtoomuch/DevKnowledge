# Fonctionnement hors ligne après préparation

Le périmètre qualifié est le socle livré : Gateway Express, KMS FastAPI,
MongoDB, CRUD conditionnel, sauvegarde/restauration et reprise après panne.
Les images doivent déjà être disponibles localement. La construction des images
et l'installation des dépendances demandent encore une préparation connectée.

## Rejouer la qualification sans données personnelles

Docker doit fonctionner avec les conteneurs Linux ; Python 3.14 et Compose
2.24.4 minimum sont requis. Depuis la racine du dépôt :

```powershell
# Préparation connectée et validation complète sur une base jetable.
python scripts/check_stabilization.py

# Nouvelle base jetable ; aucun build et aucun téléchargement d'image.
python scripts/check_stabilization.py --offline
```

Le second appel refuse de démarrer si une des images manque. Il utilise
`--no-build --pull never`, puis contrôle les images effectivement exécutées,
l'attachement exclusif au réseau interne, l'absence de route par défaut dans
les trois conteneurs et le refus d'une connexion vers une adresse hors réseau.
La restauration utilise aussi `--pull never` et un conteneur `--network none`.

Les onze groupes de contrôles couvrent ensuite le démarrage vierge, le compte
MongoDB limité, le CRUD via Gateway et les préconditions, la sauvegarde et la
restauration, les redémarrages, les pannes et les identifiants incorrects.
L'isolation est revérifiée après le deuxième démarrage. Les volumes créés pour
ces tests sont supprimés, et les images préparées restent disponibles.

Les résultats sont dans `test-results/stabilization-offline.json`, séparément
du rapport connecté. Ils incluent les identifiants et plateformes des images,
le réseau contrôlé et le résultat du nettoyage. La CI exécute successivement
les deux modes et conserve leurs rapports.

Le test conserve la connexion de la machine hôte ; l'isolation concerne les
conteneurs testés. Il ne qualifie pas le démarrage de Docker Desktop sur une
machine physiquement déconnectée ni l'interface navigateur, qui n'existe pas
encore. La preuve porte sur l'exécution applicative sans route externe, pas
sur une capture exhaustive du trafic de l'hôte.

## Préparer le Compose de développement

Les images des tests ont des noms propres ; elles ne remplacent pas celles du
Compose de développement. Avec le `.env` local déjà configuré, préparer les
images de développement pendant que la connexion est disponible :

```powershell
docker compose config --quiet
docker compose pull mongodb
docker compose build api-gateway api-kms
```

Après préparation, le démarrage sans téléchargement ni build s'effectue avec :

```powershell
docker compose up -d --no-build --pull never --wait
docker compose ps
```

La Gateway reste accessible sur le port local configuré, par défaut
`http://127.0.0.1:3000`. Conserver les mêmes fichiers Compose, le même projet,
le `.env` et les volumes. Si un volume récupéré est utilisé, conserver aussi
la surcharge décrite dans [[backup-restore]]. Ces commandes de développement
n'ont pas été exécutées dans la qualification jetable.

## Limites de reproductibilité

- Un cache manquant fait échouer le démarrage hors ligne ; il faut préparer
  ou importer les images avant de se déconnecter.
- Les tags système restent mutables. Les identifiants enregistrés prouvent
  quelles images ont été testées, sans verrouiller les builds futurs.
- Un build complet hors ligne n'est pas qualifié : les caches npm/pip et les
  sources des images de base ne sont pas distribués dans un paquet autonome.
- Angular, authentification, modèles IA, RAG et synchronisation ne font pas
  partie du socle actuellement qualifié.

Références : [options de démarrage Compose](https://docs.docker.com/reference/cli/docker/compose/up/),
[réseau interne Compose](https://docs.docker.com/reference/compose-file/networks/#internal).
