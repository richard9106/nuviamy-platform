"""Bounded host health checks and explicitly configured operator notifications.

Run from the deployed app directory with its existing instance role. No clinical
content is read, stored, or included in email. Does not restart services or restore.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

import boto3


def checked(args, **kwargs):
    result = subprocess.run(args, capture_output=True, timeout=60, **kwargs)
    if result.returncode:
        raise RuntimeError('Operational command failed; raw output withheld.')
    return result.stdout


def collect(app_dir):
    checks = {}
    try:
        # TLS is validated; health returns no clinical data.
        with urllib.request.urlopen('https://nuviamy.com/health/', timeout=15) as response:
            checks['https_health'] = response.status == 200 and json.loads(response.read(1024)) == {'status': 'ok'}
    except Exception:
        checks['https_health'] = False
    for service in ('nuviamy-postgres-backup', 'certbot'):
        result = subprocess.run(['systemctl', 'show', service + '.service', '--property=Result', '--value'],
                                capture_output=True, text=True, timeout=15)
        checks[service + '_last_result'] = result.returncode == 0 and result.stdout.strip() == 'success'
    timer = subprocess.run(['systemctl', 'is-active', '--quiet', 'nuviamy-postgres-backup.timer'], timeout=15)
    checks['backup_timer_active'] = timer.returncode == 0
    try:
        # Read only the non-secret destination in the protected .env, using the
        # app's installed dotenv parser in a short-lived offline container.
        parse = """import sys,io,json
from dotenv import dotenv_values
e=dotenv_values(stream=io.StringIO(sys.stdin.read()),interpolate=False)
print(json.dumps({k:e.get(k,'') for k in ('BACKUP_S3_BUCKET','BACKUP_S3_PREFIX','AWS_S3_REGION_NAME')}))"""
        config = json.loads(checked(['docker', 'run', '--rm', '-i', '--network', 'none',
            'nuviamy-web:local', 'python', '-c', parse], input=(app_dir / '.env').read_bytes()))
        if not config['BACKUP_S3_BUCKET'] or config['AWS_S3_REGION_NAME'] in ('', 'auto'):
            raise ValueError('Native S3 destination required.')
        s3 = boto3.client('s3', region_name=config['AWS_S3_REGION_NAME'])
        pages = s3.get_paginator('list_objects_v2').paginate(Bucket=config['BACKUP_S3_BUCKET'],
            Prefix=(config['BACKUP_S3_PREFIX'] or 'postgres').rstrip('/') + '/')
        dates = [obj['LastModified'] for page in pages for obj in page.get('Contents', [])
                 if obj['Key'].endswith('.dump.gpg') and obj['Size'] > 0]
        age = (datetime.now(timezone.utc) - max(dates)).total_seconds() if dates else -1
        checks['encrypted_backup_recent'] = 0 <= age <= 26 * 3600
    except Exception:
        checks['encrypted_backup_recent'] = False
    return checks


def notification_due(previous, failures, now):
    return bool(failures) and (previous.get('failure_codes') != failures
        or now - previous.get('notified_at', 0) >= 86400)


def notify(app_dir, recipient, failures):
    code = """import os,json
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django; django.setup()
from django.core.mail import send_mail
from django.conf import settings
payload=json.loads(__import__('sys').stdin.read())
body='An operational health check needs attention. Checks: '+', '.join(payload['failures'])+'. Review the private host status. This notice contains no clinical data or credentials.'
assert send_mail('NuviaMy: operational check needs attention',body,settings.DEFAULT_FROM_EMAIL,[payload['recipient']],fail_silently=False)==1
"""
    checked(['docker', 'compose', 'exec', '-T', 'web', 'python', '-c', code],
            cwd=app_dir, input=json.dumps({'recipient': recipient, 'failures': failures}).encode())


def run(app_dir, state_path, recipient):
    state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with state_path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous = json.loads(state_path.read_text()) if state_path.exists() else {}
        checks = collect(app_dir)
        failures = sorted(key for key, valid in checks.items() if not valid)
        now = time.time()
        report = dict(checked_at=datetime.now(timezone.utc).isoformat(), checks=checks,
            failure_codes=failures, notified_at=previous.get('notified_at', 0),
            notification_status='not_needed' if not failures else 'disabled')
        if recipient and notification_due(previous, failures, now):
            try:
                notify(app_dir, recipient, failures)
                report.update(notification_status='smtp_accepted', notified_at=now)
            except Exception:
                report['notification_status'] = 'delivery_failed'
        temp = state_path.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2))
        temp.chmod(0o600)
        temp.replace(state_path)
        print(json.dumps(report))
        return bool(failures)


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-dir', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--recipient', default='')
    args = parser.parse_args()
    raise SystemExit(run(args.app_dir, args.state, args.recipient))
