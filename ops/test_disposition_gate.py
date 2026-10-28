import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from ops.disposition_gate import DispositionError, require_authority, sign_ledger, check_restore, read_json, canonical


class DispositionGateTests(unittest.TestCase):
    def setUp(self):
        self.key = b'synthetic-disposition-signing-key-42'
        self.case = {'case_reference':'SYNTHETIC-001','authority_verified':True,'holds_clear':True,
            'disposition_authorized':True,'effective_at':'2026-10-28T00:00:00Z',
            'client_public_ids':['11111111-1111-4111-8111-111111111111'],
            'storage_keys':['synthetic/document']}
        self.payload={'format':1,'cases':[self.case]}
        self.envelope=sign_ledger(self.payload,self.key)
        self.head=hashlib.sha256(canonical(self.payload)).hexdigest()

    def test_restored_deleted_client_or_file_blocks_activation(self):
        for clients,files in [(self.case['client_public_ids'],[]),([],self.case['storage_keys'])]:
            report=check_restore(self.envelope,self.key,{'client_public_ids':clients,'storage_keys':files},self.head)
            self.assertFalse(report['activation_allowed'])
            self.assertNotIn('11111111',json.dumps(report))
            self.assertNotIn('synthetic/document',json.dumps(report))

    def test_reconciled_inventory_can_pass(self):
        self.assertTrue(check_restore(self.envelope,self.key,{'client_public_ids':[], 'storage_keys':[]},self.head)['activation_allowed'])

    def test_hold_unknown_authority_and_unsigned_or_changed_ledger_fail_closed(self):
        for field in ('authority_verified','holds_clear','disposition_authorized'):
            for value in (False,None,'true'):
                with self.subTest(field=field,value=value),self.assertRaises(DispositionError):
                    require_authority(dict(self.case,**{field:value}))
        for envelope,key in [(None,self.key),(self.envelope,b'wrong-signing-key-of-sufficient-length')]:
            with self.assertRaises(DispositionError):
                check_restore(envelope,key,{'client_public_ids':[], 'storage_keys':[]},self.head)
        modified=copy.deepcopy(self.envelope)
        modified['payload']['cases']=[]
        with self.assertRaises(DispositionError):
            check_restore(modified,self.key,{'client_public_ids':[], 'storage_keys':[]},self.head)

    def test_duplicate_json_fields_rejected(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'duplicate.json'
            path.write_text('{"format":1,"format":2}')
            with self.assertRaises(DispositionError):read_json(path)

    def test_previously_valid_but_stale_signed_ledger_is_rejected(self):
        stale=sign_ledger({'format':1,'cases':[]},self.key)
        with self.assertRaises(DispositionError):
            check_restore(stale,self.key,{'client_public_ids':[], 'storage_keys':[]},self.head)
