"""Small native-window command relay, separate from simulation and evidence."""
import secrets
import threading


class DesktopBusy(ValueError):
    pass


class DesktopControls:
    ACTIONS = ('open_3d', 'close_3d', 'show_monitor', 'toggle_fullscreen',
               'toggle_monitor_fullscreen', 'toggle_3d_fullscreen')

    def __init__(self, emit=None):
        self._emit = emit
        self._token = secrets.token_urlsafe(32) if emit else None
        self._lock = threading.RLock()
        self._pending = None
        self._state = dict(available=emit is not None, view='3d' if emit else 'monitor',
                           fullscreen=False, three_d_open=emit is not None,
                           pending=False, error=None, revision=0)

    @property
    def runtime_token(self):
        """For the inherited native stdout pipe only; never part of state."""
        return self._token

    def authenticated(self, token):
        return bool(self._token and isinstance(token, str)
                    and secrets.compare_digest(self._token.encode(), token.encode()))

    def snapshot(self):
        with self._lock:
            return self._state.copy()

    def command(self, body):
        action = body.get('action')
        if action not in self.ACTIONS or set(body) != {'action'}:
            raise ValueError('Unknown desktop action')
        with self._lock:
            if self._emit is None:
                raise DesktopBusy('Desktop controls are unavailable in the browser')
            if self._pending:
                raise DesktopBusy('A desktop command is pending')
            desired = {key: self._state[key] for key in ('view', 'fullscreen', 'three_d_open')}
            if action == 'open_3d':
                desired.update(view='3d', three_d_open=True)
            elif action == 'close_3d':
                desired.update(view='monitor', three_d_open=False)
            elif action == 'show_monitor':
                desired['view'] = 'monitor'
            else:
                desired['fullscreen'] = not desired['fullscreen']
                if action == 'toggle_monitor_fullscreen':
                    desired['view'] = 'monitor'
                elif action == 'toggle_3d_fullscreen':
                    desired.update(view='3d', three_d_open=True)
            command = dict(event='desktop_command', id=secrets.token_urlsafe(18), action=action, state=desired)
            self._pending = command
            self._state.update(pending=True, error=None)
            try:
                self._emit(command)
            except Exception:
                self._pending = None
                self._state.update(pending=False, error='Native window command could not be delivered')
                raise DesktopBusy(self._state['error']) from None
            return self.snapshot()

    def acknowledge(self, body):
        with self._lock:
            if body.get('event') == 'godot_closed' and set(body) == {'event'}:
                if self._pending:
                    raise DesktopBusy('A desktop command is pending; retry the close notification')
                if self._state['three_d_open'] or self._state['view'] != 'monitor':
                    self._state.update(three_d_open=False, view='monitor', error=None,
                                       revision=self._state['revision'] + 1)
                return self.snapshot()
            if set(body) - {'id', 'ok', 'error'} or not isinstance(body.get('id'), str) or type(body.get('ok')) is not bool:
                raise ValueError('Expected a native command acknowledgement')
            if 'error' in body and not isinstance(body['error'], str):
                raise ValueError('Expected a text error')
            if not self._pending or body['id'] != self._pending['id']:
                raise DesktopBusy('No matching pending desktop command')
            if body['ok']:
                self._state.update(self._pending['state'])
                self._state.update(revision=self._state['revision'] + 1, error=None)
            else:
                # Do not relay paths, subprocess output, or credentials from native errors.
                self._state['error'] = 'Native window command failed'
            self._pending = None
            self._state['pending'] = False
            return self.snapshot()
