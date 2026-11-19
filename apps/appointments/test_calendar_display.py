from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from django.test import SimpleTestCase

from .calendar_display import calendar_phase


class CalendarDisplayTests(SimpleTestCase):
    def test_time_boundaries_and_attendance_are_independent(self):
        now = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)
        for start, end, status, expected in [
            (-60, 0, 'scheduled', 'past'),
            (-30, 20, 'scheduled', 'soon'),
            (1440, 1490, 'scheduled', 'soon'),
            (1441, 1491, 'scheduled', 'future'),
            (-60, -10, 'cancelled', 'cancelled'),
            (-60, -10, 'no_show', 'no_show'),
        ]:
            with self.subTest(start=start, status=status):
                session = SimpleNamespace(starts_at=now + timedelta(minutes=start),
                    ends_at=now + timedelta(minutes=end), status=status)
                self.assertEqual(calendar_phase(session, now), expected)
                self.assertEqual(session.status, status)
