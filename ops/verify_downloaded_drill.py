"""Replay a synthetic S3-downloaded backup in a NEW offline PostgreSQL container."""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from cryptography.fernet import Fernet
from dotenv import dotenv_values
from ops.run_operational_drill import checked, private_write


def run(image, original, downloaded):
    if original.stat().st_mode & 0o077 or downloaded.stat().st_size>16*1024*1024:
        raise ValueError('Use private bounded synthetic evidence.')
    source=json.loads((original/'report.json').read_text())
    ciphertext=downloaded.read_bytes()
    if source.get('synthetic_only') is not True or hashlib.sha256(ciphertext).hexdigest()!=source['backup_ciphertext_sha256']:
        raise ValueError('Downloaded ciphertext does not match the independently recorded synthetic backup.')
    config=dotenv_values(original/'restored-application.env',interpolate=False)
    if config.get('OPS_SYNTHETIC_DRILL')!='1' or not config['POSTGRES_DB'].startswith('nuviamy_ops_drill_'):
        raise ValueError('This tool cannot replay a production configuration.')
    suffix=uuid.uuid4().hex[:12]
    root=original.parent/('s3-restoration-'+suffix);root.mkdir(mode=0o700)
    socket=root/'pgsocket';socket.mkdir(mode=0o777);socket.chmod(0o777)
    for name in ['fixture.json','independent-ledger.key','disposition-ledger.json','independent-current-ledger.sha256']:
        private_write(root/name,(original/name).read_bytes())
    private_write(root/'postgres.env',f"POSTGRES_DB={config['POSTGRES_DB']}\nPOSTGRES_USER=postgres\nPOSTGRES_PASSWORD={config['POSTGRES_PASSWORD']}\n".encode())
    config['OPS_DRILL_REPORT_DIR']='/evidence'
    private_write(root/'application.env',''.join(k+'='+v+'\n' for k,v in config.items()).encode())
    payload=json.loads(Fernet((original/'synthetic-backup.key').read_bytes()).decrypt(ciphertext))
    (root/'media').mkdir(mode=0o700)
    (root/'media'/'synthetic-document.txt').write_bytes(base64.b64decode(payload['document']))
    pg='nuviamy-s3-drill-'+suffix
    ops=Path(__file__).resolve().parent
    started=time.monotonic();created=False
    def app(args):
        return checked(['docker','run','--rm','--user',f'{os.getuid()}:{os.getgid()}',
            '--network','none','--read-only','--tmpfs','/tmp',
            '--mount',f'type=bind,src={socket},dst=/pgsocket',
            '--mount',f'type=bind,src={root},dst=/evidence',
            '--mount',f'type=bind,src={ops},dst=/app/ops,readonly',
            '--env-file',str(root/'application.env'),image,*args])
    try:
        checked(['docker','run','-d','--rm','--network','none','--name',pg,
            '--label','nuviamy.synthetic.drill=1','--env-file',str(root/'postgres.env'),
            '--mount',f'type=bind,src={socket},dst=/var/run/postgresql','postgres:16-alpine'])
        created=True
        for _ in range(60):
            if subprocess.run(['docker','exec',pg,'pg_isready','-U','postgres'],capture_output=True).returncode==0:break
            time.sleep(1)
        else:raise RuntimeError('Isolated PostgreSQL did not become ready.')
        checked(['docker','exec','-i',pg,'pg_restore','-U','postgres','--no-owner','--exit-on-error',
            '-d',config['POSTGRES_DB']],input=base64.b64decode(payload['database']))
        blocked=json.loads(app(['python','-m','ops.drill_scenario','verify-restored']))
        reconciled=json.loads(app(['python','-m','ops.drill_scenario','reconcile-restored']))
        app(['python','manage.py','test','apps.accounts.test_operational_drills','--noinput'])
        result={'synthetic_only':True,'source':'console-downloaded S3 ciphertext',
            'ciphertext_sha256':hashlib.sha256(ciphertext).hexdigest(),
            'restored_gate_blocked':blocked,'after_reconciliation':reconciled,
            'http_and_incident_tests':'passed','production_modified':False,
            'completed_at':datetime.now(timezone.utc).isoformat(),
            'seconds':round(time.monotonic()-started,3)}
        private_write(root/'report.json',json.dumps(result,sort_keys=True,indent=2).encode())
        print(json.dumps({'result':'passed','evidence_directory':str(root),'seconds':result['seconds']}))
    finally:
        if created:subprocess.run(['docker','rm','-f','-v',pg],capture_output=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True)
    parser.add_argument('--original-evidence',type=Path,required=True)
    parser.add_argument('--downloaded-backup',type=Path,required=True)
    args=parser.parse_args()
    run(args.image,args.original_evidence,args.downloaded_backup)
