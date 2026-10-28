"""Synthetic scenario phases. Runs only in a dedicated offline *_rehearsal DB.

This module is deliberately NOT a production erasure command.
"""
import hashlib
import json
import os
from pathlib import Path
import time


def initialize():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.conf import settings
    from django.db import connection
    from ops.rehearsal import validate_rehearsal
    name = connection.settings_dict['NAME']
    settings.MIGRATION_REHEARSAL = os.environ.get('OPS_SYNTHETIC_DRILL') == '1'
    validate_rehearsal(settings, name, settings.MIGRATION_REHEARSAL)
    if not name.startswith('nuviamy_ops_drill_') or connection.vendor != 'postgresql':
        raise ValueError('This exercise requires its dedicated synthetic PostgreSQL database.')
    root = Path('/evidence')
    if not root.is_dir():
        raise ValueError('A dedicated evidence mount is required.')
    settings.MEDIA_ROOT = root / 'media'
    settings.MEDIA_ROOT.mkdir(exist_ok=True, mode=0o700)
    return root


def write(root, name, value):
    path = root / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(value, output, sort_keys=True, indent=2)


def inventory(root):
    from apps.clients.models import Client
    return {'client_public_ids': [str(value) for value in Client.objects.values_list('public_id', flat=True)],
            'storage_keys': [path.name for path in (root / 'media').iterdir() if path.is_file()]}


def seed(root):
    from django.contrib.auth import get_user_model
    from apps.accounts.models import UserProfile
    from apps.practices.models import Practice, TherapistProfile
    from apps.clients.models import Client
    from apps.clinical.models import SessionNote
    from apps.documents.models import ClientDocument
    if Client.objects.exists() or get_user_model().objects.exists():
        raise ValueError('Seed refuses a nonempty database.')
    practice = Practice.objects.create(name='SYNTHETIC OPS DRILL')
    owner = get_user_model().objects.create_user('synthetic-drill-owner', email='drill@example.invalid')
    UserProfile.objects.create(user=owner, practice=practice, role='owner')
    therapist = TherapistProfile.objects.create(user=owner, practice=practice,
        license_number='SYNTHETIC-DRILL', license_state='CA')
    deleted = Client.objects.create(practice=practice, first_name='SYNTHETIC', last_name='DISPOSITION')
    held = Client.objects.create(practice=practice, first_name='SYNTHETIC', last_name='PRESERVATION')
    SessionNote.objects.create(practice=practice, client=held, therapist=therapist,
        content='Synthetic preserved record; not a patient record.')
    body = b'SYNTHETIC OPERATIONAL DRILL ONLY - document revision two. No patient or customer data.\n'
    (root / 'media' / 'synthetic-document.txt').write_bytes(body)
    ClientDocument.objects.create(practice=practice, client=deleted, title='SYNTHETIC DOCUMENT',
        file='synthetic-document.txt', file_size=len(body))
    from apps.dashboard.models import SupportTicket, SupportMessage
    ticket = SupportTicket.objects.create(practice=practice, requester=owner, contact_email=owner.email, topic='technical')
    SupportMessage.objects.create(ticket=ticket, body='Synthetic encrypted support recovery check')
    write(root, 'fixture.json', {'support_digest': hashlib.sha256(b'Synthetic encrypted support recovery check').hexdigest(), 'disposed_client': str(deleted.public_id), 'held_client': str(held.public_id),
        'document_sha256': hashlib.sha256(body).hexdigest()})
    return {'synthetic_clients': 2, 'documents': 1, 'production_modified': False}


def dispose(root):
    from django.utils import timezone
    from apps.clients.models import Client
    from apps.audit.models import AuditLog
    from ops.disposition_gate import require_authority, DispositionError, sign_ledger, canonical
    fixture = json.loads((root / 'fixture.json').read_text())
    case = {'case_reference': 'SYNTHETIC-DISPOSITION-001', 'authority_verified': True,
        'holds_clear': True, 'disposition_authorized': True, 'effective_at': timezone.now().isoformat(),
        'client_public_ids': [fixture['disposed_client']], 'storage_keys': ['synthetic-document.txt']}
    try:
        require_authority(dict(case, holds_clear=False))
    except DispositionError:
        pass
    else:
        raise AssertionError('A preservation hold was bypassed.')
    require_authority(case)
    client = Client.objects.get(public_id=fixture['disposed_client'])
    assert client.first_name == 'SYNTHETIC' and client.practice.name == 'SYNTHETIC OPS DRILL'
    practice = client.practice
    client.delete()
    (root / 'media' / 'synthetic-document.txt').unlink()
    assert Client.objects.filter(public_id=fixture['held_client']).exists()
    AuditLog.objects.create(practice=practice, action='delete', object_type='synthetic.Disposition',
                            metadata={'case': case['case_reference'], 'synthetic': True})
    payload = {'format': 1, 'cases': [case]}
    key = (root / 'independent-ledger.key').read_bytes()
    write(root, 'disposition-ledger.json', sign_ledger(payload, key))
    head = hashlib.sha256(canonical(payload)).hexdigest()
    (root / 'independent-current-ledger.sha256').write_text(head)
    write(root, 'post-disposition-inventory.json', inventory(root))
    return {'held_client_preserved': True, 'hold_rejected': True, 'active_fixture_erased': True,
            'ledger_outside_backup': True, 'production_modified': False}


def verify_restored(root, reconcile=False):
    from apps.clients.models import Client
    from ops.disposition_gate import check_restore, verify_ledger
    fixture = json.loads((root / 'fixture.json').read_text())
    if fixture.get('support_digest'):
        from apps.dashboard.models import SupportMessage
        value = SupportMessage.objects.get().body
        assert hashlib.sha256(value.encode()).hexdigest() == fixture['support_digest']
    envelope = json.loads((root / 'disposition-ledger.json').read_text())
    key = (root / 'independent-ledger.key').read_bytes()
    head = (root / 'independent-current-ledger.sha256').read_text()
    before = check_restore(envelope, key, inventory(root), head)
    if not reconcile:
        assert not before['activation_allowed'] and before['blocked_clients'] == 1
        assert Client.objects.filter(public_id=fixture['held_client']).exists()
        write(root, 'restored-gate-blocked.json', before)
        return before
    payload = verify_ledger(envelope, key)
    for case in payload['cases']:
        for public_id in case['client_public_ids']:
            client = Client.objects.get(public_id=public_id)
            assert client.first_name == 'SYNTHETIC' and client.practice.name == 'SYNTHETIC OPS DRILL'
            client.delete()
        for name in case['storage_keys']:
            if name != 'synthetic-document.txt':
                raise ValueError('Unexpected synthetic fixture path.')
            (root / 'media' / name).unlink(missing_ok=True)
    from ops.rehearsal import clear_restored_integrations
    clear_restored_integrations()
    after = check_restore(envelope, key, inventory(root), head)
    assert after['activation_allowed'] and Client.objects.filter(public_id=fixture['held_client']).exists()
    write(root, 'restored-gate-reconciled.json', after)
    return {'reconciled_gate': after, 'held_client_preserved': True, 'restored_sessions_cleared': True}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['seed', 'dispose', 'verify-restored', 'reconcile-restored'])
    args = parser.parse_args()
    started = time.monotonic()
    root = initialize()
    actions = {'seed': seed, 'dispose': dispose, 'verify-restored': verify_restored,
               'reconcile-restored': lambda root: verify_restored(root, reconcile=True)}
    result = actions[args.phase](root)
    result['phase_seconds'] = round(time.monotonic() - started, 3)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
