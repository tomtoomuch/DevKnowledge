"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const { createSessionHandler } = require("../src/supervisor-session-handler");

const key = "a".repeat(64);
const token = "b".repeat(64);
const cookie = "dk_session=" + token;
const principal = {
  user_id: "95689fc7-bd42-4201-b2df-c8368362016e",
  username: "admin", roles: ["ADMIN"], permissions: ["users.manage"],
};

async function withHandler(sessionStore, fn) {
  const server = http.createServer(createSessionHandler({gatewayKey: key, sessionStore}));
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  try {
    await fn("http://127.0.0.1:" + server.address().port);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}
function post(url, endpoint, payload, secret = key) {
  return fetch(url + "/internal/v1/auth/" + endpoint, {
    method: "POST",
    headers: {"x-service-key": secret, "content-type": "application/json"},
    body: JSON.stringify(payload),
  });
}
const store = () => ({
  login: async () => ({token, principal}),
  logout: async () => {},
});

test("rejects invalid signing key and missing identity store", () => {
  assert.throws(() => createSessionHandler({gatewayKey:"bad",sessionStore:store()}));
  assert.throws(() => createSessionHandler({gatewayKey:key,sessionStore:{}}));
});

test("internal login only returns a session to authenticated Gateway caller", async () => {
  let called = 0;
  await withHandler({
    login: async payload => {
      called++;
      assert.deepEqual(payload, {username:"admin",password:"password"});
      return {token,principal};
    },
    logout: async () => {},
  }, async url => {
    const unauthenticated = await post(url,"login",{username:"admin",password:"password"},"c".repeat(64));
    assert.equal(unauthenticated.status,401);
    const response = await post(url,"login",{username:"admin",password:"password"});
    assert.equal(response.status,200);
    assert.equal(response.headers.get("cache-control"),"no-store");
    const result = await response.json();
    assert.equal(result.session_token,token);
    assert.deepEqual(result.principal,principal);
  });
  assert.equal(called,1);
});

test("invalid login payloads, authentication failures and outage fail closed", async () => {
  await withHandler({
    login: async () => null, logout: async () => {},
  }, async url => {
    assert.equal((await post(url,"login",{username:"admin",password:"bad"})).status,401);
    assert.equal((await post(url,"login",{username:"admin"})).status,422);
    assert.equal((await post(url,"login",{username:"admin",password:"bad",admin:true})).status,422);
    assert.equal((await post(url,"logout",{session_cookie:"bad"})).status,422);
    assert.equal((await fetch(url + "/internal/v1/auth/login")).status,404);
    assert.equal((await fetch(url + "/internal/v1/auth/login?next=evil",{
      method:"POST",headers:{"content-type":"application/json","x-service-key":key},
      body:"{}",
    })).status,404);
  });
  await withHandler({
    login: async () => {throw new Error("SECRET_DATABASE_ERROR");},
    logout: async () => {},
  }, async url => {
    const response = await post(url,"login",{username:"admin",password:"bad"});
    assert.equal(response.status,503);
    assert.equal(JSON.stringify(await response.json()).includes("SECRET_DATABASE_ERROR"),false);
  });
});

test("logout revokes exactly the supplied opaque session and never returns token", async () => {
  let seen;
  await withHandler({
    login: async () => null,
    logout: async value => { seen = value; },
  }, async url => {
    const response = await post(url,"logout",{session_cookie:cookie});
    assert.equal(response.status,204);
    assert.equal(await response.text(),"");
  });
  assert.equal(seen,cookie);
});

test("invalid upstream login session token fails closed", async () => {
  await withHandler({
    login: async () => ({token:"bad",principal}),
    logout: async () => {},
  }, async url => {
    assert.equal((await post(url,"login",{username:"admin",password:"password"})).status,503);
  });
});

test("strict JSON content type and body size limits", async () => {
  await withHandler(store(), async url => {
    const unsupported = await fetch(url + "/internal/v1/auth/login", {
      method:"POST",headers:{"x-service-key":key,"content-type":"text/plain"},
      body:"{}",
    });
    assert.equal(unsupported.status,415);
    const huge = await post(url,"login",{username:"admin",password:"x".repeat(5000)});
    assert.equal(huge.status,413);
    const malformed = await fetch(url + "/internal/v1/auth/login", {
      method:"POST",headers:{"x-service-key":key,"content-type":"application/json"},
      body:"{not-json",
    });
    assert.equal(malformed.status,400);
  });
});
