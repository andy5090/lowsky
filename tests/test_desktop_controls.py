import concurrent.futures
import unittest

from tools.desktop_controls import DesktopBusy, DesktopControls


class DesktopControlsTests(unittest.TestCase):
    def setUp(self):
        self.commands = []
        self.controls = DesktopControls(self.commands.append)

    def ack(self, ok=True, **extra):
        return self.controls.acknowledge(dict(id=self.commands[-1]['id'], ok=ok, **extra))

    def test_native_ack_is_the_only_state_commit(self):
        before = self.controls.snapshot()
        pending = self.controls.command({'action': 'toggle_fullscreen'})
        self.assertTrue(pending['pending'])
        self.assertFalse(pending['fullscreen'])
        self.assertEqual(pending['revision'], 0)
        self.assertTrue(self.commands[-1]['state']['fullscreen'])
        self.assertEqual(self.commands[-1]['event'], 'desktop_command')
        done = self.ack()
        self.assertTrue(done['fullscreen'])
        self.assertFalse(done['pending'])
        self.assertEqual(done['revision'], 1)
        self.controls.command({'action': 'toggle_fullscreen'})
        self.assertFalse(self.ack()['fullscreen'])
        self.assertFalse(before['fullscreen'])

    def test_open_close_and_monitor_switch(self):
        for action, view, opened in [('close_3d', 'monitor', False), ('open_3d', '3d', True),
                                     ('show_monitor', 'monitor', True), ('open_3d', '3d', True)]:
            self.controls.command({'action': action})
            state = self.ack()
            self.assertEqual((state['view'], state['three_d_open']), (view, opened))

    def test_explicit_fullscreen_target_overrides_stale_focus(self):
        self.controls.command({'action': 'toggle_monitor_fullscreen'})
        self.assertEqual(self.controls.snapshot()['view'], '3d')
        monitor = self.ack()
        self.assertEqual((monitor['view'], monitor['fullscreen']), ('monitor', True))
        self.controls.command({'action': 'toggle_3d_fullscreen'})
        three_d = self.ack()
        self.assertEqual((three_d['view'], three_d['fullscreen']), ('3d', False))
        self.controls.command({'action': 'close_3d'})
        self.ack()
        self.controls.command({'action': 'toggle_3d_fullscreen'})
        reopened = self.ack()
        self.assertEqual((reopened['view'], reopened['three_d_open'], reopened['fullscreen']), ('3d', True, True))

    def test_failed_emit_or_ack_preserves_prior_window_state_and_hides_private_errors(self):
        self.controls.command({'action': 'close_3d'})
        failed = self.ack(False, error='private /path SECRET')
        self.assertTrue(failed['three_d_open'])
        self.assertFalse(failed['pending'])
        self.assertEqual(failed['revision'], 0)
        self.assertNotIn('SECRET', str(failed))
        self.controls.command({'action': 'show_monitor'})
        self.assertIsNone(self.ack()['error'])
        def broken(_):
            raise OSError('SECRET')
        controls = DesktopControls(broken)
        with self.assertRaises(DesktopBusy):
            controls.command({'action': 'close_3d'})
        self.assertTrue(controls.snapshot()['three_d_open'])
        self.assertFalse(controls.snapshot()['pending'])
        self.assertNotIn('SECRET', str(controls.snapshot()))

    def test_concurrent_commands_and_stale_ack_do_not_change_pending(self):
        def issue(_):
            try:
                self.controls.command({'action': 'toggle_fullscreen'})
                return True
            except DesktopBusy:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(issue, range(16))), 1)
        with self.assertRaises(DesktopBusy):
            self.controls.acknowledge({'id': 'wrong', 'ok': True})
        self.assertTrue(self.controls.snapshot()['pending'])
        self.ack()
        with self.assertRaises(DesktopBusy):
            self.ack()

    def test_close_notification_is_idempotent_and_does_not_clobber_command(self):
        self.controls.command({'action': 'toggle_fullscreen'})
        with self.assertRaises(DesktopBusy):
            self.controls.acknowledge({'event': 'godot_closed'})
        self.ack()
        closed = self.controls.acknowledge({'event': 'godot_closed'})
        self.assertEqual((closed['three_d_open'], closed['view'], closed['revision']), (False, 'monitor', 2))
        self.assertEqual(self.controls.acknowledge({'event': 'godot_closed'}), closed)

    def test_validation_and_unavailable_browser(self):
        for body in ({}, {'action': 'exec'}, {'action': 'open_3d', 'path': 'anything'}):
            with self.assertRaises(ValueError):
                self.controls.command(body)
        self.controls.command({'action': 'show_monitor'})
        for body in ({'ok': True}, {'id': self.commands[0]['id'], 'ok': 1},
                     {'id': self.commands[0]['id'], 'ok': False, 'error': {}}):
            with self.assertRaises(ValueError):
                self.controls.acknowledge(body)
        browser = DesktopControls()
        self.assertFalse(browser.snapshot()['available'])
        self.assertIsNone(browser.runtime_token)
        self.assertFalse(browser.authenticated(''))
        with self.assertRaises(DesktopBusy):
            browser.command({'action': 'open_3d'})
        self.assertTrue(self.controls.authenticated(self.controls.runtime_token))
        self.assertFalse(self.controls.authenticated('wrong'))
        self.assertFalse(self.controls.authenticated(None))
        self.assertNotIn(self.controls.runtime_token, str(self.controls.snapshot()))


if __name__ == '__main__':
    unittest.main()
