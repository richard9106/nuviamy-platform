"""Restore a recent encrypted S3 backup in a disposable, offline PostgreSQL container.

Run on the AWS host as its existing Docker operator. Never connects to the live DB.
Reports contain aggregate metadata and belong in restricted operator storage.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import uuid

import boto3


def checked(args, **kwargs):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=600, **kwargs)
    if result.returncode:
        # stderr can contain SQL, object keys, credentials or decrypted values.
        raise RuntimeError('Recovery verification step failed; inspect privately, never publish raw output.')
    return result.stdout


def newest_backup(objects, now):
    eligible = [obj for obj in objects if obj['Key'].endswith('.dump.gpg')]
    if not eligible:
        raise ValueError('No encrypted PostgreSQL backup found.')
    obj = max(eligible, key=lambda value: value['LastModified'])
    age = (now - obj['LastModified']).total_seconds()
    if not 0 <= age <= 26 * 3600:
        raise ValueError('Latest backup is stale or dated in the future.')
    if not 0 < obj['Size'] <= 1024 ** 3:
        raise ValueError('Backup size is outside this bounded rehearsal capacity.')
    return obj


VALIDATE = '''
import json, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from django.apps import apps
from django.db import connection
from apps.practices.fields import EncryptedTextField
from apps.dashboard.fields import SupportEncryptedTextField
from django.core.management import call_command
from django.db.migrations.executor import MigrationExecutor
from apps.clinical.models import SessionNote
from ops.postgres_roles import GUARDS, verify_contract_guards
with connection.cursor() as cursor:
    cursor.execute("SELECT tgname, tgenabled FROM pg_trigger WHERE tgname = ANY(%s)", [list(GUARDS)])
    guards = dict(cursor.fetchall())
    assert set(guards) == GUARDS and all(v == 'O' for v in guards.values()), 'Guard validation failed'
# A valid older backup can precede the candidate release's migrations. Upgrade
# only the disposable copy, after checking its baseline protections.
executor = MigrationExecutor(connection)
plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
applied = [migration.app_label + '.' + migration.name for migration, backward in plan]
assert not any(backward for _, backward in plan), 'Unexpected reverse migration'
call_command('migrate', interactive=False, verbosity=0)
connection.ensure_connection()
contracts = verify_contract_guards(connection.connection)
with connection.cursor() as cursor:
    cursor.execute('SELECT count(*) FROM django_migrations')
    migrations = cursor.fetchone()[0]
counts, encrypted, signed = {}, 0, 0
for model in apps.get_models():
    if not model.__module__.startswith('apps.') or model._meta.proxy:
        continue
    counts[model._meta.label] = model.objects.count()
    fields = [f.name for f in model._meta.fields if isinstance(f, (EncryptedTextField, SupportEncryptedTextField))]
    if fields:
        for values in model.objects.values_list(*fields).iterator():
            encrypted += sum(bool(value) for value in values)
for note in SessionNote.objects.select_related('signature').filter(signature__isnull=False).iterator():
    assert note.review_digest() == note.signature_digest, 'Signed note digest mismatch'
    signed += 1
assert migrations > 0 and counts, 'Restored schema is empty'
print(json.dumps(dict(model_counts=counts, enabled_guards=len(guards)+contracts, migrations=migrations,
                     migrations_applied_to_isolated_copy=applied,
                     encrypted_values_read=encrypted, signed_note_digests_verified=signed)))
'''


def run(app_dir):
    started = time.monotonic()
    image = 'nuviamy-web:local'
    env_path = app_dir / '.env'
    if env_path.stat().st_mode & 0o077:
        raise ValueError('Production env file must have restricted permissions.')
    # Use the already installed parser in the app image, offline. Values never
    # become process arguments or shell code; only required fields are returned.
    parse = """import sys, json, io
from dotenv import dotenv_values
env = dotenv_values(stream=io.StringIO(sys.stdin.read()), interpolate=False)
keys = ('BACKUP_S3_BUCKET','BACKUP_S3_PREFIX','AWS_S3_REGION_NAME',
        'BACKUP_ENCRYPTION_PASSPHRASE','FIELD_ENCRYPTION_KEY')
