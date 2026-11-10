/*
 * Optional one-time provisioning of a minimally privileged Supervisor account.
 *
 * Run manually with mongosh only after a verified MongoDB backup. This file is
 * intentionally NOT mounted into /docker-entrypoint-initdb.d: existing volumes
 * are not automatically modified by new Compose deployments.
 *
 * Required environment:
 *   MONGODB_DATABASE
 *   MONGODB_SUPERVISOR_USERNAME
 *   MONGODB_SUPERVISOR_PASSWORD
 * The operator must use an authenticated MongoDB administration session.
 */
(() => {
  const dbName = process.env.MONGODB_DATABASE;
  const username = process.env.MONGODB_SUPERVISOR_USERNAME;
  const password = process.env.MONGODB_SUPERVISOR_PASSWORD;
  const appUsername = process.env.MONGODB_APP_USERNAME;
  const rootUsername = process.env.MONGO_INITDB_ROOT_USERNAME;
  if (!/^[A-Za-z][A-Za-z0-9_-]{0,62}$/.test(dbName || "") ||
      typeof username !== "string" || username.length < 3 ||
      typeof password !== "string" || password.length < 20 ||
      username === appUsername || username === rootUsername ||
      [username, password].some(value => /[\r\n\0]/.test(value))) {
    throw new Error("Supervisor reader provisioning: invalid configuration");
  }
  const target = db.getSiblingDB(dbName);
  const roleName = "supervisorIdentityReadOnly";
  const collections = [
    "users", "sessions", "user_roles", "roles",
    "role_permissions", "permissions",
  ];
  const privileges = collections.map(resource => ({
    resource: { db: dbName, collection: resource },
    actions: ["find"],
  }));
  const role = target.getRole(roleName, { showPrivileges: true });
  if (role === null) {
    target.createRole({ role: roleName, privileges, roles: [] });
  } else {
    const actual = role.privileges.map(item =>
      JSON.stringify({ resource: item.resource, actions: [...item.actions].sort() })).sort();
    const expected = privileges.map(item =>
      JSON.stringify({ resource: item.resource, actions: [...item.actions].sort() })).sort();
    if (JSON.stringify(actual) !== JSON.stringify(expected) ||
        role.roles.length !== 0) {
      throw new Error("Supervisor identity reader role has unexpected privileges");
    }
  }
  const existing = target.getUser(username);
  if (existing !== null) {
    const expectedRoles = [{ role: roleName, db: dbName }];
    if (JSON.stringify(existing.roles) !== JSON.stringify(expectedRoles)) {
      throw new Error("Supervisor identity account exists with unexpected roles");
    }
    print("Supervisor identity reader already exists; password not changed");
    return;
  }
  target.createUser({
    user: username, pwd: password,
    roles: [{ role: roleName, db: dbName }],
  });
  print("Supervisor identity reader created with find-only grants");
})();
