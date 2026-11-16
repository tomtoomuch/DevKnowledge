"use strict";

const { createHash, randomBytes, scrypt: scryptCallback, timingSafeEqual } = require("node:crypto");
const { promisify } = require("node:util");
const { createMongoSessionLookup } = require("./mongo-session-lookup");

const scrypt = promisify(scryptCallback);
const USERNAME = /^[a-z0-9_.-]{3,40}$/;
const SESSION_COOKIE = /^dk_session=([0-9a-f]{64})$/;
const PASSWORD_HASH = /^scrypt\$32768\$8\$3\$([0-9a-f]{32})\$([0-9a-f]{128})$/i;
const DUMMY_SALT = Buffer.alloc(16);
const DUMMY_HASH = Buffer.alloc(64);
const SCRYPT_OPTIONS = { N: 32768, r: 8, p: 3, maxmem: 64 * 1024 * 1024 };
const SESSION_TTL_MS = 8 * 60 * 60 * 1000;

function usernameKey(username) {
  if (typeof username !== "string") return null;
  const key = username.trim().toLowerCase();
  return USERNAME.test(key) ? key : null;
}

async function verifyLegacyPassword(password, encoded) {
  if (typeof password !== "string" || password.length > 256) return false;
  const match = typeof encoded === "string" ? PASSWORD_HASH.exec(encoded) : null;
  const salt = match ? Buffer.from(match[1], "hex") : DUMMY_SALT;
  const digest = match ? Buffer.from(match[2], "hex") : DUMMY_HASH;
  // Match the existing FastAPI/Python scrypt parameters and dklen=64 bytes.
  const actual = await scrypt(password, salt, 64, SCRYPT_OPTIONS);
  return Boolean(match) && timingSafeEqual(actual, digest);
}

/**
 * Implements the existing KMS MongoDB session document contract without
 * changing the schema or bootstrapping administrators. This module is NOT
 * wired to an HTTP route or enabled in the read-only "shadow" mode.
 */
function createIdentitySessionStore(db, {
  now = () => new Date(),
  generateToken = () => randomBytes(32).toString("hex"),
} = {}) {
  if (!db || typeof db.collection !== "function") throw new TypeError("MongoDB required");
  const sessions = db.collection("sessions");
  const users = db.collection("users");
  const lookupSession = createMongoSessionLookup(db, now);

  async function login({ username, password } = {}) {
    // Always perform a password hash operation to reduce user enumeration
    // through authentication timing (even if the username does not exist).
    const key = usernameKey(username);
    const user = key ? await users.findOne({ username_key: key }) : null;
    const match = await verifyLegacyPassword(password, user?.password_hash);
    if (!match || !user || user.account_status !== "ACTIVE" || user.deleted_at ||
        !Number.isSafeInteger(user.revision ?? 1) || (user.revision ?? 1) < 1) {
      return null;
    }
    const issuedAt = now();
    if (!(issuedAt instanceof Date) || !Number.isFinite(issuedAt.getTime())) {
      throw new Error("Invalid identity clock");
    }
    // Prevent a concurrent disable/role revision from authorizing login
    // after the account has changed, using an optimistic revision guard.
    const result = await users.updateOne({
      _id: user._id, account_status: "ACTIVE",
      revision: user.revision ?? 1, deleted_at: null,
    }, { $set: { last_login_at: issuedAt } });
    if (result.matchedCount !== 1) return null;

    const token = generateToken();
    if (typeof token !== "string" || !/^[0-9a-f]{64}$/.test(token)) {
      throw new Error("Invalid session token generator");
    }
    const id = createHash("sha256").update(token, "ascii").digest("hex");
    await sessions.insertOne({
      _id: id, user_id: user._id, identity_revision: user.revision ?? 1,
      created_at: issuedAt,
      expires_at: new Date(issuedAt.getTime() + SESSION_TTL_MS),
    });
    let principal;
    try {
      principal = await lookupSession("dk_session=" + token);
    } catch (error) {
      await sessions.deleteOne({ _id: id });
      throw error;
    }
    if (!principal) {
      await sessions.deleteOne({ _id: id });
      return null;
    }
    return { token, principal };
  }

  async function logout(cookie) {
    const match = SESSION_COOKIE.exec(cookie || "");
    if (!match) return;
    const id = createHash("sha256").update(match[1], "ascii").digest("hex");
    await sessions.deleteOne({ _id: id });
  }

  return { login, logout, lookupSession };
}

module.exports = { createIdentitySessionStore, verifyLegacyPassword, usernameKey };
