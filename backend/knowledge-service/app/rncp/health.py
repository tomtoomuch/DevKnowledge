"""Bounded PostgreSQL readiness probe, imported only in optional RNCP mode."""
import psycopg

from app.rncp.migrate import connection_string


def check_storage():
    with psycopg.connect(connection_string(), connect_timeout=2,
                         options='-c statement_timeout=2000') as connection:
        connection.execute('SELECT 1')
