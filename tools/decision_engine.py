"""Event-driven, received-evidence review gates for a synthetic replay.

All effects are local replay/review actions. Model prose never authorizes effects.
"""
import copy
import json
import os
import threading
import time
import uuid
from pathlib import Path

try:
    from .evidence_review import digest
    from .situation_agent import build_bundle
except ImportError:
    from evidence_review import digest
    from situation_agent import build_bundle

OPTIONS = (
    {'id': 'continue_monitoring', 'effect': 'resume'},
    {'id': 'hold_review', 'effect': 'pause'},
    {'id': 'defer', 'effect': 'resume_with_further_review'},
)
ACTIVE = ('pending', 'evaluating', 'ready', 'failed')


class DecisionBusy(ValueError):
    pass


class DecisionAudit:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self.records = []
        if self.path is not None and self.path.exists():
            content = self.path.read_text(encoding='utf-8')
            if content and not content.endswith('\n'):
                raise ValueError('Incomplete decision audit record')
            for line in content.splitlines():
                row = json.loads(line)
                if (not isinstance(row, dict) or row.get('schema_version') != 1
                        or row.get('kind') != 'event_decision'
                        or digest(row.get('snapshot')) != row.get('snapshot_hash')
                        or not all(k in row for k in ('id', 'run_id', 'case_id', 'event_id', 'option_id',
                                                     'reviewer', 'reason', 'decided_at_unix_ms'))):
                    raise ValueError('Invalid decision audit record')
                self.records.append(row)

    def append(self, row):
        saved = copy.deepcopy(row)
        content = json.dumps(saved, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n'
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a', encoding='utf-8') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        self.records.append(saved)

    def export(self):
        return {'schema_version': 1, 'records': copy.deepcopy(self.records)}


def semantic_state(bundle):
    """Heartbeat IDs/count increments are evidence changes, not interrupt triggers."""
    obs = bundle['observations']
    state = {('first_tracks', 'received_tracks'): (bool(obs['total']), [obs['id']]),
             ('track_conflict', 'received_tracks'): (bool(obs['by_quality']['contradictory']), [obs['id']]),
             ('track_stale', 'received_tracks'): (bool(obs['last_known']), [obs['id']])}
    for source in bundle['sources']:
        state[('source_health', source['source_id'])] = (source['status'],
                                                       [source['evidence_id']] if source['evidence_id'] else [obs['id']])
    for group in bundle['fleet']:
        counts = group['counts']
        status = 'lost' if counts['offline'] + counts['stale'] else 'online' if counts['online'] else 'waiting'
        state[('fleet_health', group['group_id'])] = (status, [group['id']])
    for zone in bundle['early_signals']:
        positive, negative = zone['positive_sources'], zone['negative_sources']
        status = ('conflicting' if positive and negative else 'corroborated' if positive >= 2 else
                  'single' if positive else 'no_current_positive')
        state[('early_signal', zone['zone_id'])] = (status, [zone['id']])
    return state


def transitions(previous, current):
    result = []
    for (kind, subject), (value, evidence) in current.items():
        before = previous.get((kind, subject), (None, []))[0]
        if before == value:
            continue
        if kind == 'first_tracks' and not value:
            continue
        if (kind in ('source_health', 'fleet_health') and before in (None, 'unknown', 'waiting')
                and value in ('online', 'unknown', 'waiting')):
            continue
        if kind == 'early_signal' and value == 'no_current_positive' and before in (None, 'no_current_positive'):
            continue
        if kind in ('track_conflict', 'track_stale') and before is None and not value:
            continue
        result.append(dict(kind=kind, subject=subject, previous=before, current=value,
                           evidence_ids=list(evidence)))
    return result


class DecisionEngine:
    def __init__(self, simulation, evaluator=None, audit_path=None):
        self.sim = simulation
        self.evaluator = evaluator
        self.audit = DecisionAudit(audit_path)
        self.enabled, self.language = True, 'en'
        self.events = []
        self.previous = None
        self.previous_run = None
        self.worker = None
        self.stopping = threading.Event()
        self.scheduler = None

    def _bundle(self):
        return build_bundle(self.sim.state())

    def _reconcile(self, bundle):
        for event in self.events:
            if event['status'] in ACTIVE and (event['run_id'] != bundle['run_id']
                    or event['evidence_version'] != bundle['input_version']):
                event['status'] = 'superseded'
                event.pop('_frozen', None)
        if bundle['run_id'] != self.previous_run:
            self.previous_run = bundle['run_id']
            self.previous = semantic_state(bundle)

    def observe_control(self):
        """Record reset/seek baselines and invalidate frozen cards synchronously."""
        self._reconcile(self._bundle())

    def snapshot(self):
        with self.sim.lock:
            self._reconcile(self._bundle())
            events = [{k: copy.deepcopy(v) for k, v in event.items() if k != '_frozen'}
                      for event in reversed(self.events)]
            history = [{k: copy.deepcopy(v) for k, v in row.items() if k != 'snapshot'}
                       for row in reversed(self.audit.records) if row['run_id'] == self.sim.run_id]
            return dict(run_id=self.sim.run_id, enabled=self.enabled, language=self.language,
                        events=events, history=history, options=copy.deepcopy(OPTIONS),
                        configuration=self.sim.assessment_configuration())

    def start(self):
        with self.sim.lock:
            if self.scheduler and self.scheduler.is_alive():
                return
            self.stopping.clear()
            self.observe_control()
            self.scheduler = threading.Thread(target=self._loop, name='decision-events', daemon=True)
            self.scheduler.start()

    def stop(self):
        self.stopping.set()
        self.sim.test_operator.cancel('stopped')
        if self.scheduler and self.scheduler is not threading.current_thread():
            self.scheduler.join(timeout=2)
        # Provider work is bounded by its adapter; stop invalidates late results.

    def _loop(self):
        while not self.stopping.wait(.25):
            try:
                self.tick()
                self.sim.test_operator.tick()
            except Exception:
                # Do not terminate replay or leak provider/private data into server logs.
                pass

    def tick(self):
        with self.sim.lock:
            if not self.enabled or not self.sim._clock_state()['playing']:
                return
            state = self.sim.state()
            bundle = build_bundle(state)
            self._reconcile(bundle)
            if not self.enabled or not state['playing']:
                return
            current = semantic_state(bundle)
            changes = transitions(self.previous or {}, current)
            if changes:
                self._capture(state, bundle, changes, self.language, queue_if_busy=True)
            else:
                self.previous = current

    def _capture(self, state, bundle, triggers, language, queue_if_busy=False):
        busy = bool(self.worker and self.worker.is_alive())
        if busy and not queue_if_busy:
            raise DecisionBusy('An event assessment is already running')
        for event in self.events:
            if event['status'] in ACTIVE:
                event['status'] = 'superseded'
                event.pop('_frozen', None)
        # Anchor to exactly the captured input, including when a tick consumed time.
        self.sim.anchor_ms, self.sim.anchor_wall = state['at_ms'], self.sim.clock()
        self.sim.playing = False
        self.sim.revision += 1
        event = dict(id=uuid.uuid4().hex, run_id=state['run_id'], case_id=state['case_id'],
                     at_ms=state['at_ms'], evidence_version=bundle['input_version'],
                     triggers=copy.deepcopy(triggers), status='pending', language=language,
                     report=None, error=None, decision=None,
                     created_at_unix_ms=int(time.time() * 1000), _frozen=copy.deepcopy(state))
        self.events.append(event)
        # Keep current review cards bounded; confirmed snapshots live in the journal.
        self.events = self.events[-100:]
        self.previous_run, self.previous = state['run_id'], semantic_state(bundle)
        if not busy:
            self._start_evaluation(event)

    def _start_evaluation(self, event):
        frozen = copy.deepcopy(event['_frozen'])
        self.worker = threading.Thread(target=self._evaluate, args=(event, frozen), name='event-assessment', daemon=True)
        event['status'] = 'evaluating'
        self.worker.start()

    def _evaluate(self, event, frozen):
        result, error = None, None
        try:
            evaluator = self.evaluator
            if evaluator is None:
                try:
                    from .situation_agent import evaluate_decision
                except ImportError:
                    from situation_agent import evaluate_decision
                evaluator = evaluate_decision
            public_event = {k: copy.deepcopy(v) for k, v in event.items() if k != '_frozen'}
            result = evaluator(frozen, public_event, event['language'])
            if not isinstance(result, dict):
                raise ValueError('Invalid decision assessment')
            options = result.get('decision_options')
            if (not isinstance(options, list) or {item.get('id') for item in options} != {o['id'] for o in OPTIONS}
                    or len(options) != len(OPTIONS) or result.get('recommended_option_id') not in {o['id'] for o in OPTIONS}):
                raise ValueError('Invalid decision options')
            result = {**result, 'run_id': event['run_id'], 'case_id': event['case_id'],
                      'at_ms': event['at_ms'], 'language': event['language']}
        except Exception:
            error = 'Event assessment failed; check provider configuration, connection, or response validation.'
        with self.sim.lock:
            self._reconcile(self._bundle())
            if self.stopping.is_set():
                return
            if event['status'] != 'superseded':
                event['report'], event['error'] = copy.deepcopy(result), error
                event['status'] = 'failed' if error else 'ready'
            pending = next((item for item in reversed(self.events) if item['status'] == 'pending'), None)
            if pending is not None:
                self._start_evaluation(pending)

    def command(self, command):
        with self.sim.lock:
            if command.get('run_id') != self.sim.run_id:
                raise ValueError('Stale run')
            action = command.get('action')
            if action == 'configure':
                enabled, language = command.get('enabled'), command.get('language')
                if type(enabled) is not bool or language not in ('en', 'ko'):
                    raise ValueError('Invalid event configuration')
                self.enabled, self.language = enabled, language
                if not enabled:
                    self.sim.test_operator.cancel('manual_override')
                bundle = self._bundle()
                self._reconcile(bundle)
                self.previous = semantic_state(bundle)
            elif action in ('assess_current', 'retry'):
                language = command.get('language', self.language)
                if language not in ('en', 'ko'):
                    raise ValueError('Invalid assessment language')
                if action == 'retry' and not any(e['id'] == command.get('event_id') for e in self.events):
                    raise ValueError('Unknown event')
                state = self.sim.state()
                bundle = build_bundle(state)
                self._reconcile(bundle)
                trigger = dict(kind='manual_review', subject='received_situation', previous=None,
                               current='requested', evidence_ids=[bundle['observations']['id']])
                self._capture(state, bundle, [trigger], language)
            elif action == 'confirm':
                self.sim.test_operator.cancel('manual_override', pause=False)
                self._confirm(command)
            else:
                raise ValueError('Unknown decision action')
            return self.snapshot()

    def _confirm(self, command, actor=None):
        self._reconcile(self._bundle())
        event = next((e for e in self.events if e['id'] == command.get('event_id')), None)
        if event is None or event['run_id'] != self.sim.run_id or event['status'] != 'ready':
            raise ValueError('Event is not ready for a current decision')
        if command.get('confirm') is not True:
            raise ValueError('Explicit confirmation is required')
        if command.get('evidence_version') != event['evidence_version']:
            raise ValueError('Evidence changed; request a new assessment')
        option = command.get('option_id')
        if option not in {item['id'] for item in event['report']['decision_options']}:
            raise ValueError('Invalid decision option')
        reviewer, reason = command.get('reviewer', ''), command.get('reason', '')
        if not isinstance(reviewer, str) or len(reviewer.strip()) > 80:
            raise ValueError('Reviewer alias must be text up to 80 characters')
        if not isinstance(reason, str) or len(reason.strip()) > 1000:
            raise ValueError('Additional comment must be text up to 1000 characters')
        frozen = {k: copy.deepcopy(v) for k, v in event.items() if k != '_frozen'}
        snapshot = dict(event=frozen, evidence=build_bundle(event['_frozen']), report=copy.deepcopy(event['report']))
        row = dict(schema_version=1, kind='event_decision', id=uuid.uuid4().hex,
                   actor=copy.deepcopy(actor or {'type': 'human'}),
                   run_id=event['run_id'], case_id=event['case_id'], event_id=event['id'],
                   at_ms=event['at_ms'], evidence_version=event['evidence_version'],
                   option_id=option, outcome='deferred' if option == 'defer' else 'confirmed',
                   reviewer=reviewer.strip(), reason=reason.strip(), decided_at_unix_ms=int(time.time() * 1000),
                   snapshot=snapshot, snapshot_hash=digest(snapshot))
        self.audit.append(row)  # Durable success must precede every local effect.
        event['status'] = 'decided'
        event.pop('_frozen', None)
        event['decision'] = {k: copy.deepcopy(v) for k, v in row.items() if k != 'snapshot'}
        self.sim.playing = False
        self.sim.anchor_ms, self.sim.anchor_wall = event['at_ms'], self.sim.clock()
        if option in ('continue_monitoring', 'defer'):
            # Preserve the normal Play contract, including starting a new run at the end.
            self.sim.control({'action': 'play'})
        else:
            self.sim.revision += 1
