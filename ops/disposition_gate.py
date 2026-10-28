"""Fail-closed, read-only gate for a restored inventory and an external disposition ledger.

Never erases records or enables a service. Effective instructions, the latest-ledger digest and the MAC key must be
kept outside the backup being restored. Identifiers belong in private evidence.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
from uuid import UUID


class DispositionError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def require_authority(case):
    if not isinstance(case, dict):
        raise DispositionError('Invalid disposition authority review.')
    if (case.get('authority_verified') is not True or case.get('holds_clear') is not True
            or case.get('disposition_authorized') is not True):
        raise DispositionError('Disposition is not authorized or preservation review is incomplete.')


def validate_ledger(payload):
    if not isinstance(payload, dict) or (type(payload.get('format')) is not int or payload.get('format') != 1) or not isinstance(payload.get('cases'), list):
        raise DispositionError('Invalid disposition ledger.')
    refs = set()
    for case in payload['cases']:
        if not isinstance(case, dict):
            raise DispositionError('Invalid disposition case.')
        require_authority(case)
        ref = case.get('case_reference')
        if not isinstance(ref, str) or not ref or len(ref) > 100 or ref in refs:
            raise DispositionError('Invalid case reference.')
        refs.add(ref)
        if not isinstance(case.get('effective_at'), str) or not case['effective_at']:
            raise DispositionError('An effective disposition instruction must be recorded.')
        if not isinstance(case.get('client_public_ids'), list) or not isinstance(case.get('storage_keys'), list):
            raise DispositionError('Invalid disposition identifiers.')
        for value in case['client_public_ids']:
            if not isinstance(value, str) or str(UUID(value)) != value:
                raise DispositionError('Invalid client identifier.')
        for value in case['storage_keys']:
            if not isinstance(value, str) or not value or len(value) > 1024:
                raise DispositionError('Invalid storage identifier.')
    return payload


def sign_ledger(payload, key):
    validate_ledger(payload)
    if not isinstance(key, bytes) or len(key) < 32:
        raise DispositionError('An independent signing key is required.')
    return {'payload': payload, 'hmac_sha256': hmac.new(key, canonical(payload), hashlib.sha256).hexdigest()}


def verify_ledger(envelope, key):
    if not isinstance(envelope, dict) or set(envelope) != {'payload', 'hmac_sha256'}:
        raise DispositionError('Missing or invalid signed disposition ledger.')
    expected = sign_ledger(envelope['payload'], key)['hmac_sha256']
    signature = envelope['hmac_sha256']
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        raise DispositionError('Disposition ledger authentication failed.')
    return envelope['payload']


def check_restore(envelope, key, inventory, expected_ledger_sha256):
    payload = verify_ledger(envelope, key)
    current_digest = hashlib.sha256(canonical(payload)).hexdigest()
    if not isinstance(expected_ledger_sha256, str) or not hmac.compare_digest(current_digest, expected_ledger_sha256):
        raise DispositionError('Latest independent ledger digest does not match.')
    if (not isinstance(inventory, dict) or set(inventory) != {'client_public_ids', 'storage_keys'}
            or not all(isinstance(inventory.get(k), list) for k in inventory)):
        raise DispositionError('Invalid restored inventory.')
    if any(not isinstance(value, str) for values in inventory.values() for value in values):
        raise DispositionError('Invalid restored identifier.')
    clients, files, cases = set(), set(), []
    for case in payload['cases']:
        found_clients = set(case['client_public_ids']) & set(inventory['client_public_ids'])
        found_files = set(case['storage_keys']) & set(inventory['storage_keys'])
        if found_clients or found_files:
            cases.append(case['case_reference'])
            clients.update(found_clients)
            files.update(found_files)
    return {'activation_allowed': not (clients or files), 'blocked_clients': len(clients),
            'blocked_files': len(files), 'matched_case_references': cases,
            'ledger_sha256': hashlib.sha256(canonical(payload)).hexdigest(),
            'inventory_sha256': hashlib.sha256(canonical(inventory)).hexdigest()}


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise DispositionError('Duplicate JSON field.')
            result[key] = value
        return result
    if path.stat().st_size > 16 * 1024 * 1024:
        raise DispositionError('Inventory exceeds the bounded gate capacity.')
    return json.loads(path.read_text(), object_pairs_hook=unique)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--key-file', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--expected-ledger-sha256', required=True, help='Read the latest digest from the independent current register, never from the restored backup.')
    args = parser.parse_args()
    try:
        if args.key_file.stat().st_mode & 0o077:
            raise DispositionError('Signing key permissions must be private.')
        if args.key_file.stat().st_size > 4096:
            raise DispositionError('Invalid signing key file.')
        key = args.key_file.read_bytes()
        result = check_restore(read_json(args.ledger), key, read_json(args.inventory), args.expected_ledger_sha256)
    except (ValueError, TypeError, OSError):
        print(json.dumps({'activation_allowed': False, 'error': 'restore_review_required'}))
        raise SystemExit(2)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result['activation_allowed'] else 1)


if __name__ == '__main__':
    main()
