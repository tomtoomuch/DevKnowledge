/**
 * Provisionnement du compte applicatif uniquement lors du premier démarrage
 * sur un /data/db vierge (mécanisme de l'image officielle mongo:8.0).
 *
 * Les valeurs viennent des variables d'environnement du conteneur MongoDB.
 * Aucun mot de passe n'est stocké dans ce script ni affiché dans les logs.
 */
(() => {
  const databaseName = process.env.MONGODB_DATABASE;
  const username = process.env.MONGODB_APP_USERNAME;
  const password = process.env.MONGODB_APP_PASSWORD;

  if (!databaseName || !username || !password) {
    throw new Error("Initialisation MongoDB : variables applicatives manquantes");
  }
  if (["admin", "local", "config"].includes(databaseName)) {
    throw new Error("Initialisation MongoDB : nom de base réservé");
  }
  if (username === process.env.MONGO_INITDB_ROOT_USERNAME) {
    throw new Error("Initialisation MongoDB : le compte applicatif doit être distinct du compte admin");
  }

  const appDb = db.getSiblingDB(databaseName);
  const existingUser = appDb.getUser(username);

  if (existingUser === null) {
    appDb.createUser({
      user: username,
      pwd: password,
      roles: [{ role: "readWrite", db: databaseName }],
    });
    print("Compte MongoDB applicatif initialisé dans " + databaseName);
  } else {
    const correctRole = existingUser.roles.length === 1 &&
      existingUser.roles[0].role === "readWrite" &&
      existingUser.roles[0].db === databaseName;
    if (!correctRole) {
      throw new Error("Initialisation MongoDB : permissions applicatives inattendues");
    }
    print("Compte MongoDB applicatif déjà présent dans " + databaseName);
  }
})();
