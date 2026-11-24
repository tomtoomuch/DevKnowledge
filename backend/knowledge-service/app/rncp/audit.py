"""Read-only cross-store reference audit; freeze application writers for certification.

This detects orphan links. It does not provide a distributed transaction or
repair/delete evidence automatically.
"""
import json
import os

import psycopg
from pymongo import MongoClient

from app.rncp.migrate import connection_string


def audit_links(connection, knowledge_collection, sample_limit=100):
    checked = invalid_count = 0
    invalid = []
    with connection.cursor(name='rncp_reference_audit') as cursor:
        cursor.execute('SELECT link_id, knowledge_id FROM rncp.knowledge_competency_links ORDER BY link_id')
        while rows := cursor.fetchmany(500):
            identifiers = [str(row[1]) for row in rows]
            active = {row['_id'] for row in knowledge_collection.find(
                {'_id': {'$in': identifiers}, 'deleted_at': None}, {'_id': 1})}
            for link, knowledge in rows:
                checked += 1
                if str(knowledge) not in active:
                    invalid_count += 1
                    if len(invalid) < sample_limit:
                        invalid.append({'link_id': str(link), 'knowledge_id': str(knowledge)})
    return {'checked': checked, 'consistent': invalid_count == 0, 'invalid_count': invalid_count,
            'invalid_references': invalid, 'sample_truncated': invalid_count > len(invalid)}


def main():
    with MongoClient(os.environ.get('MONGODB_HOST', 'mongodb'), int(os.environ.get('MONGODB_PORT', '27017')),
                     username=os.environ['MONGODB_USERNAME'], password=os.environ['MONGODB_PASSWORD'],
                     authSource=os.environ['MONGODB_AUTH_SOURCE'], serverSelectionTimeoutMS=3000) as mongo:
        with psycopg.connect(connection_string()) as pg:
            pg.execute('SET TRANSACTION READ ONLY')
            result = audit_links(pg, mongo[os.environ['MONGODB_DATABASE']]['knowledge_items'])
    print(json.dumps(result))
    return 0 if result['consistent'] else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        # Never emit DSNs, credentials or document contents in an operational error.
        print(json.dumps({'error': 'RNCP reference audit unavailable'}))
        raise SystemExit(1) from None
