import unittest
from tools.monitor_server import Simulation
from tools.exercise import motion_time, sample
from tools.situation_agent import build_bundle

class ExerciseTests(unittest.TestCase):
    def setUp(self):
        self.now=0.0
        self.sim=Simulation(clock=lambda:self.now)
        self.sim.control(dict(action="case",case_id="case_003"))
        self.sim.control(dict(action='seek',at_ms=100000))
        self.state=self.sim.state()
        self.object_id=self.state['exercise']['eligible_objects'][0]

    def command(self, branch='hold'):
        return dict(action='exercise_branch',run_id=self.sim.run_id,object_id=self.object_id,
                    asset_id='admin_1',branch_id=branch,confirm=True)

    def test_requires_received_object_current_run_and_explicit_confirmation(self):
        for override in ({'run_id':'old'},{'object_id':'hidden'},{'asset_id':'unknown'},
                         {'branch_id':'invented'},{'confirm':False}):
            with self.assertRaises(ValueError):self.sim.control({**self.command(),**override})
            self.assertIsNone(self.sim.exercise_selection)
        self.sim.control(dict(action='reset'))
        with self.assertRaises(ValueError):self.sim.control(self.command())

    def test_hold_is_delayed_keeps_clock_running_and_changes_received_positions(self):
        self.sim.control(dict(action='play'))
        result=self.sim.control(self.command())
        self.assertTrue(result['playing'])
        self.assertEqual(result['exercise']['selection']['status'],'pending')
        selection=self.sim.exercise_selection
        self.now+=11
        state=self.sim.state(show_positions=True)
        self.assertEqual(state['at_ms'],111000)
        self.assertEqual(state['exercise']['selection']['status'],'applied')
        self.assertEqual(next(a for a in state['exercise']['assets'] if a['id']=='admin_1')['status'],'restricted')
        expected=sample(self.sim.world_frames[self.sim.case_id][self.object_id],105000)
        truth=next(p for p in state['simulation_positions'] if p['object_id']==self.object_id)
        self.assertEqual(truth['position'],expected)
        track=next(t for t in state['tracks'] if t['object_id']==self.object_id)
        for actual, wanted in zip(track['position'], expected):
            self.assertAlmostEqual(actual, wanted, places=6)
        self.assertTrue(all(row['available_at_ms']<=state['at_ms'] for row in track['records']))
        self.assertEqual(build_bundle(state)['exercise']['scope'],'scripted_training')
        self.assertNotIn('simulation_positions',str(build_bundle(state)))
        self.now+=2
        self.assertEqual(next(p['position'] for p in self.sim.state(True)['simulation_positions'] if p['object_id']==self.object_id),expected)
        self.assertEqual(motion_time(selection,'another',111000),111000)

    def test_each_branch_has_explicit_facility_state_and_motion(self):
        for branch,status in [('continue','unavailable'),('hold','restricted'),('withdraw','available')]:
            self.sim.control(dict(action='seek',at_ms=100000))
            self.sim.control(self.command(branch))
            self.sim.control(dict(action='play'))
            self.now+=10
            state=self.sim.state(True)
            self.assertEqual(next(a for a in state['exercise']['assets'] if a['id']=='admin_1')['status'],status)
            t=motion_time(self.sim.exercise_selection,self.object_id,state['at_ms'])
            self.assertEqual(t, {'continue':110000,'hold':105000,'withdraw':100000}[branch])
            self.sim.control(dict(action='pause'))

    def test_only_one_branch_reset_and_late_selection_guard(self):
        self.sim.control(self.command())
        with self.assertRaises(ValueError):self.sim.control(self.command('withdraw'))
        self.sim.control(dict(action='seek',at_ms=120000))
        self.assertIsNone(self.sim.state()['exercise']['selection'])
        self.sim.control(dict(action='seek',at_ms=179000))
        with self.assertRaises(ValueError):self.sim.control(self.command())

    def test_branch_does_not_reveal_hidden_drone_positions_or_change_source_input(self):
        original=self.sim._public_input()['observations'][-1]['position'][:]
        self.sim.control(self.command())
        self.sim.control(dict(action='play'));self.now+=11
        self.assertNotIn('simulation_positions',self.sim.state())
        self.assertEqual(original,self.sim._public_input()['observations'][-1]['position'])
        self.assertEqual(len(self.sim.state()['exercise']['assets']),len(self.sim.site_layout['facilities'])+1)



class MissionVignetteTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation(clock=lambda: 0)
        self.sim.control(dict(action='case', case_id='case_001'))

    def advance(self, at_ms, truth=False):
        self.sim.anchor_ms = at_ms
        return self.sim.state(show_positions=truth)

    def mission(self, state, object_id='object_11'):
        return next(row for row in state['exercise']['missions'] if row['object_id'] == object_id)

    def command(self, state, branch):
        mission = self.mission(state)
        return dict(action='exercise_branch', run_id=state['run_id'], object_id=mission['object_id'],
                    asset_id=mission['asset_id'], branch_id=branch, confirm=True)

    def asset_status(self, state, asset_id='hangar_1'):
        return next(row['status'] for row in state['exercise']['assets'] if row['id'] == asset_id)

    def test_identity_is_received_only_and_truth_opt_in_is_separate(self):
        before = self.advance(269999)
        self.assertEqual(before['exercise']['missions'], [])
        self.assertNotIn('simulation_missions', before)
        truth = self.advance(269999, True)
        self.assertEqual(len(truth['simulation_missions']), 2)
        self.assertEqual(truth['exercise']['missions'], [])
        first = self.advance(270000)
        self.assertEqual([row['object_id'] for row in first['exercise']['missions']], ['object_11'])
        both = self.advance(300000)
        self.assertEqual({row['kind'] for row in both['exercise']['missions']}, {'impact_vignette', 'drop_vignette'})
        for row in both['exercise']['missions']:
            self.assertEqual(row['scope'], 'scripted_training')
            self.assertTrue(row['synthetic'])
            self.assertIsNone(row['outcome'])
            self.assertIsNone(row['result_at_ms'])
        self.sim.control(dict(action='case', case_id='case_003'))
        self.assertEqual(self.advance(170000, True)['simulation_missions'], [])
        self.assertEqual(self.sim.state()['exercise']['missions'], [])

    def test_default_vignettes_publish_late_results_on_the_shared_clock(self):
        first = self.advance(674999)
        self.assertEqual(self.mission(first)['phase'], 'approach')
        for at_ms, progress in ((675000, 0.0), (682500, 0.5)):
            state = self.advance(at_ms)
            mission = self.mission(state)
            self.assertEqual(mission['phase'], 'finale')
            self.assertEqual(mission['progress'], progress)
            self.assertIsNone(mission['outcome'])
            self.assertEqual(self.asset_status(state), 'available')
        completed = self.advance(690000)
        mission = self.mission(completed)
        self.assertEqual((mission['phase'], mission['outcome'], mission['result_at_ms']),
                         ('complete', 'unresolved', 690000))
        self.assertEqual(self.asset_status(completed), 'unavailable')
        self.assertIsNone(self.mission(completed, 'object_12')['outcome'])
        self.assertEqual(self.asset_status(completed, 'admin_1'), 'available')
        self.assertIsNone(self.mission(self.advance(719999), 'object_12')['outcome'])
        dropped = self.advance(720000)
        self.assertEqual(self.mission(dropped, 'object_12')['outcome'], 'unresolved')
        self.assertEqual(self.asset_status(dropped, 'admin_1'), 'unavailable')
        # Seeking starts a fresh run; elapsed outcomes must not survive the rewind.
        reset = self.sim.control(dict(action='seek', at_ms=300000))
        self.assertIsNone(self.mission(reset)['outcome'])
        self.assertEqual(self.asset_status(reset), 'available')

    def test_scripted_branches_change_only_the_selected_vignette_outcome(self):
        for branch, outcome, asset in (('hold', 'partial', 'restricted'), ('withdraw', 'prevented', 'available')):
            state = self.sim.control(dict(action='seek', at_ms=300000))
            self.sim.control(self.command(state, branch))
            self.assertIsNone(self.mission(self.advance(304999))['outcome'])
            applied = self.advance(305000)
            self.assertEqual(self.mission(applied)['outcome'], outcome)
            self.assertEqual(self.mission(applied)['result_at_ms'], 305000)
            self.assertEqual(self.asset_status(applied), asset)
            later = self.advance(720000)
            self.assertEqual(self.mission(later)['outcome'], outcome)
            self.assertEqual(self.asset_status(later), asset)
            self.assertEqual(self.mission(later, 'object_12')['outcome'], 'unresolved')

    def test_continue_preserves_the_authored_late_result_instead_of_early_damage(self):
        state = self.advance(300000)
        branches = {row['id']: row for row in state['exercise']['branches']}
        self.assertEqual(branches['continue']['mission_result_timing'], 'finale')
        self.assertEqual(branches['continue']['result_timing'], 'after_delay')
        self.sim.control(self.command(state, 'continue'))
        applied = self.advance(305000)
        self.assertEqual(applied['exercise']['selection']['status'], 'applied')
        self.assertEqual(self.asset_status(applied), 'available')
        self.assertIsNone(self.mission(applied)['outcome'])
        self.assertEqual(self.asset_status(self.advance(690000)), 'unavailable')

    def test_wrong_asset_and_retroactive_prevention_are_rejected(self):
        state = self.advance(300000)
        with self.assertRaisesRegex(ValueError, 'authored facility'):
            self.sim.control({**self.command(state, 'hold'), 'asset_id': 'admin_1'})
        for at_ms in (685000, 690000):
            state = self.advance(at_ms)
            with self.assertRaises(ValueError):
                self.sim.control(self.command(state, 'withdraw'))
        self.assertIsNone(self.sim.exercise_selection)

    def test_hidden_actors_do_not_gain_public_missions_or_facility_outcomes(self):
        self.sim.public['case_001']['observations'] = []
        state = self.advance(780000, True)
        self.assertEqual(state['exercise']['missions'], [])
        self.assertEqual(len(state['simulation_missions']), 2)
        self.assertEqual(self.asset_status(state), 'available')

    def test_vignettes_and_author_truth_are_never_agent_evidence(self):
        state = self.advance(682500, True)
        for branch in (None, 'hold'):
            if branch:
                state = self.sim.control(dict(action='seek', at_ms=300000))
                self.sim.control(self.command(state, branch))
                state = self.advance(305000, True)
            encoded = str(build_bundle(state))
            for forbidden in ('simulation_missions', 'vignette_impact', 'vignette_drop', 'impact_vignette',
                              'drop_vignette', 'phase_end_ms'):
                self.assertNotIn(forbidden, encoded)


if __name__ == '__main__':
    unittest.main()
