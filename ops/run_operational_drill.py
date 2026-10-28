"""Orchestrate disposable offline PostgreSQL and image-based synthetic exercises.

No production env file, volume, database, cloud credentials or TCP network is used.
Reports and synthetic encrypted backup artifacts are written only to a NEW private
subdirectory. Never interprets the timings as a measured production RTO.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import uuid

from cryptography.fernet import Fernet


def checked(args, **kwargs):
    result = subprocess.run(args, capture_output=True, timeout=600, **kwargs)
    if result.returncode:
        raise RuntimeError('Synthetic drill step failed; inspect the isolated workspace privately.')
    return result.stdout


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(data)


def run(image, parent):
    if not parent.is_dir() or parent.stat().st_mode & 0o077:
        raise ValueError('Evidence parent must already exist with mode 0700.')
    suffix = uuid.uuid4().hex[:12]
    root = parent / ('offline-' + suffix)
    root.mkdir(mode=0o700)
    socket_dir = root / 'pgsocket'
    socket_dir.mkdir(mode=0o777)
    socket_dir.chmod(0o777)  # Parent remains 0700; PostgreSQL's uid owns its socket.
    pg = 'nuviamy-ops-drill-' + suffix
    database = 'nuviamy_ops_drill_' + suffix + '_rehearsal'
    restored = 'nuviamy_ops_drill_restore_' + suffix + '_rehearsal'
    password = secrets.token_urlsafe(40)
    pg_env = root / 'postgres.env'
    private_write(pg_env, f'POSTGRES_DB={database}\nPOSTGRES_USER=postgres\nPOSTGRES_PASSWORD={password}\n'.encode())
    config = {'DJANGO_ENVIRONMENT':'test', 'DJANGO_DEBUG':'false', 'DJANGO_ALLOWED_HOSTS':'testserver,localhost',
        'DJANGO_SECRET_KEY': secrets.token_urlsafe(50), 'FIELD_ENCRYPTION_KEY': Fernet.generate_key().decode(),
        'POSTGRES_DB':database, 'POSTGRES_USER':'postgres', 'POSTGRES_PASSWORD':password,
        'POSTGRES_HOST':'/pgsocket', 'POSTGRES_PORT':'5432', 'OPS_SYNTHETIC_DRILL':'1',
        'DJANGO_STORAGE_BACKEND':'', 'EMAIL_BACKEND':'django.core.mail.backends.dummy.EmailBackend',
        'MFA_REQUIRED':'false', 'MFA_PRIVILEGED_REQUIRED':'true', 'EMAIL_TWO_STEP_REQUIRED':'false',
        'SENTRY_DSN':'', 'AWS_EC2_METADATA_DISABLED':'true', 'AWS_ACCESS_KEY_ID':'',
        'AWS_SECRET_ACCESS_KEY':'', 'AWS_SESSION_TOKEN':'', 'STRIPE_SECRET_KEY':'',
        'STRIPE_PUBLISHABLE_KEY':'', 'STRIPE_WEBHOOK_SECRET':'', 'GOOGLE_OAUTH_CLIENT_ID':'',
        'GOOGLE_OAUTH_CLIENT_SECRET':''}
    app_env = root / 'application.env'
    def save_env(path, values):
        private_write(path, ''.join(k+'='+v+'\n' for k,v in values.items()).encode())
    save_env(app_env, config)
    key = Fernet.generate_key()
    private_write(root / 'synthetic-backup.key', key)
    private_write(root / 'independent-ledger.key', secrets.token_bytes(32))
    ops_dir = Path(__file__).resolve().parent
    report = {'format':1, 'started_at':datetime.now(timezone.utc).isoformat(),
        'synthetic_only':True, 'database_network':'none', 'application_network':'none',
        'image':image, 'production_modified':False, 'steps':[]}
    started = time.monotonic()
    def app(command, env=app_env):
        return checked(['docker','run','--rm','--user',f'{os.getuid()}:{os.getgid()}','--network','none','--read-only','--tmpfs','/tmp',
            '--mount',f'type=bind,src={socket_dir},dst=/pgsocket',
            '--mount',f'type=bind,src={root},dst=/evidence',
            '--mount',f'type=bind,src={ops_dir},dst=/app/ops,readonly',
            '--env-file',str(env),image,*command])
    def phase(name, env=app_env):
        result = json.loads(app(['python','-m','ops.drill_scenario',name],env))
        report['steps'].append({'phase':name,'at':datetime.now(timezone.utc).isoformat(),
                                'elapsed_seconds':round(time.monotonic()-started,3),'result':result})
    created = False
    try:
        checked(['docker','run','-d','--rm','--network','none','--name',pg,
            '--label','nuviamy.synthetic.drill=1','--env-file',str(pg_env),
            '--mount',f'type=bind,src={socket_dir},dst=/var/run/postgresql','postgres:16-alpine'])
        created = True
        for _ in range(60):
            ready = subprocess.run(['docker','exec',pg,'pg_isready','-U','postgres'],capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Isolated PostgreSQL did not become ready.')
        app(['python','manage.py','migrate','--noinput'])
        phase('seed')
        dump = checked(['docker','exec',pg,'pg_dump','-U','postgres','-Fc','--no-owner','-d',database])
        document = (root / 'media' / 'synthetic-document.txt').read_bytes()
        snapshot = json.dumps({'database':base64.b64encode(dump).decode(),
                              'document':base64.b64encode(document).decode()}).encode()
        ciphertext = Fernet(key).encrypt(snapshot)
        private_write(root/'synthetic-backup.fernet',ciphertext)
        report['backup_ciphertext_sha256'] = hashlib.sha256(ciphertext).hexdigest()
        phase('dispose')
        checked(['docker','exec',pg,'createdb','-U','postgres',restored])
        recovered = json.loads(Fernet(key).decrypt((root/'synthetic-backup.fernet').read_bytes()))
        checked(['docker','exec','-i',pg,'pg_restore','-U','postgres','--no-owner','--exit-on-error','-d',restored],
                input=base64.b64decode(recovered['database']))
        (root/'media'/'synthetic-document.txt').write_bytes(base64.b64decode(recovered['document']))
        restored_env = root/'restored-application.env'
        save_env(restored_env,dict(config,POSTGRES_DB=restored))
        from ops.verify_s3_recovery import VALIDATE
        restored_proof = json.loads(app(['python','-c',VALIDATE],restored_env))
        assert restored_proof['enabled_guards'] == 17
        report['restored_database_validation'] = restored_proof
        wrong_env = root/'wrong-field-key.env'
        save_env(wrong_env,dict(config,POSTGRES_DB=restored,FIELD_ENCRYPTION_KEY=Fernet.generate_key().decode()))
        try:
            app(['python','-c',VALIDATE],wrong_env)
        except RuntimeError:
            report['wrong_field_key_rejected'] = True
        else:
            raise AssertionError('An incorrect field key was accepted.')
        phase('verify-restored',restored_env)
        phase('reconcile-restored',restored_env)
        tests_env = root/'test-application.env'
        save_env(tests_env,dict(config,OPS_DRILL_REPORT_DIR='/evidence'))
        app(['python','manage.py','test','apps.accounts.test_operational_drills','--noinput'],tests_env)
        report['scoped_http_and_incident_tests'] = 'passed'
        # Simulate the legitimate schema of a pre-support-release backup in
        # another disposable copy; never modify the just-validated restoration.
        compatibility = 'nuviamy_ops_drill_old_' + suffix + '_rehearsal'
        checked(['docker','exec',pg,'createdb','-U','postgres',compatibility])
        checked(['docker','exec','-i',pg,'pg_restore','-U','postgres','--no-owner','--exit-on-error','-d',compatibility],input=dump)
        checked(['docker','exec','-i',pg,'psql','-U','postgres','-d',compatibility,'-v','ON_ERROR_STOP=1'],
            input=b"DROP TABLE dashboard_supportmessage; DROP TABLE dashboard_supportticket; DELETE FROM django_migrations WHERE app='dashboard' AND name='0003_supportticket_supportmessage';")
        compatibility_env = root/'older-schema-application.env'
        save_env(compatibility_env,dict(config,POSTGRES_DB=compatibility))
        older_proof = json.loads(app(['python','-c',VALIDATE],compatibility_env))
        assert 'dashboard.0003_supportticket_supportmessage' in older_proof['migrations_applied_to_isolated_copy']
        report['older_schema_recovered_with_isolated_migrations'] = True
        report['completed_at'] = datetime.now(timezone.utc).isoformat()
        report['total_seconds'] = round(time.monotonic()-started,3)
        report['result'] = 'passed'
        private_write(root/'report.json',json.dumps(report,sort_keys=True,indent=2).encode())
        return root,report
    except Exception as error:
        report['result'] = 'failed'
        report['failure_type'] = type(error).__name__
        private_write(root/'failure.json',json.dumps(report,sort_keys=True,indent=2).encode())
        raise
    finally:
        if created:
            subprocess.run(['docker','rm','-f','-v',pg],capture_output=True)
        # These env files contain synthetic credentials only, and remain private for
        # reproducing evidence. They are never copied into a backup or Git artifact.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True)
    parser.add_argument('--evidence-dir',type=Path,required=True)
    args = parser.parse_args()
    root,report = run(args.image,args.evidence_dir)
    print(json.dumps({'evidence_directory':str(root),'result':report['result'],
                      'total_seconds':report['total_seconds'],'synthetic_only':True},sort_keys=True))


if __name__ == '__main__':
    main()
