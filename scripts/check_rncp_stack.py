"""Qualify the optional RNCP stack on synthetic, disposable data only.

Never reads .env or accepts a deployment project. --offline reuses prepared images.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from mongodb_backup import backup, restore

ROOT = Path(__file__).resolve().parents[1]
PG_SNAPSHOT = r"""
import hashlib,json,psycopg
from psycopg import sql
from app.rncp.migrate import connection_string
with psycopg.connect(connection_string()) as c:
    tables=c.execute("SELECT tablename FROM pg_tables WHERE schemaname='rncp' ORDER BY tablename").fetchall()
    result={}
    for (table,) in tables:
        rows=c.execute(sql.SQL('SELECT to_jsonb(t)::text FROM rncp.{} t ORDER BY to_jsonb(t)::text').format(sql.Identifier(table))).fetchall()
        result[table]={'count':len(rows),'sha256':hashlib.sha256('\n'.join(r[0] for r in rows).encode()).hexdigest()}
    print(json.dumps(result))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    project = 'devknowledge-rncp-stack-' + uuid4().hex[:12]
    directory = ROOT / 'test-results' / project
    directory.mkdir(parents=True)
    settings = dict(line.split('=', 1) for line in (ROOT / 'tests/stabilization.env').read_text().splitlines()
                    if line and not line.startswith('#'))
    settings.update(RNCP_PG_USER='rncp_test', RNCP_PG_PASSWORD='rncp-stack-test-password-only', RNCP_PG_DATABASE='rncp_test')
    env = {key: value for key, value in os.environ.items() if not key.startswith(
        ('COMPOSE_', 'MONGODB_', 'MONGO_INITDB_', 'RNCP_', 'POSTGRES_', 'GATEWAY_', 'KMS_', 'SUPERVISOR_', 'AUTH_', 'FRONTEND_'))}
    env.update(settings)
    compose = ['docker', 'compose', '--env-file', str(ROOT / 'tests/stabilization.env'), '-p', project]
    for name in ['compose.yaml', 'compose.rncp.yaml', 'tests/compose.identity.yaml', 'tests/rncp/compose.yaml']:
        compose += ['-f', str(ROOT / name)]
    report = {'project': project, 'offline': args.offline, 'checks': [], 'success': False}
    recovery = None
    restored_mongo = None

    def run(command, stdin=None, check=True, timeout=180, binary=False):
        result = subprocess.run(command, cwd=ROOT, env=env, input=stdin, capture_output=True,
                                text=not binary, **({} if binary else {'encoding': 'utf-8', 'errors': 'replace'}), timeout=timeout)
        if check and result.returncode:
            output = (result.stdout + result.stderr)
            if binary:
                output = output.decode('utf-8', errors='replace')
            for key, value in settings.items():
                if 'PASSWORD' in key or 'KEY' in key:
                    output = output.replace(value, '<test-secret>')
            raise RuntimeError(output[-5000:])
        return result

    def passed(label):
        report['checks'].append(label)
        print('PASS ' + label, flush=True)

    def healthy(command):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            raw = run(command + ['ps', '--format', 'json']).stdout.strip()
            rows = (json.loads(raw) if raw.startswith('[') else [json.loads(line) for line in raw.splitlines()]) if raw else []
            services = [r for r in rows if r['Service'] != 'rncp-migrate']
            if len(services) == 6 and all(r.get('Health') == 'healthy' for r in services):
                return
            time.sleep(2)
        raise RuntimeError('RNCP stack did not become healthy')

    def pg(command, sql):
        return run(command + ['exec', '-T', 'postgres-rncp', 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', settings['RNCP_PG_USER'], '-d', settings['RNCP_PG_DATABASE']], sql)

    def pg_snapshot(command):
        return json.loads(run(command + ['run', '--rm', '--no-deps', 'rncp-migrate', 'python', '-c', PG_SNAPSHOT]).stdout)

    state = {}

    def probe(command, phase):
        nonlocal state
        result = run(command + ['exec', '-T', 'api-gateway', 'node', '-e',
                                (ROOT / 'tests/rncp/roundtrip.js').read_text(encoding='utf-8')],
                     json.dumps({'phase': phase, 'state': state}))
        value = json.loads(result.stdout)
        state = value['state']
        for label in value['checks']:
            passed(phase + ': ' + label)

    try:
        config = json.loads(run(compose + ['config', '--format', 'json']).stdout)
        assert all(not value.get('ports') for value in config['services'].values())
        assert all(value['internal'] for value in config['networks'].values())
        assert config['services']['api-kms']['environment']['KMS_SERVICE_TOKEN_MODE'] == 'required'
        assert config['services']['supervisor']['environment']['SUPERVISOR_IDENTITY_MODE'] == 'active'
        if not args.offline:
            print('Building isolated RNCP images', flush=True)
            built = run(compose + ['build'], timeout=900)
            (directory / 'build.log').write_text(built.stdout + built.stderr, encoding='utf-8')
            run(compose + ['pull', 'postgres-rncp', 'mongodb'], timeout=300)
        run(compose + ['up', '-d', '--no-build', '--pull', 'never'])
        healthy(compose)
        for container in run(compose + ['ps', '-q']).stdout.split():
            actual = json.loads(run(['docker', 'inspect', container]).stdout)[0]
            assert not actual['HostConfig'].get('PortBindings')
            for network in actual['NetworkSettings']['Networks']:
                assert json.loads(run(['docker', 'network', 'inspect', network]).stdout)[0]['Internal']
        passed('Six healthy services, Supervisor authority, actual private networks and no host ports')
        run(compose + ['run', '--rm', '--no-deps', 'rncp-migrate'])
        passed('RNCP migrations replay without changes on an initialized volume')
        pg(compose, (ROOT / 'tests/rncp/seed.sql').read_text(encoding='utf-8'))
        run(compose + ['exec', '-T', 'supervisor', 'node', 'src/bootstrap-admin.js'],
            json.dumps({'username': 'admin', 'password': 'rncp-fixture-password-only'}))
        probe(compose, 'initial')
        # The author must be the authenticated Supervisor subject, not a browser header.
        author = pg(compose, "SELECT created_by_user_id FROM rncp.evidence_artifacts;").stdout
        assert state['editorId'] in author
        assert pg_snapshot(compose)['evidence_artifacts']['count'] == 1
        passed('SQL author matches authenticated user; failed writes leave no partial evidence')
        race = run(compose + ['exec', '-T', 'api-kms', 'python', '-c',
                   (ROOT / 'tests/rncp/cross_store_race.py').read_text(encoding='utf-8')],
                   json.dumps({'admin': state['admin'], 'port': settings['GATEWAY_PORT']}))
        finding = json.loads(race.stdout)
        assert finding['reproduced'] and finding['detected_by_audit']
        report['activation_gates'] = [finding['limitation']]
        passed('Concurrent MongoDB delete/SQL insert race reproduced deterministically and detected by read-only reference audit')
        audited = json.loads(run(compose + ['exec', '-T', 'api-kms', 'python', '-m', 'app.rncp.audit']).stdout)
        assert audited['consistent'] and audited['checked'] == 1
        for service, phase in [('postgres-rncp', 'pg-outage'), ('supervisor', 'supervisor-outage'), ('mongodb', 'mongo-outage')]:
            run(compose + ['stop', service])
            probe(compose, phase)
            run(compose + ['start', service])
            healthy(compose)
            probe(compose, 'recovery')
        run(compose + ['restart', 'postgres-rncp', 'mongodb', 'supervisor', 'api-kms', 'api-gateway'])
        healthy(compose)
        run(compose + ['run', '--rm', '--no-deps', 'rncp-migrate'])
        probe(compose, 'recovery')
        passed('All databases/services restart and migrations remain idempotent')
        # Freeze all application writers for a common MongoDB/PostgreSQL/SQLite checkpoint.
        run(compose + ['stop', 'api-gateway', 'api-kms', 'supervisor'])
        before = pg_snapshot(compose)
        dump = run(compose + ['exec', '-T', 'postgres-rncp', 'pg_dump', '-U', settings['RNCP_PG_USER'], '-d', settings['RNCP_PG_DATABASE'], '-Fc', '--no-owner', '--no-acl'], binary=True).stdout
        (directory / 'postgres.dump').write_bytes(dump)
        mongo_manifest = backup(compose, directory / 'mongodb-backup', env=env)
        supervisor = run(compose + ['ps', '-a', '-q', 'supervisor']).stdout.strip()
        run(['docker', 'cp', supervisor + ':/var/lib/devknowledge-supervisor', str(directory / 'metrics')])
        metrics_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted((directory / 'metrics').iterdir()) if path.is_file()}
        assert 'metrics.sqlite3' in metrics_hashes
        assert before == pg_snapshot(compose)
        report['checkpoint'] = {'postgres_sha256': hashlib.sha256(dump).hexdigest(), 'mongo_sha256': mongo_manifest['archive_sha256'],
                                'sql_tables': before, 'metrics_file_hashes': metrics_hashes}
        restored = restore(compose, directory / 'mongodb-backup', env=env, keep_volume=True)
        restored_mongo = restored['volume']
        assert restored['verified']
        passed('Writers stopped across MongoDB/PostgreSQL/SQLite; consistent archives and isolated MongoDB restore verified')
        overlay = directory / 'restore.yaml'
        overlay.write_text('volumes:\n  mongodb:\n    external: true\n    name: ' + restored_mongo + '\n    driver: !reset null\n', encoding='utf-8')
        recovery = compose.copy()
        recovery[recovery.index('-p') + 1] = project + '-restored'
        recovery += ['-f', str(overlay)]
        run(recovery + ['up', '-d', '--no-build', '--pull', 'never', '--wait', 'postgres-rncp', 'mongodb'])
        run(recovery + ['exec', '-T', 'postgres-rncp', 'pg_restore', '-U', settings['RNCP_PG_USER'], '-d', settings['RNCP_PG_DATABASE'], '--no-owner', '--no-acl', '--exit-on-error'], dump, binary=True)
        assert before == pg_snapshot(recovery)
        run(recovery + ['create', 'supervisor'])
        metrics_volume = project + '-restored_supervisor-metrics'
        run(['docker', 'run', '--rm', '--network', 'none', '--user', '0', '--mount', 'type=bind,source=' + str(directory / 'metrics') + ',target=/source,readonly',
             '--mount', 'type=volume,source=' + metrics_volume + ',target=/target', '--entrypoint', 'sh', config['services']['supervisor']['image'],
             '-c', 'cp -a /source/. /target/ && chown -R 1000:1000 /target'])
        restored_metrics = run(['docker', 'run', '--rm', '--network', 'none',
                                '--mount', 'type=volume,source=' + metrics_volume + ',target=/target,readonly',
                                '--entrypoint', 'node', config['services']['supervisor']['image'], '-e',
                                "const fs=require('node:fs'),crypto=require('node:crypto');"
                                "console.log(JSON.stringify(Object.fromEntries(fs.readdirSync('/target').filter(n=>fs.statSync('/target/'+n).isFile()).map(n=>[n,crypto.createHash('sha256').update(fs.readFileSync('/target/'+n)).digest('hex')]))));"])
        assert metrics_hashes == json.loads(restored_metrics.stdout)
        run(recovery + ['up', '-d', '--no-build', '--pull', 'never'])
        healthy(recovery)
        probe(recovery, 'recovery')
        run(recovery + ['exec', '-T', 'supervisor', 'node', 'src/metrics-backup.js', '/var/lib/devknowledge-supervisor/restored-check.sqlite3'])
        passed('Restored MongoDB/PostgreSQL/SQLite stack starts without downloads; persisted session and RNCP/business data remain usable')
        report['success'] = True
    except Exception as exc:
        report['error'] = str(exc)
        raise
    finally:
        for command in [recovery, compose]:
            if command:
                suffix = 'restored' if command is recovery else 'source'
                logs = run(command + ['logs', '--no-color'], check=False)
                (directory / (suffix + '.log')).write_text(logs.stdout, encoding='utf-8')
                report[suffix + '_cleanup'] = run(command + ['down', '--volumes'], check=False).returncode == 0
        if restored_mongo:
            report['mongo_restore_volume_cleanup'] = run(['docker', 'volume', 'rm', restored_mongo], check=False).returncode == 0
        cleanup_failed = any(value is False for key, value in report.items() if key.endswith('_cleanup'))
        if cleanup_failed:
            report['success'] = False
            report['error'] = report.get('error', '') + ' Isolated stack cleanup failed'
        (directory / 'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('Report: ' + str(directory / 'summary.json'), flush=True)
    if not report['success']:
        raise RuntimeError('RNCP qualification incomplete; see report')


if __name__ == '__main__':
    main()