print(json.dumps({key: env.get(key, '') for key in keys}))
"""
    config = json.loads(checked(['docker', 'run', '--rm', '-i', '--network', 'none', image,
                                 'python', '-c', parse], input=env_path.read_bytes()))
    if not all(config.get(key) for key in ('BACKUP_S3_BUCKET', 'BACKUP_ENCRYPTION_PASSPHRASE', 'FIELD_ENCRYPTION_KEY')):
        raise ValueError('Native S3 backup and recovery keys are required.')
    region = config.get('AWS_S3_REGION_NAME')
    if region in ('', 'auto', None):
        raise ValueError('Native S3 requires an explicit region.')
    client = boto3.client('s3', region_name=region)
    bucket = config['BACKUP_S3_BUCKET']
    prefix = (config.get('BACKUP_S3_PREFIX') or 'postgres').rstrip('/') + '/'
    pages = client.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix)
    obj = newest_backup([obj for page in pages for obj in page.get('Contents', [])], datetime.now(timezone.utc))
    name = 'nuviamy-recovery-' + uuid.uuid4().hex
    password = secrets.token_urlsafe(40)
    child_env = dict(os.environ, POSTGRES_PASSWORD=password,
                     FIELD_ENCRYPTION_KEY=config['FIELD_ENCRYPTION_KEY'])
    created = False
    with tempfile.TemporaryDirectory(prefix='nuviamy-recovery-') as work:
        work = Path(work)
        cipher, plain = work / 'backup.gpg', work / 'backup.dump'
        try:
            client.download_file(bucket, obj['Key'], str(cipher))
            digest = hashlib.sha256(cipher.read_bytes()).hexdigest()
            # Passphrase in a pipe FD, never argv or a plaintext passphrase file.
            read_fd, write_fd = os.pipe()
            try:
                os.write(write_fd, (config['BACKUP_ENCRYPTION_PASSPHRASE'] + '\n').encode())
                os.close(write_fd)
                checked(['gpg', '--homedir', str(work), '--batch', '--yes', '--pinentry-mode', 'loopback',
                         '--passphrase-fd', str(read_fd), '--output', str(plain), '--decrypt', str(cipher)],
                        pass_fds=(read_fd,))
            finally:
                os.close(read_fd)
            checked(['docker', 'run', '-d', '--name', name, '--network', 'none',
                '--label', 'nuviamy.security-recovery=true', '--memory', '384m', '--cpus', '0.5',
                '--tmpfs', '/var/lib/postgresql/data:rw,nosuid,size=256m',
                '--env', 'POSTGRES_PASSWORD', '--env', 'POSTGRES_USER=recovery',
                '--env', 'POSTGRES_DB=recovery', 'postgres:16-alpine'], env=child_env)
            created = True
            for _ in range(30):
                ready = subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'recovery', '-d', 'recovery'],
                                       capture_output=True, timeout=10)
                if ready.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError('Isolated recovery database did not become ready.')
            with plain.open('rb') as source:
                checked(['docker', 'exec', '-i', name, 'pg_restore', '-U', 'recovery', '-d', 'recovery',
                         '--no-owner', '--no-privileges', '--exit-on-error'], stdin=source)
            # Sharing the offline PG network namespace grants no outbound access.
            proof = json.loads(checked(['docker', 'run', '--rm', '--network', 'container:' + name,
                '--env', 'POSTGRES_PASSWORD', '--env', 'FIELD_ENCRYPTION_KEY',
                '--env', 'POSTGRES_USER=recovery', '--env', 'POSTGRES_DB=recovery',
                '--env', 'POSTGRES_HOST=127.0.0.1', '--env', 'DJANGO_ENVIRONMENT=test',
                '--env', 'DJANGO_DEBUG=true', '--env', 'SENTRY_DSN=',
                image, 'python', '-c', VALIDATE], env=child_env))
            return dict(observed_at=datetime.now(timezone.utc).isoformat(),
                backup_last_modified=obj['LastModified'].isoformat(), ciphertext_sha256=digest,
                backup_age_hours=round((datetime.now(timezone.utc) - obj['LastModified']).total_seconds() / 3600, 2),
                elapsed_seconds=round(time.monotonic() - started, 2),
                restored_database=True, outbound_network=False, production_database_modified=False,
                scope='Same-host isolated database recovery; not loss-of-region, document recovery or RTO proof.', **proof)
        finally:
            if created:
                checked(['docker', 'rm', '-f', name])


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.app_dir), indent=2))
    except Exception:
        raise SystemExit('Recovery verification failed. No raw provider/SQL/secret output was printed.')
