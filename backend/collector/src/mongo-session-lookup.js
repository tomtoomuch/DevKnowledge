"use strict";

const { createHash } = require("node:crypto");

// Keep the same role semantics as KMS during the transitional migration.
// The MLD/ADR requires role codes and account revisions to remain stable.
const BUILTIN_ROLES = Object.freeze({
  ADMIN: ["knowledge.read", "knowledge.create", "knowledge.update", "knowledge.delete", "users.manage"],
  EDITOR: ["knowledge.read", "knowledge.create", "knowledge.update"],
  READER: ["knowledge.read"],
});
const SESSION = /^dk_session=([0-9a-f]{64})$/;

function normalizedPrincipal(user, codes) {
  const roles = [...new Set(codes)].sort();
  if (!roles.length || roles.some(role => !Object.hasOwn(BUILTIN_ROLES, role))) return null;
  return {
    user_id: user._id, username: user.username,
    roles,
    permissions: [...new Set(roles.flatMap(role => BUILTIN_ROLES[role]))].sort(),
  };
}

/**
 * MongoDB-backed session introspection.
 *
 * db must implement the regular MongoDB Collection API. This module deliberately
 * does not connect itself: the future Supervisor bootstrap owns the connection,
 * database credentials, readiness, reconnects and restricted MongoDB grants.
 *
 * The opaque browser cookie never appears in logs or the returned principal.
 */
function createMongoSessionLookup(db, now = () => new Date()) {
  if (!db || typeof db.collection !== "function") throw new TypeError("MongoDB database required");
  return async function lookupSession(cookie) {
    const parsed = SESSION.exec(cookie || "");
    if (!parsed) return null;
    const sessionId = createHash("sha256").update(parsed[1], "ascii").digest("hex");
    const session = await db.collection("sessions").findOne({ _id: sessionId });
    if (!session || !(session.expires_at instanceof Date) ||
        !Number.isFinite(session.expires_at.getTime()) ||
        session.expires_at.getTime() <= now().getTime()) return null;

    const user = await db.collection("users").findOne({
      _id: session.user_id, account_status: "ACTIVE",
    });
    if (!user || user.deleted_at || typeof user._id !== "string" ||
        typeof user.username !== "string" ||
        (session.identity_revision ?? 1) !== (user.revision ?? 1)) return null;

    if (Array.isArray(user.role_codes)) {
      return normalizedPrincipal(user, user.role_codes);
    }

    // Legacy accounts used user_roles instead of the atomic role_codes field.
    const assignments = await db.collection("user_roles")
      .find({ user_id: user._id }).limit(100).toArray();
    if (!assignments.length) return null;
    const roleIds = assignments.map(item => item.role_id);
    const roles = await db.collection("roles")
      .find({ _id: { $in: roleIds } }).limit(100).toArray();
    // Resolve privileges from the stored RBAC graph, rather than inferring
    // grants for legacy/custom role records that might have been restricted.
    const grants = await db.collection("role_permissions")
      .find({ role_id: { $in: roles.map(r => r._id) } }).limit(500).toArray();
    const perms = await db.collection("permissions")
      .find({ _id: { $in: grants.map(g => g.permission_id) } }).limit(500).toArray();
    const allowed = new Set(perms.map(p => p.code));
    const principal = normalizedPrincipal(user, roles.map(r => r.code));
    if (!principal) return null;
    principal.permissions = principal.permissions.filter(p => allowed.has(p));
    return principal;
  };
}

module.exports = { createMongoSessionLookup, BUILTIN_ROLES };
