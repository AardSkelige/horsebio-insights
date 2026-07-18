import threading
from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from sync.sync_task import SyncLockHeartbeat

from .models import SyncLock


class SyncLockTests(TestCase):
    lock_type = 'moysklad_sync'

    def test_fresh_lock_cannot_be_acquired_twice(self):
        token = SyncLock.acquire_lock(self.lock_type, locked_by='first')

        second_token = SyncLock.acquire_lock(self.lock_type, locked_by='second')

        self.assertIsNotNone(token)
        self.assertIsNone(second_token)

    def test_stale_owner_cannot_release_reacquired_lock(self):
        stale_token = SyncLock.acquire_lock(self.lock_type, locked_by='stale-worker')
        SyncLock.objects.filter(lock_type=self.lock_type).update(
            locked_at=timezone.now() - timedelta(minutes=61)
        )

        current_token = SyncLock.acquire_lock(self.lock_type, locked_by='current-worker')

        self.assertIsNotNone(current_token)
        self.assertNotEqual(stale_token, current_token)
        self.assertFalse(SyncLock.release_lock(self.lock_type, stale_token))

        lock = SyncLock.objects.get(lock_type=self.lock_type)
        self.assertTrue(lock.is_locked)
        self.assertEqual(str(lock.lock_token), current_token)

    def test_refresh_extends_lease_and_requires_owner_token(self):
        token = SyncLock.acquire_lock(self.lock_type, locked_by='worker')
        old_locked_at = timezone.now() - timedelta(minutes=59)
        SyncLock.objects.filter(lock_type=self.lock_type).update(locked_at=old_locked_at)

        self.assertFalse(SyncLock.refresh_lock(self.lock_type, '00000000-0000-0000-0000-000000000000'))
        self.assertTrue(SyncLock.refresh_lock(self.lock_type, token))

        lock = SyncLock.objects.get(lock_type=self.lock_type)
        self.assertGreater(lock.locked_at, old_locked_at)
        self.assertIsNone(
            SyncLock.acquire_lock(self.lock_type, locked_by='competitor', timeout_minutes=60)
        )

    @override_settings(SYNC_LOCK_HEARTBEAT_SECONDS=0.01)
    def test_heartbeat_periodically_refreshes_lock(self):
        refresh_called = threading.Event()
        task = Mock()

        def refresh_lock(lock_type, lock_token):
            refresh_called.set()
            return True

        with patch.object(SyncLock, 'refresh_lock', side_effect=refresh_lock):
            heartbeat = SyncLockHeartbeat(task, self.lock_type, 'owner-token')
            heartbeat.start()
            try:
                self.assertTrue(refresh_called.wait(timeout=1))
            finally:
                heartbeat.stop()

        task.stop.assert_not_called()

    @override_settings(SYNC_LOCK_HEARTBEAT_SECONDS=0.01)
    def test_heartbeat_stops_task_after_ownership_is_lost(self):
        task_stopped = threading.Event()
        task = Mock()
        task.stop.side_effect = task_stopped.set

        with patch.object(SyncLock, 'refresh_lock', return_value=False):
            heartbeat = SyncLockHeartbeat(task, self.lock_type, 'stale-token')
            heartbeat.start()
            try:
                self.assertTrue(task_stopped.wait(timeout=1))
            finally:
                heartbeat.stop()

        task.stop.assert_called_once_with()
