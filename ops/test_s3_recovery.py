from datetime import datetime, timedelta, timezone
import unittest

from ops.verify_s3_recovery import newest_backup


class RecoverySelectionTests(unittest.TestCase):
    def test_selects_latest_encrypted_dump_ignoring_probe_objects(self):
        now = datetime.now(timezone.utc)
        objects = [dict(Key='postgres/probe.json', Size=2, LastModified=now),
                   dict(Key='postgres/old.dump.gpg', Size=100, LastModified=now-timedelta(hours=25)),
                   dict(Key='postgres/latest.dump.gpg', Size=100, LastModified=now-timedelta(hours=1))]
        self.assertEqual(newest_backup(objects, now)['Key'], 'postgres/latest.dump.gpg')

    def test_rejects_missing_future_stale_empty_and_oversized_backups(self):
        now = datetime.now(timezone.utc)
        for size, hours in [(0, 1), (1024**3+1, 1), (1, -1), (1, 27)]:
            with self.subTest(size=size, hours=hours), self.assertRaises(ValueError):
                newest_backup([dict(Key='a.dump.gpg', Size=size, LastModified=now-timedelta(hours=hours))], now)
        with self.assertRaises(ValueError):
            newest_backup([], now)
