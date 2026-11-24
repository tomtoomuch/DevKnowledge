"use strict";
const assert = require('node:assert/strict');
const {randomUUID} = require('node:crypto');
const base = 'http://127.0.0.1:' + process.env.GATEWAY_PORT;
const comp = '40000000-0000-0000-0000-000000000001';
const framework = '/api/v1/rncp/frameworks/RNCP-TEST/versions/';
const evidence = '/api/v1/rncp/competencies/' + comp + '/evidence';
const link = '/api/v1/rncp/competencies/' + comp + '/knowledge-links';
const password = 'rncp-fixture-password-only';
const checks = [];
async function call(path, {cookie,method='GET',body,headers={},expected=200,origin=base}={}) {
  const response = await fetch(origin+path,{method,headers:{...headers,...(cookie?{cookie}:{}),...(body?{'content-type':'application/json'}:{})},
    body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(20000)});
  assert.equal(response.status,expected,method+' '+path+' status');
  const text = await response.text();
  return {body:text && response.headers.get('content-type')?.includes('json')?JSON.parse(text):text,headers:response.headers};
}
async function login(username) {
  const result = await call('/api/v1/auth/login',{method:'POST',body:{username,password}});
  assert.equal(result.body.session_token,undefined);
  return result.headers.get('set-cookie').split(';')[0];
}
async function main({phase,state={}}) {
  if(phase==='supervisor-outage'||phase==='mongo-outage') {
    await call(framework+'v1',{cookie:state.admin,expected:503});
    checks.push('Identity dependency outage refuses RNCP without fallback');return state;
  }
  if(phase==='pg-outage') {
    await call(framework+'v1',{cookie:state.admin,expected:503});
    await call(evidence,{cookie:state.admin,method:'POST',body:{title:'Unavailable write',evidence_type_code:'UNIT_TEST'},expected:503});
    await call('/api/v1/knowledges',{cookie:state.admin});
    await call('/health/ready',{expected:503});
    checks.push('PostgreSQL outage refuses RNCP reads/writes and readiness, MongoDB knowledge remains readable');return state;
  }
  if(phase==='recovery') {
    const result=await call(evidence,{cookie:state.admin});
    assert.ok(result.body.evidence.some(e=>e.id===state.evidence));
    await call('/api/v1/knowledges/'+state.knowledge,{cookie:state.admin});
    assert.equal((await call(framework+'v2',{cookie:state.admin})).body.blocks[0].competencies[0].evidence_count,0);
    checks.push('Persisted session, knowledge, RNCP evidence and version boundaries survive restart/restoration');return state;
  }
  await call(framework+'v1',{expected:401});
  state.admin=await login('admin');
  for(const [username,roles] of [['editor',['EDITOR']],['reader',['READER']]]) {
    const user=await call('/api/v1/users',{cookie:state.admin,method:'POST',body:{username,password,roles},expected:201});
    if(username==='editor')state.editorId=user.body.user_id;
  }
  const editor=await login('editor'),reader=await login('reader');
  const one=(await call(framework+'v1',{cookie:reader})).body;
  assert.equal(one.blocks[0].competencies[0].id,comp);assert.equal(one.blocks[0].competencies[0].criteria_count,1);
  assert.notEqual((await call(framework+'v2',{cookie:reader})).body.blocks[0].competencies[0].id,comp);
  await call(framework+'missing',{cookie:reader,expected:404});
  await call('/api/v1/rncp/arbitrary',{cookie:state.admin,expected:404});
  await call(evidence,{cookie:reader,method:'POST',body:{title:'Denied',evidence_type_code:'UNIT_TEST'},expected:403});
  await call(evidence,{cookie:editor,method:'POST',body:{title:'Denied origin',evidence_type_code:'UNIT_TEST'},headers:{origin:'https://untrusted.invalid'},expected:403});
  checks.push('Versioned RNCP reads, Gateway allowlist, RBAC and origin checks through Supervisor JWTs');
  const created=await call(evidence,{cookie:editor,method:'POST',body:{title:'Synthetic evidence',evidence_type_code:'UNIT_TEST'},headers:{'x-user-id':randomUUID(),authorization:'Bearer forged'},expected:201});
  state.evidence=created.body.id;assert.equal(created.body.verification_status,'PENDING');
  await call(evidence,{cookie:editor,method:'POST',body:{title:'   ',evidence_type_code:'UNIT_TEST'},expected:422});
  await call(evidence,{cookie:editor,method:'POST',body:{title:'Invalid type',evidence_type_code:'UNKNOWN'},expected:422});
  await call('/api/v1/rncp/competencies/'+randomUUID()+'/evidence',{cookie:editor,method:'POST',body:{title:'Missing competency',evidence_type_code:'UNIT_TEST'},expected:404});
  state.knowledge=(await call('/api/v1/knowledges',{cookie:editor,method:'POST',body:{title:'RNCP linked knowledge',content:'Synthetic',knowledge_type:'COURSE_NOTE'},expected:201})).body.knowledge_id;
  await call(link,{cookie:editor,method:'POST',body:{knowledge_id:state.knowledge,confidence_score:0.75},expected:201});
  await call(link,{cookie:editor,method:'POST',body:{knowledge_id:state.knowledge},expected:409});
  await call(link,{cookie:editor,method:'POST',body:{knowledge_id:randomUUID()},expected:422});
  const deleted=await call('/api/v1/knowledges',{cookie:editor,method:'POST',body:{title:'Deleted fixture',content:'Synthetic',knowledge_type:'COURSE_NOTE'},expected:201});
  await call('/api/v1/knowledges/'+deleted.body.knowledge_id,{cookie:state.admin,method:'DELETE',headers:{'if-match':deleted.headers.get('etag')},expected:204});
  await call(link,{cookie:editor,method:'POST',body:{knowledge_id:deleted.body.knowledge_id},expected:422});
  checks.push('Evidence transaction, real MongoDB reference validation, deleted/missing reference and duplicate refusals');
  const user=await call('/api/v1/users/'+state.editorId,{cookie:state.admin});
  await call('/api/v1/users/'+state.editorId,{cookie:state.admin,method:'PATCH',body:{roles:['READER']},headers:{'if-match':user.headers.get('etag')}});
  await call(evidence,{cookie:editor,expected:401});
  await call(evidence,{cookie:await login('editor'),method:'POST',body:{title:'Revoked write',evidence_type_code:'UNIT_TEST'},expected:403});
  const direct=await call(framework+'v1',{origin:'http://api-kms:8000',cookie:state.admin,expected:401});
  assert.ok(direct.body.detail);
  checks.push('Role change revokes existing session; fresh reader cannot write; KMS refuses browser cookie');
  return state;
}
(async()=>{let input='';for await(const part of process.stdin)input+=part;const state=await main(JSON.parse(input));process.stdout.write(JSON.stringify({checks,state}));})()
  .catch(e=>{console.error(e.message);process.exitCode=1;});
