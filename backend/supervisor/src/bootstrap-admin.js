"use strict";

// Credentials arrive over stdin, never in arguments or logs.
async function main() {
  if (process.env.SUPERVISOR_IDENTITY_MODE !== "active") throw new Error("Active identity required");
  const { MongoClient } = require("mongodb");
  const { initializeIdentity, bootstrapAdmin } = require("./identity-users");
  let input = "";
  for await (const chunk of process.stdin) {
    input += chunk;
    if (input.length > 8192) throw new Error("Invalid bootstrap payload");
  }
  const { username, password } = JSON.parse(input);
  const client = new MongoClient(`mongodb://${process.env.MONGODB_HOST}:${process.env.MONGODB_PORT || 27017}/`, {
    auth: { username: process.env.MONGODB_USERNAME, password: process.env.MONGODB_PASSWORD },
    authSource: process.env.MONGODB_AUTH_SOURCE, serverSelectionTimeoutMS: 3000,
  });
  try {
    await client.connect();
    const db = client.db(process.env.MONGODB_DATABASE);
    await initializeIdentity(db);
    await bootstrapAdmin(db, username, password);
    process.stdout.write("Initial administrator created\n");
  } finally { await client.close(); }
}
if (require.main === module) main().catch(() => {
  console.error("Administrator bootstrap refused or unavailable; existing accounts are preserved");
  process.exitCode = 1;
});
