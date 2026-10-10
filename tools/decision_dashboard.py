"""Received-evidence review cards and local scripted follow-ups, not engagement advice."""
import copy
import time
import uuid

try:
    from .evidence_review import AuditLog, digest
except ImportError:
    from evidence_review import AuditLog, digest

WAIT_MS = 30000
REVIEW_WINDOW_MS = 90000
REASONS = ('bird', 'civil_aircraft', 'friendly', 'sensor_error')
BASE_ACTIONS = ('continue_observe', 'cue_sensor', 'raise_alert', 'dismiss')
REVIEW_ACTIONS = ('escalate', 'notify_mock', 'record_review', 'hold')


class DecisionDashboard:
    def __init__(self, path=None):
        self.audit = AuditLog(path)

    def view(self, state):
        records = [r for r in self.audit.records if r['run_id'] == state['run_id']]
        grouped = {}
        for row in records:
            grouped.setdefault(row['object_id'], []).append(row)
        cards = []
        now = state['at_ms']
        for track in state['tracks']:
            history = grouped.get(track['object_id'], [])
            # Receipt history only; no world positions, flight routes or future reports.
            first_ms = track['first_received_at_ms']
            deadline = min(state['duration_ms'], first_ms + REVIEW_WINDOW_MS)
            wait = next((r for r in reversed(history) if r['decision'] in ('continue_observe', 'cue_sensor')), None)
            due = wait['at_ms'] + WAIT_MS if wait else None
            followup = None
            if wait:
                received = now >= due
                followup = dict(status='received' if received else 'pending', available_at_ms=due,
                                id=f"scripted_review_{wait['id']}" if received else None,
                                result='scripted_visual_review' if received else None)
            done = {r['decision'] for r in history}
            if now >= deadline or 'dismiss' in done:
                status = 'closed'
            elif track['last_known']:
                status = 'stale'
            elif track['quality'] in ('contradictory', 'not_comparable', 'missing'):
                status = 'needs_review'
            elif followup and followup['status'] == 'received':
                status = 'corroborated'
            else:
                status = 'observed'
            actions = []
            for choice in BASE_ACTIONS + (REVIEW_ACTIONS if status in ('needs_review', 'corroborated') else ()):
                reason = None
                if status in ('closed', 'stale'):
                    reason = status
                elif choice in done:
                    reason = 'completed'
                elif choice in ('continue_observe', 'cue_sensor'):
                    if wait:
                        reason = 'pending' if now < due else 'completed'
                    elif now + WAIT_MS >= deadline:
                        reason = 'too_late'
                actions.append(dict(id=choice, enabled=reason is None, reason=reason))
            card = dict(object_id=track['object_id'], status=status, quality=track['quality'],
                        source_count=len(track['records']), evidence_ids=[r['id'] for r in track['records']],
                        deadline_ms=deadline, remaining_ms=max(0, deadline-now),
                        next_review_at_ms=due, followup=followup, priority='raise_alert' in done,
                        actions=actions, last_action=history[-1]['decision'] if history else None)
            card['mock_notice'] = dict(
                en=f"SIMULATION / {track['object_id']} / Evidence review requested. Identity and intent are unconfirmed.",
                ko=f"시뮬레이션 / {track['object_id']} / 관측 근거 검토를 요청합니다. 정체와 의도는 확인되지 않았습니다.")
            # Routine receipt IDs/positions and time passage do not erase a human draft.
            # Stage, source availability, expiry and completed actions do invalidate it.
            card['version'] = digest(dict(run_id=state['run_id'], object_id=track['object_id'],
                status=status, quality=track['quality'], deadline_ms=deadline, source_count=card['source_count'],
                sources=[(r['source_id'], r['status']) for r in state['sources']],
                actions=actions, last_id=history[-1]['id'] if history else None))
            cards.append(card)
        return dict(scope='simulation_review', at_ms=now, cards=cards,
                    recent=[{key: r[key] for key in ('id', 'object_id', 'decision', 'at_ms', 'reason')}
                            for r in records[-20:]])

    def confirm(self, command, state):
        if command.get('confirm') is not True or command.get('run_id') != state['run_id']:
            raise ValueError('Confirm a choice for the current run')
        card = next((c for c in state['dashboard']['cards'] if c['object_id'] == command.get('object_id')), None)
        if card is None or command.get('card_version') != card['version']:
            raise ValueError('The review card changed; select again')
        choice = command.get('choice')
        if not any(a['id'] == choice and a['enabled'] for a in card['actions']):
            raise ValueError('This choice is no longer available')
        reason_code = command.get('reason_code', '')
        if choice == 'dismiss' and reason_code not in REASONS:
            raise ValueError('Select a dismissal reason')
        if choice != 'dismiss' and reason_code:
            raise ValueError('Dismissal reasons apply only to dismissal')
        reviewer, comment = command.get('reviewer', ''), command.get('comment', '')
        if not isinstance(reviewer, str) or len(reviewer.strip()) > 80:
            raise ValueError('Reviewer alias must be at most 80 characters')
        if not isinstance(comment, str) or len(comment.strip()) > 1000:
            raise ValueError('Comment must be at most 1000 characters')
        if len(self.audit.records) >= 10000:
            raise ValueError('Local dashboard journal limit reached')
        track = next(t for t in state['tracks'] if t['object_id'] == card['object_id'])
        evidence = dict(records=copy.deepcopy(track['records']), sources=copy.deepcopy(state['sources']),
                        test_run=copy.deepcopy(state.get('test_run')))
        outcome = dict(kind='local_review', scheduled_at_ms=None)
        if choice in ('continue_observe', 'cue_sensor'):
            outcome = dict(kind='scripted_visual_review', scheduled_at_ms=state['at_ms']+WAIT_MS)
        elif choice == 'notify_mock':
            outcome = dict(kind='local_mock_notice', transmitted=False,
                           text=copy.deepcopy(card['mock_notice']))
        fields = dict(
            event=dict(object_id=card['object_id'], scope='simulation_review'),
            evidence=evidence,
            assessment=copy.deepcopy(card),
            uncertainty=['Object type, intent and communication method remain unknown.',
                         'The follow-up is scripted, not an EO measurement. Review time is not arrival time.'],
            decision=dict(choice=choice, reviewer=reviewer.strip(), actor='local_human', outcome=outcome),
            reason=dict(code=reason_code, comment=comment.strip(), classification_verified=False),
            time=dict(simulation_ms=state['at_ms'], recorded_at_unix_ms=int(time.time()*1000)))
        row = dict(schema_version=1, id=uuid.uuid4().hex, run_id=state['run_id'], case_id=state['case_id'],
                   object_id=card['object_id'], at_ms=state['at_ms'], reviewer=reviewer.strip(),
                   decision=choice, reason=reason_code or comment.strip(),
                   reviewed_at_unix_ms=fields['time']['recorded_at_unix_ms'],
                   evidence_snapshot=fields, evidence_version=digest(fields))
        self.audit.append(row)

    def export(self):
        return dict(schema_version=1, scope='simulation_review', records=[
            dict(id=r['id'], run_id=r['run_id'], case_id=r['case_id'], fields=copy.deepcopy(r['evidence_snapshot']))
            for r in self.audit.records])
