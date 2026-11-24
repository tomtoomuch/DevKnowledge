"""Deterministically reproduce the documented interbase race on fixture data.

Runs inside the isolated KMS only. A PostgreSQL advisory lock pauses insertion
after MongoDB validation, then an authorized HTTP delete removes the reference.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import sys
import time
from urllib.request import Request, urlopen

import psycopg
from pymongo import MongoClient
from app.rncp.audit import audit_links
from app.rncp.migrate import connection_string


def main():
    state = json.load(sys.stdin)
    base = 'http://api-gateway:' + state['port']
    def call(path, method='GET', payload=None, headers=None):
        request = Request(base + path, method=method, data=json.dumps(payload).encode() if payload else None,
                          headers={'cookie': state['admin'], 'content-type': 'application/json', **(headers or {})})
        with urlopen(request, timeout=20) as response:
            body = response.read()
            return (json.loads(body) if body else None), response.headers

    item, headers = call('/api/v1/knowledges', 'POST',
                         {'title': 'Synthetic race fixture', 'content': 'Test only', 'knowledge_type': 'COURSE_NOTE'})
    knowledge = item['knowledge_id']
    with psycopg.connect(connection_string(), autocommit=True) as pg:
        pg.execute("""CREATE FUNCTION rncp.fixture_pause_link() RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN PERFORM pg_advisory_xact_lock(4242,42); RETURN NEW; END $$""")
        pg.execute('CREATE TRIGGER fixture_pause BEFORE INSERT ON rncp.knowledge_competency_links FOR EACH ROW EXECUTE FUNCTION rncp.fixture_pause_link()')
        pg.execute('SELECT pg_advisory_lock(4242,42)')
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(call, '/api/v1/rncp/competencies/40000000-0000-0000-0000-000000000001/knowledge-links', 'POST', {'knowledge_id': knowledge})
                try:
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        blocked = pg.execute("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND classid=4242 AND objid=42 AND NOT granted").fetchone()[0]
                        if blocked:
                            break
                        time.sleep(0.05)
                    else:
                        raise AssertionError('Did not reach cross-store validation barrier')
                    call('/api/v1/knowledges/' + knowledge, 'DELETE', headers={'if-match': headers['etag']})
                finally:
                    pg.execute('SELECT pg_advisory_unlock(4242,42)')
                link, _ = pending.result(timeout=20)
                assert link['knowledge_id'] == knowledge
        finally:
            pg.execute('SELECT pg_advisory_unlock(4242,42)')
            pg.execute('DROP TRIGGER fixture_pause ON rncp.knowledge_competency_links')
            pg.execute('DROP FUNCTION rncp.fixture_pause_link()')
        with MongoClient(os.environ['MONGODB_HOST'], username=os.environ['MONGODB_USERNAME'],
                         password=os.environ['MONGODB_PASSWORD'], authSource=os.environ['MONGODB_AUTH_SOURCE']) as mongo:
            with psycopg.connect(connection_string()) as audit_pg:
                audit_pg.execute('SET TRANSACTION READ ONLY')
                result = audit_links(audit_pg, mongo[os.environ['MONGODB_DATABASE']]['knowledge_items'])
            assert result['invalid_count'] == 1
            assert result['invalid_references'][0]['knowledge_id'] == knowledge
        # Remove only this synthetic race's SQL link before the consistent backup.
        # This fixture cleanup is not a production repair strategy.
        pg.execute('DELETE FROM rncp.knowledge_competency_links WHERE knowledge_id=%s', (knowledge,))
    print(json.dumps({'reproduced': True, 'detected_by_audit': True,
                      'limitation': 'MongoDB deletion after validation can leave an orphan PostgreSQL link; production activation requires a consistency policy'}))


if __name__ == '__main__':
    main()
