import unittest
from tools.monitor_server import Simulation
from tools.exercise import motion_time, sample
from tools.situation_agent import build_bundle

class ExerciseTests(unittest.TestCase):
    def setUp(self):
        self.now=0.0
        self.sim=Simulation(clock=lambda:self.now)
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
        self.assertEqual(track['position'],expected)
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

if __name__=='__main__':unittest.main()
