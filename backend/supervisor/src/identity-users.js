"use strict";

const { createHash, randomBytes, randomUUID, scrypt: rawScrypt } = require("node:crypto");
const { promisify } = require("node:util");
const { BUILTIN_ROLES } = require("./mongo-session-lookup");
const { usernameKey } = require("./identity-sessions");
const scrypt = promisify(rawScrypt);
const now = () => new Date(Math.floor(Date.now() / 1000) * 1000);
const fail = (status, message) => { throw Object.assign(new Error(message), { status }); };
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Same UUIDv5 namespace and names as Python uuid5(NAMESPACE_URL, ...).
function uid(kind, code) {
  const hash = createHash("sha1").update(Buffer.from("6ba7b8119dad11d180b400c04fd430c8", "hex"))
    .update(`devknowledge:${kind}:${code}`).digest().subarray(0, 16);
  hash[6] = (hash[6] & 15) | 80;
  hash[8] = (hash[8] & 63) | 128;
  const value = hash.toString("hex");
  return `${value.slice(0,8)}-${value.slice(8,12)}-${value.slice(12,16)}-${value.slice(16,20)}-${value.slice(20)}`;
}

function validatePassword(password) {
  if (typeof password !== "string" || [...password].length < 12 || [...password].length > 256 || !password.trim()) {
    fail(422, "Password must have 12 to 256 characters");
  }
}
async function hashPassword(password) {
  validatePassword(password);
  const salt = randomBytes(16);
  const hash = await scrypt(password, salt, 64, { N: 32768, r: 8, p: 3, maxmem: 64 * 1024 * 1024 });
  return `scrypt$32768$8$3$${salt.toString("hex")}$${hash.toString("hex")}`;
}
function validateRoles(roles) {
  if (!Array.isArray(roles) || !roles.length || roles.length > 3 || new Set(roles).size !== roles.length ||
      roles.some(role => !Object.hasOwn(BUILTIN_ROLES, role))) fail(422, "Invalid roles");
  return [...roles].sort();
}
function fields(payload, allowed, required = []) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload) ||
      Object.keys(payload).some(key => !allowed.includes(key)) ||
      required.some(key => !Object.hasOwn(payload, key))) fail(422, "Invalid account payload");
}
function revision(header) {
  if (header === undefined) fail(428, "If-Match is required; read the resource first");
  if (typeof header !== "string" || !/^"(0|[1-9][0-9]{0,15})"$/.test(header)) fail(400, "Invalid If-Match");
  const value = Number(header.slice(1, -1));
  if (!Number.isSafeInteger(value) || value >= Number.MAX_SAFE_INTEGER) fail(400, "Revision is out of range");
  return value;
}

async function initializeIdentity(db) {
  await db.collection("users").createIndex({ username_key: 1 }, { unique: true, name: "username_unique" });
  await db.collection("user_roles").createIndex({ user_id: 1, role_id: 1 }, { unique: true });
  await db.collection("role_permissions").createIndex({ role_id: 1, permission_id: 1 }, { unique: true });
  await db.collection("sessions").createIndex({ expires_at: 1 }, { expireAfterSeconds: 0, name: "expiry" });
  for (const [code, permissions] of Object.entries(BUILTIN_ROLES)) {
    const roleId = uid("role", code);
    await db.collection("roles").updateOne({ _id: roleId }, { $setOnInsert: {
      code, name: code[0] + code.slice(1).toLowerCase(), description: "Built-in local role",
    } }, { upsert: true });
    for (const permission of permissions) {
      const permissionId = uid("permission", permission);
      const [resource, action] = permission.split(".");
      await db.collection("permissions").updateOne({ _id: permissionId }, { $setOnInsert: {
        code: permission, resource, action,
      } }, { upsert: true });
      await db.collection("role_permissions").updateOne({ _id: roleId + ":" + permissionId }, {
        $setOnInsert: { role_id: roleId, permission_id: permissionId },
      }, { upsert: true });
    }
  }
}

