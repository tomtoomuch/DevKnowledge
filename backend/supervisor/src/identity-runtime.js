"use strict";

const { createMongoSessionLookup } = require("./mongo-session-lookup");
const { createAuthorizationHandler } = require("./supervisor-authorization");

const MODES = new Set(["disabled", "shadow"]);
const HOST = /^[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}$/;
const DB_NAME = /^[a-zA-Z][a-zA-Z0-9_-]{0,62}$/;

/**
 * Prepare a read-only MongoDB session authority for the Supervisor.
 *
 * "shadow" enables the authenticated internal endpoint but does not change
 * Gateway routing, KMS authentication or user/session ownership. This provides
 * an independent integration checkpoint before the destructive cutover.
 * No admin bootstrap, index writes, schema migrations or volume resets.
 *
 * MongoClient is injected for fast, hermetic tests. The production entrypoint
 * lazily loads the official MongoDB Node driver only when explicitly enabled.
 */
async function startIdentityAuthority({
  mode = process.env.SUPERVISOR_IDENTITY_MODE || "disabled",
  config = process.env,
  MongoClient,
  peerGuard,
} = {}) {
  if (!MODES.has(mode)) throw new Error("Unsupported Supervisor identity mode");
  if (mode === "disabled") return { authorizationHandler: null, close: async () => {} };
  if (typeof MongoClient !== "function") throw new Error("MongoDB driver required");
  const { SUPERVISOR_GATEWAY_KEY: gatewayKey, SUPERVISOR_KMS_TOKEN_KEY: kmsKey,
    MONGODB_USERNAME: username, MONGODB_PASSWORD: password,
    MONGODB_DATABASE: database, MONGODB_HOST: hostname = "mongodb",
    MONGODB_PORT: port = "27017", MONGODB_AUTH_SOURCE: authSource } = config;
  if (!HOST.test(hostname) || !DB_NAME.test(database || "") ||
      !DB_NAME.test(authSource || "") ||
      !/^[1-9][0-9]{0,4}$/.test(String(port)) || Number(port) > 65535 ||
      !username || !password || /[\r\n\0]/.test(username + password)) {
    throw new Error("Supervisor MongoDB identity configuration is invalid");
  }
  if (typeof peerGuard !== "function") throw new Error("Supervisor peer guard required");
  // Validate secrets and callable authorization dependencies BEFORE connecting.
  const preflight = createAuthorizationHandler({
    gatewayKey, kmsKey, lookupSession: async () => null,
  });
  if (!preflight) throw new Error("Invalid authorization configuration");

  const client = new MongoClient("mongodb://" + hostname + ":" + port + "/", {
    auth: { username, password },
    authSource,
    serverSelectionTimeoutMS: 3000,
    connectTimeoutMS: 3000,
    maxPoolSize: 5,
    retryWrites: false,
  });
  try {
    await client.connect();
    const db = client.db(database);
    await db.command({ ping: 1 });
    const lookupSession = createMongoSessionLookup(db);
    const handler = createAuthorizationHandler({ gatewayKey, kmsKey, lookupSession });
    const authorizationHandler = async (req, res) => {
      // Defend the internal API in depth: a valid service key alone is
      // insufficient if a caller is not on the approved private network.
      try {
        if (!(await peerGuard(req))) {
          res.setHeader("cache-control", "no-store");
          res.writeHead(404).end(JSON.stringify({ detail: "Not found" }));
          return;
        }
      } catch {
        res.writeHead(503).end(JSON.stringify({ detail: "Identity unavailable" }));
        return;
      }
      return handler(req, res);
    };
    return { authorizationHandler, close: async () => client.close() };
  } catch {
    await client.close();
    // Avoid propagating connection URI, credentials or MongoDB error strings.
    throw new Error("Supervisor identity database unavailable");
  }
}

module.exports = { startIdentityAuthority };
