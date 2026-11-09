# Modifications concurrentes — STAB-08

Les connaissances exposent un entier `revision`. Une création commence à 1.
Chaque PATCH ou suppression logique réussie incrémente cet entier dans la même
opération MongoDB que la modification. Aucun contrôle ne dépend de la précision
de `updated_at`.

POST, GET individuel et PATCH renvoient `ETag: "N"`, où N est la révision, avec
`Cache-Control: no-store`. Les listes contiennent `revision` dans chaque élément.
La Gateway transmet `If-Match`, `ETag` et `Cache-Control`.

## Changement de contrat pour les clients

**PATCH et DELETE exigent maintenant `If-Match`**, contenant une seule révision
entre guillemets. Exemple :

```http
GET /api/v1/knowledges/UUID

HTTP/1.1 200 OK
ETag: "1"

PATCH /api/v1/knowledges/UUID
Content-Type: application/json
If-Match: "1"

{"title":"Nouveau titre"}
```

La réponse réussie contient `revision: 2` et `ETag: "2"`. Un autre client
présentant encore `"1"` reçoit **412** et ne modifie rien. Il doit relire la
connaissance, examiner les différences et décider de sa nouvelle modification.
Il ne faut pas réessayer aveuglément avec le dernier ETag.

- Précondition absente : **428**.
- Précondition mal formée, dupliquée, liste, joker `*` ou ETag faible : **400**.
  Cette API admet uniquement une révision forte unique pour garantir la
  protection contre les écrasements ; elle ne prend pas en charge toutes les
  formes générales du champ HTTP If-Match.
- Révision dépassée sur une ressource active : **412**.
- Ressource inexistante ou déjà supprimée, avec précondition valide : **404**.
- Erreurs métier/Pydantic : **422** ; indisponibilité MongoDB : **503**.

`revision` est un champ serveur : il n'est pas accepté dans les corps de création
ou de modification. Les clients existants doivent d'abord lire la ressource,
puis envoyer son ETag lors d'une écriture.

## Données historiques et atomicité

Un document ancien sans `revision` est lu comme révision 0. La première écriture
conditionnelle avec `If-Match: "0"` crée la révision 1. Aucune migration globale
ou suppression des données existantes n'est nécessaire.

Le filtre MongoDB contient l'identifiant, l'absence de suppression et la révision
attendue ; `$inc` et `$set` sont effectués dans un seul `find_one_and_update`.
Deux écritures concurrentes avec la même révision ne peuvent donc pas réussir
toutes les deux. La suppression utilise le même contrôle.

Après une restauration ancienne, fermer/recharger les clients et relire tous
les ETag : les révisions appartiennent à l'historique restauré. Ce mécanisme
n'est ni un journal de versions, ni une authentification ou une autorisation.

Référence : [préconditions HTTP, RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#name-if-match).