function createUserManagement(db) {
  const users = db.collection("users");
  async function rolesFor(user) {
    if (Array.isArray(user.role_codes)) return user.role_codes;
    const assignments = await db.collection("user_roles").find({ user_id: user._id }).limit(100).toArray();
    const roles = await db.collection("roles").find({ _id: { $in: assignments.map(a => a.role_id) } }).limit(100).toArray();
    return roles.map(r => r.code).filter(code => Object.hasOwn(BUILTIN_ROLES, code));
  }
  async function publicUser(user) {
    return { user_id: user._id, username: user.username, account_status: user.account_status,
      roles: [...new Set(await rolesFor(user))].sort(), revision: user.revision ?? 1,
      created_at: user.created_at ?? null, updated_at: user.updated_at ?? null, last_login_at: user.last_login_at ?? null };
  }
  async function record(id) {
    if (!UUID.test(id)) fail(422, "Invalid account identifier");
    const user = await users.findOne({ _id: id.toLowerCase(), account_status: { $ne: "DELETED" } });
    if (!user) fail(404, "User not found");
    return user;
  }
  async function syncRoles(id, roles) {
    await db.collection("user_roles").deleteMany({ user_id: id });
    for (const role of roles) {
      const roleId = uid("role", role);
      await db.collection("user_roles").insertOne({ _id: id + ":" + roleId, user_id: id, role_id: roleId, assigned_at: now() });
    }
  }
  async function create(payload) {
    fields(payload, ["username", "password", "roles"], ["username", "password", "roles"]);
    const key = usernameKey(payload.username);
    if (!key) fail(422, "Invalid account identifier");
    const roles = validateRoles(payload.roles);
    const encoded = await hashPassword(payload.password);
    const stamp = now();
    const user = { _id: randomUUID(), username: key, username_key: key, email: null,
      password_hash: encoded, oidc_issuer: null, oidc_subject: null, account_status: "ACTIVE",
      created_at: stamp, updated_at: stamp, last_login_at: null, revision: 1, role_codes: roles, deleted_at: null };
    await users.insertOne(user);
    await syncRoles(user._id, roles);
    return publicUser(user);
  }
  // No automatic lease stealing: a suspended writer must never resume after
  // another worker has stolen its lock. A crash leaves a fail-closed mutex;
  // recovery requires stopping all identity writers before clearing its owner.
  async function guarded(operation) {
    const mutex = db.collection("identity_admin_mutex");
    const owner = randomUUID();
    try {
      await mutex.findOneAndUpdate({ _id: "admin", owner: { $exists: false } }, {
        $set: { owner, acquired_at: now() }, $unset: { expires_at: "" },
      }, { upsert: true, returnDocument: "after" });
    } catch (error) {
      if (error.code === 11000) fail(409, "Account administration busy; retry later");
      throw error;
    }
    try { return await operation(); }
    finally { await mutex.updateOne({ _id: "admin", owner }, { $unset: { owner: "", acquired_at: "" } }); }
  }
  async function mutate(id, expected, actor, payload, kind, reauthorize) {
    let encoded;
    if (kind === "password") {
      fields(payload, ["password"], ["password"]);
      encoded = await hashPassword(payload.password);
    } else if (kind === "patch") {
      fields(payload, ["username", "roles", "account_status"]);
      if (!Object.keys(payload).length || Object.values(payload).some(value => value === null)) fail(422, "Empty or null update");
      if (payload.username !== undefined && !usernameKey(payload.username)) fail(422, "Invalid account identifier");
      if (payload.roles !== undefined) validateRoles(payload.roles);
      if (payload.account_status !== undefined && !["ACTIVE", "DISABLED"].includes(payload.account_status)) fail(422, "Invalid account status");
    }
    return guarded(async () => {
      // Recheck the actor under the same mutex as all identity mutations.
      if (reauthorize) await reauthorize();
      const current = await record(id);
      if ((current.revision ?? 1) !== expected) fail(412, "Revision changed");
      const oldRoles = await rolesFor(current);
      const roles = kind === "delete" ? [] : payload.roles ?? oldRoles;
      const status = kind === "delete" ? "DELETED" : payload.account_status ?? current.account_status;
      if (kind !== "password") {
        if (current._id === actor && (status !== "ACTIVE" || !roles.includes("ADMIN"))) fail(409, "Cannot disable or demote the current administrator");
        if (current.account_status === "ACTIVE" && oldRoles.includes("ADMIN") &&
            (status !== "ACTIVE" || !roles.includes("ADMIN"))) {
          let admins = 0;
          for await (const user of users.find({ account_status: "ACTIVE", deleted_at: null })) {
            if ((await rolesFor(user)).includes("ADMIN")) admins++;
          }
          if (admins <= 1) fail(409, "Cannot remove the last active administrator");
        }
      }
      const changes = { updated_at: now(), revision: expected + 1 };
      if (kind === "password") changes.password_hash = encoded;
      else {
        Object.assign(changes, { role_codes: [...roles].sort(), account_status: status });
        if (payload.username !== undefined) changes.username = changes.username_key = usernameKey(payload.username);
        if (kind === "delete") Object.assign(changes, { password_hash: null, deleted_at: now() });
      }
      const guard = Object.hasOwn(current, "revision") ? { revision: current.revision } : { revision: { $exists: false } };
      const updated = await users.findOneAndUpdate({ _id: current._id, account_status: { $ne: "DELETED" }, ...guard },
        { $set: changes }, { returnDocument: "after" });
      if (!updated) fail(412, "Revision changed");
      await db.collection("sessions").deleteMany({ user_id: current._id });
      if (kind !== "password") await syncRoles(current._id, roles);
      return publicUser(updated);
    });
  }
  return {
    create, mutate, guarded,
    get: async id => publicUser(await record(id)),
    list: async (skip, limit) => Promise.all((await users.find({ account_status: { $ne: "DELETED" } })
      .sort({ username_key: 1, _id: 1 }).skip(skip).limit(limit).toArray()).map(publicUser)),
  };
}

async function bootstrapAdmin(db, username, password) {
  if (!usernameKey(username)) fail(422, "Invalid account identifier");
  validatePassword(password);
  const management = createUserManagement(db);
  return management.guarded(async () => {
    if (await db.collection("users").countDocuments({})) fail(409, "An account already exists: bootstrap forbidden");
    await db.collection("auth_bootstrap").insertOne({ _id: "initial-admin", created_at: now() });
    return management.create({ username, password, roles: ["ADMIN"] });
  });
}

module.exports = { createUserManagement, initializeIdentity, bootstrapAdmin, uid, revision, fail };
