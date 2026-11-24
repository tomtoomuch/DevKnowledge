/* Run on a fresh volume via Compose, or explicitly after backup on an existing
 * database. Creates NEW restricted accounts; never changes existing passwords,
 * roles or data. A mismatching existing account/role causes a refusal. */
(() => {
  const name = process.env.MONGODB_DATABASE;
  const kms = process.env.MONGODB_KMS_USERNAME;
  const supervisor = process.env.MONGODB_SUPERVISOR_USERNAME;
  const kmsPassword = process.env.MONGODB_KMS_PASSWORD;
  const supervisorPassword = process.env.MONGODB_SUPERVISOR_PASSWORD;
  if (!/^[A-Za-z][A-Za-z0-9_-]{0,62}$/.test(name || "") || ["admin", "local", "config"].includes(name) ||
      [kms, supervisor].some(value => typeof value !== "string" || value.length < 3 || /[\r\n\0]/.test(value)) ||
      [kmsPassword, supervisorPassword].some(value => typeof value !== "string" || value.length < 20 || /[\r\n\0]/.test(value)) ||
      new Set([kms, supervisor, process.env.MONGODB_APP_USERNAME, process.env.MONGO_INITDB_ROOT_USERNAME]).size !== 4) {
    throw new Error("Distinct identity-owner accounts and credentials required");
  }
  const database = db.getSiblingDB(name);
  const actions = ["find", "insert", "update", "remove", "createIndex", "createCollection", "listIndexes"];
  const entries = [
    ["kmsBusinessOwner", kms, kmsPassword, ["knowledge_items", "knowledge_types", "tags", "technologies", "technology_versions", "relation_types", "knowledge_relations"]],
    ["supervisorIdentityOwner", supervisor, supervisorPassword, ["users", "sessions", "roles", "permissions", "user_roles", "role_permissions", "auth_bootstrap", "identity_admin_mutex"]],
  ];
  const normalized = privileges => privileges.map(p => JSON.stringify({ db: p.resource.db,
    collection: p.resource.collection, actions: [...p.actions].sort() })).sort().join("|");
  // Inspect all existing grants before creating anything.
  for (const [roleName, username, , collections] of entries) {
    const privileges = collections.map(collection => ({ resource: { db: name, collection }, actions }));
    const existingRole = database.getRole(roleName, { showPrivileges: true });
    const existingUser = database.getUser(username);
    if (existingRole && (existingRole.roles.length || normalized(existingRole.privileges) !== normalized(privileges))) throw new Error("Unexpected existing owner role");
    if (existingUser && (existingUser.roles.length !== 1 || existingUser.roles[0].role !== roleName || existingUser.roles[0].db !== name)) throw new Error("Unexpected existing owner account");
  }
  for (const [roleName, username, password, collections] of entries) {
    if (!database.getRole(roleName)) database.createRole({ role: roleName, roles: [],
      privileges: collections.map(collection => ({ resource: { db: name, collection }, actions })) });
    if (!database.getUser(username)) database.createUser({ user: username, pwd: password, roles: [{ role: roleName, db: name }] });
  }
  print("Restricted business and identity accounts verified; existing passwords unchanged");
})();
