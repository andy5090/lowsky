import copy
import importlib.util
import json
import os
import unittest
from unittest.mock import patch

from tools.monitor_server import Simulation
from tools.situation_agent import (_create_agent, _evidence_tools, build_bundle, configuration_status, deepagents_report,
                                   evaluate, rules_report, validate_report)


class SituationAgentTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'LOW_SKY_AGENT_MODEL': ''})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.sim = Simulation()

    def state(self, case='case_003', at_ms=90000):
        self.sim.control(dict(action='case', case_id=case))
        self.sim.control(dict(action='seek', at_ms=at_ms))
        return self.sim.state()

    def test_rules_are_explicit_and_change_with_received_evidence(self):
        empty = evaluate(self.state(at_ms=0))
        loss = evaluate(self.state())
        recovered = evaluate(self.state(at_ms=140000))
        self.assertEqual(loss['mode'], 'rules')
        self.assertIsNone(loss['model'])
        self.assertNotEqual(empty['summary'], loss['summary'])
        self.assertNotEqual(loss['summary'], recovered['summary'])
        self.assertTrue(any('cause is unknown' in item['text'] for item in loss['uncertain']))
        self.assertNotEqual(evaluate(self.state(), 'ko')['summary'], loss['summary'])

    def test_bundle_has_complete_counts_and_bounded_examples(self):
        bundle = build_bundle(self.state())
        self.assertEqual(bundle['observations']['total'], 240)
        self.assertEqual(bundle['reviews']['pending'], 240)
        self.assertEqual(len(bundle['track_examples']), 12)
        self.assertTrue(bundle['sampling']['truncated'])
        self.assertEqual(sum(group['total'] for group in bundle['fleet']), 240)
        self.assertLess(len(json.dumps(bundle)), 18000)
        tools = _evidence_tools(bundle)
        self.assertEqual(len(tools), 4)
        for tool in tools:
            result = tool()
            self.assertIsInstance(result, dict)
        tool_result = tools[0]()
        tool_result['observations']['total'] = -1
        self.assertEqual(bundle['observations']['total'], 240)

    def test_truth_history_free_text_and_future_records_are_excluded(self):
        state = self.state(at_ms=10000)
        state['simulation_positions'] = [{'object_id': 'secret_truth', 'position': [1, 2, 3]}]
        state['world'] = {'keyframes': 'secret_future_path'}
        state['contexts'] = [{'text': 'secret_context'}]
        state['situation'] = {'events': [{'text': 'secret_event'}]}
        state['tracks'][0]['history'] = [{'text': 'secret_history'}]
        state['tracks'][0]['records'][0]['ground_truth'] = 'secret_truth'
        future = copy.deepcopy(state['tracks'][0])
        future['object_id'] = 'secret_unknown_track'
        for record in future['records']:
            record.update(id='secret_future_evidence', observed_at_ms=11000, available_at_ms=12000)
        state['tracks'].append(future)
        state['track_reviews'] = [dict(object_id=state['tracks'][0]['object_id'],
            run_id=state['run_id'], at_ms=9000, evidence_version=state['tracks'][0]['evidence_version'],
            decision='noted', reviewer='secret_person', reason='secret_reason')]
        encoded = json.dumps(build_bundle(state))
        self.assertNotIn('secret_', encoded)
        self.assertNotIn('position', encoded)
        self.assertNotIn('history', encoded)
        report = evaluate(state)
        self.assertNotIn('secret_', json.dumps(report['evidence_bundle']))
        self.assertEqual(report['input_version'], report['evidence_bundle']['input_version'])
        self.assertTrue(set(report['evidence_ids']) <= set(report['evidence_bundle']['evidence_ids']))
        frozen = copy.deepcopy(report['evidence_bundle'])
        state['tracks'].clear()
        self.assertEqual(report['evidence_bundle'], frozen)

    def test_future_source_fleet_and_early_evidence_are_not_reported(self):
        state = self.state(at_ms=0)
        state['sources'][0]['evidence'] = dict(id='future_health', status='online', observed_at_ms=0, available_at_ms=1)
        state['sensor_fleet']['sensors'][0].update(evidence_id='future_fleet', observed_at_ms=0, available_at_ms=1, status='online')
        state['early_warning']['zones'][0]['evidence'] = [dict(id='future_early', observed_at_ms=0, available_at_ms=1, assessment='current', object_present=True)]
        bundle = build_bundle(state)
        self.assertEqual(bundle['sources'][0]['status'], 'unknown')
        self.assertTrue(all(zone['positive_sources'] == 0 for zone in bundle['early_signals']))
        self.assertNotIn('future_', json.dumps(bundle))
        self.assertEqual(bundle['observations']['total'], 0)

    def test_mutation_outside_sample_changes_input_version(self):
        state = self.state(case='case_001', at_ms=90000)
        original = build_bundle(state)
        state['tracks'][-1]['records'][0]['marker_label'] = 'diamond'
        changed = build_bundle(state)
        self.assertNotEqual(original['input_version'], changed['input_version'])
        self.assertNotEqual(original['observations']['by_quality'], changed['observations']['by_quality'])
        # Even a timestamp-only change outside the first 12 sampled load tracks
        # changes the input digest; the report is tied to the complete snapshot.
        state = self.state()
        original = build_bundle(state)
        state['tracks'][-1]['records'][0]['available_at_ms'] -= 1
        state['tracks'][-1]['records'][0]['observed_at_ms'] -= 1
        self.assertNotEqual(original['input_version'], build_bundle(state)['input_version'])

    def test_fake_runner_is_citation_checked_and_never_silently_falls_back(self):
        state = self.state()
        with patch.dict(os.environ, {'LOW_SKY_AGENT_MODEL': 'test:fake'}):
            def good(bundle, language, model):
                self.assertEqual((language, model), ('en', 'test:fake'))
                return rules_report(bundle, language)
            report = evaluate(state, runner=good)
            self.assertEqual(report['mode'], 'llm')
            self.assertEqual(report['model'], 'test:fake')
            def invalid(bundle, language, model):
                result = rules_report(bundle, language)
                result['known'][0]['evidence_ids'] = ['invented_evidence']
                return result
            with self.assertRaisesRegex(ValueError, 'evidence reference'):
                evaluate(state, runner=invalid)
            with self.assertRaisesRegex(RuntimeError, 'provider failed'):
                evaluate(state, runner=lambda *_: (_ for _ in ()).throw(RuntimeError('provider failed')))

    def test_config_and_schema_rejections(self):
        self.assertEqual(configuration_status()['mode'], 'rules')
        with patch.dict(os.environ, {'LOW_SKY_AGENT_MODEL': 'no_provider'}):
            with self.assertRaisesRegex(ValueError, 'provider:model'):
                evaluate(self.state())
        with self.assertRaises(ValueError):
            evaluate(self.state(), 'fr')
        bundle = build_bundle(self.state())
        report = rules_report(bundle)
        report['known'][0]['evidence_ids'] = []
        with self.assertRaises(ValueError):
            validate_report(report, bundle)

    @unittest.skipUnless(importlib.util.find_spec('deepagents'), 'Optional Deep Agents SDK is not installed')
    def test_actual_sdk_tool_loop_and_structured_output_without_provider_calls(self):
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import AIMessage, ToolMessage
        from langchain_core.outputs import ChatGeneration, ChatResult
        from pydantic import Field
        bundle = build_bundle(self.state())
        expected = rules_report(bundle)
        class EvidenceModel(BaseChatModel):
            model_name: str = 'lowsky:test'
            bound_names: list[str] = Field(default_factory=list)
            @property
            def _llm_type(self):
                return 'lowsky-test'
            def bind_tools(self, tools, **kwargs):
                self.bound_names[:] = [tool.get('function', {}).get('name', tool.get('name', ''))
                                       if isinstance(tool, dict) else tool.name for tool in tools]
                return self
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                if not any(isinstance(message, ToolMessage) for message in messages):
                    calls = [dict(name=tool.__name__, args={}, id=f'call_{index}')
                             for index, tool in enumerate(_evidence_tools(bundle))]
                else:
                    calls = [dict(name='SituationReport', args=expected, id='structured_report')]
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content='', tool_calls=calls))])
        model = EvidenceModel()
        agent = _create_agent(bundle, model)
        result = agent.invoke({'messages': [{'role': 'user', 'content': 'Read evidence tools and report.'}]},
                              config={'recursion_limit': 12})
        self.assertEqual(validate_report(result['structured_response'], bundle), expected)
        called = {call['name'] for message in result['messages'] for call in getattr(message, 'tool_calls', [])}
        self.assertTrue({tool.__name__ for tool in _evidence_tools(bundle)} <= called)
        self.assertFalse({'task', 'ls', 'read_file', 'write_file', 'execute', 'grep'} & set(model.bound_names))
        with patch('langchain.chat_models.init_chat_model', return_value=model) as initialize:
            self.assertEqual(deepagents_report(bundle, 'en', 'lowsky:test'), expected)
            initialize.assert_called_once_with('lowsky:test', timeout=20, max_retries=0)


if __name__ == '__main__':
    unittest.main()
