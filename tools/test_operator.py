"""Opt-in Codex operator for local synthetic review decisions only."""
import copy
import threading
import time
import uuid

try:
    from .codex_test_operator import choose, configuration_status
    from .situation_agent import DECISION_EFFECTS
except ImportError:
    from codex_test_operator import choose, configuration_status
    from situation_agent import DECISION_EFFECTS


class TestOperator:
    def __init__(self, simulation, runner=None, configuration=None):
        self.sim = simulation
        self.runner = runner or choose
        self.configuration = configuration or configuration_status
        self.active = self.applying = False
        self.status = 'idle'
        self.run_id = self.session_id = None
        self.max_decisions = 3
        self.decisions = []
        self.error = None
        self.worker = None
        self.cancelled = threading.Event()
        self.started = 0

    def snapshot(self):
        with self.sim.lock:
            return dict(active=self.active, status=self.status, run_id=self.run_id,
                        session_id=self.session_id, max_decisions=self.max_decisions,
                        completed=len(self.decisions), decisions=copy.deepcopy(self.decisions),
                        error=self.error, configuration=self.configuration())

    def cancel(self, status='stopped'):
        with self.sim.lock:
            if not self.active:
                return
            self.cancelled.set()
            self.active, self.status = False, status

    def command(self, command):
        with self.sim.lock:
            if command.get('run_id') != self.sim.run_id:
                raise ValueError('Stale run')
            if command.get('action') == 'stop':
                self.cancel()
                return self.snapshot()
            if command.get('action') != 'start' or command.get('confirm') is not True:
                raise ValueError('Explicit automated-test start is required')
            limit = command.get('max_decisions', 3)
            if type(limit) is not int or not 1 <= limit <= 10:
                raise ValueError('Decision limit must be 1 to 10')
            if self.active or (self.worker and self.worker.is_alive()):
                raise ValueError('A test operator is already running or stopping')
            if self.sim.test_run['mode'] != 'seeded':
                raise ValueError('Start a seeded simulation test first')
            if not self.configuration()['available']:
                raise ValueError('Codex CLI is not available')
            if not self.sim.decisions.enabled:
                raise ValueError('Enable important-event checkpoints first')
            if self.sim._time() >= self.sim.public[self.sim.case_id]['duration_ms']:
                raise ValueError('Start a new test before enabling the operator')
            self.run_id, self.session_id = self.sim.run_id, uuid.uuid4().hex
            self.max_decisions, self.decisions, self.error = limit, [], None
            self.cancelled = threading.Event()
            self.active, self.status, self.started = True, 'running', time.monotonic()
            events = self.sim.decisions.snapshot()['events']
            if not any(e['status'] in ('pending', 'evaluating', 'ready', 'failed') for e in events):
                self.applying = True
                try:
                    self.sim.control({'action': 'play'})
                finally:
                    self.applying = False
            return self.snapshot()

    def tick(self):
        with self.sim.lock:
            if not self.active:
                return
            if self.run_id != self.sim.run_id:
                self.cancel('run_changed')
                return
            if time.monotonic() - self.started > 600:
                self.cancel('time_limit')
                return
            if self.sim._time() >= self.sim.public[self.sim.case_id]['duration_ms']:
                self.cancel('completed')
                return
            if self.worker and self.worker.is_alive():
                return
            event = next((e for e in reversed(self.sim.decisions.snapshot()['events'])
                          if e['status'] in ('pending', 'evaluating', 'ready', 'failed')), None)
            if event is None or event['status'] in ('pending', 'evaluating'):
                return
            if event['status'] == 'failed':
                self.error = 'assessment_failed'
                self.cancel('failed')
                return
            # Only already displayed report fields and local choice effects enter Codex.
            report = event['report']
            context = dict(event_id=event['id'], run_id=event['run_id'], at_ms=event['at_ms'],
                           language=event['language'], test_run=copy.deepcopy(self.sim.test_run),
                           report={key: copy.deepcopy(report.get(key)) for key in
                                   ('summary', 'known', 'uncertain', 'review_items', 'decision_options', 'recommended_option_id')},
                           allowed_choices=copy.deepcopy(DECISION_EFFECTS))
            self.status = 'selecting'
            self.worker = threading.Thread(target=self._select, args=(event, context, self.session_id, self.cancelled), daemon=True)
            self.worker.start()

    def _select(self, event, context, session_id, cancelled):
        try:
            answer = self.runner(context, cancelled)
            if (not isinstance(answer, dict) or set(answer) != {'option_id', 'reason'}
                    or answer['option_id'] not in DECISION_EFFECTS
                    or not isinstance(answer['reason'], str) or not 1 <= len(answer['reason'].strip()) <= 1000):
                raise ValueError('Invalid operator answer')
            with self.sim.lock:
                if cancelled.is_set() or not self.active or self.session_id != session_id or self.sim.run_id != event['run_id']:
                    return
                current = next((e for e in self.sim.decisions.snapshot()['events'] if e['id'] == event['id']), None)
                if not current or current['status'] != 'ready' or current['evidence_version'] != event['evidence_version']:
                    self.cancel('evidence_changed')
                    return
                self.applying = True
                try:
                    self.sim.decisions._confirm(dict(action='confirm', run_id=event['run_id'], event_id=event['id'],
                        evidence_version=event['evidence_version'], option_id=answer['option_id'],
                        reviewer='Codex simulated operator', reason=answer['reason'], confirm=True),
                        actor=dict(type='automated_test', provider='codex_cli', model=self.configuration()['model'],
                                   session_id=session_id))
                finally:
                    self.applying = False
                self.decisions.append(dict(event_id=event['id'], at_ms=event['at_ms'],
                                           option_id=answer['option_id'], reason=answer['reason'], actor='automated_test'))
                self.status = 'running'
                if answer['option_id'] == 'hold_review':
                    self.cancel('held')
                elif len(self.decisions) >= self.max_decisions:
                    self.cancel('decision_limit')
        except Exception:
            with self.sim.lock:
                if self.active and self.session_id == session_id and not cancelled.is_set():
                    self.error = 'operator_failed'
                    self.cancel('failed')
