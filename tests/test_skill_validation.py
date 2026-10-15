import asyncio
import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agents.frontmatter import parse_frontmatter
from agents.online_skill_evolution import OnlineSkillCandidate, maintain_online_skill_candidate, online_ingest
from agents.skill_evolution import load_skill_stats, record_skill_usage_judgments
from agents.skill_validation import (
    accept_candidate, candidate_diff, evaluate_candidate, list_candidates, load_candidate,
    reject_candidate, rollback_candidate, stage_candidate,
)
from agents.skills import get_skill_by_name, reset_skill_cache
from agents.tools import execute_tool


class SkillValidationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        folder = Path(stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.project, self.home = folder / 'project', folder / 'home'
        self.project.mkdir()
        self.home.mkdir()
        stack.enter_context(patch('pathlib.Path.cwd', return_value=self.project))
        stack.enter_context(patch('pathlib.Path.home', return_value=self.home))
        stack.enter_context(patch.dict(os.environ, {}, clear=True))
        reset_skill_cache()
        self.addCleanup(reset_skill_cache)
        self.cases = self.project / 'cases.json'
        self.cases.write_text(json.dumps([{'prompt': 'Summarize testing.', 'must_include': ['Summary:']}]))
        self.file = self.project / '.bear/skills/summary-rules/SKILL.md'

    def stage(self, action='add', **kwargs):
        return stage_candidate(action=action, name='summary-rules', description='Short summaries',
                               instructions='Begin summaries with Summary:', **kwargs)['candidate_id']

    def existing(self):
        self.file.parent.mkdir(parents=True)
        content = ('---\r\nname: summary-rules\r\ndescription: Short summaries\r\nversion: 1.2.3\r\n'
                   'context: fork\r\nallowed-tools: read_file\r\nuser-invocable: true\r\n---\r\nBe concise.\r\n')
        self.file.write_bytes(content.encode())
        reset_skill_cache()
        return self.file.read_bytes()

    async def compare(self, candidate_id):
        async def query(system, prompt):
            return 'Summary: tests catch regressions.' if 'Begin summaries with Summary:' in prompt else 'Tests catch regressions.'
        return await evaluate_candidate(candidate_id, self.cases, query, model='test-model')

    async def test_add_compare_accept_and_rollback(self):
        candidate = self.stage()
        self.assertFalse(self.file.exists())
        self.assertIsNone(get_skill_by_name('summary-rules'))
        self.assertIn(candidate, list_candidates())
        self.assertIn('+Begin summaries', candidate_diff(candidate))
        report = await self.compare(candidate)
        self.assertEqual((report['baseline_score'], report['candidate_score'], report['total']), (1, 2, 2))
        self.assertFalse(self.file.exists())
        accept_candidate(candidate, model='test-model')
        self.assertEqual(self.file.read_text(), load_candidate(candidate)['proposed'])
        self.assertIsNotNone(get_skill_by_name('summary-rules'))
        self.assertEqual(load_skill_stats()['summary-rules']['accepted'], 1)
        asset = self.file.parent / 'keep.txt'
        asset.write_text('keep')
        rollback_candidate(candidate)
        self.assertFalse(self.file.exists())
        self.assertTrue(asset.exists())
        self.assertIsNone(get_skill_by_name('summary-rules'))
        self.assertEqual(load_skill_stats()['summary-rules']['rolled_back'], 1)

    async def test_merge_preserves_metadata_and_rollback_restores_exact_bytes(self):
        original = self.existing()
        candidate = self.stage('merge')
        self.assertEqual(self.file.read_bytes(), original)
        await self.compare(candidate)
        result = accept_candidate(candidate, model='test-model')
        meta = parse_frontmatter(self.file.read_text()).meta
        self.assertEqual(result['version'], '1.2.4')
        self.assertEqual(load_skill_stats()['summary-rules']['version'], '1.2.4')
        self.assertEqual((meta['context'], meta['allowed-tools'], meta['user-invocable']), ('fork', 'read_file', 'true'))
        rollback_candidate(candidate)
        self.assertEqual(self.file.read_bytes(), original)
        self.assertEqual(load_skill_stats()['summary-rules']['version'], '1.2.3')

    async def test_unvalidated_and_wrong_model_are_blocked(self):
        candidate = self.stage()
        with self.assertRaises(ValueError):
            accept_candidate(candidate, model='test-model')
        await self.compare(candidate)
        with self.assertRaises(ValueError):
            accept_candidate(candidate, model='another-model')
        self.assertFalse(self.file.exists())

    async def test_no_improvement_and_failed_candidate_stay_pending(self):
        for response in ['Summary: both already pass.', 'Missing required prefix.']:
            candidate = self.stage()
            report = await evaluate_candidate(candidate, self.cases, AsyncMock(return_value=response), model='test-model')
            self.assertFalse(report['passed'])
            self.assertEqual(load_candidate(candidate)['status'], 'pending')
            with self.assertRaises(ValueError):
                accept_candidate(candidate, model='test-model')

    async def test_active_edits_block_acceptance_and_rollback(self):
        self.existing()
        candidate = self.stage('merge')
        await self.compare(candidate)
        self.file.write_text('Human edit')
        with self.assertRaisesRegex(ValueError, 'Active skill changed'):
            accept_candidate(candidate, model='test-model')
        self.assertEqual(self.file.read_text(), 'Human edit')
        self.file.write_bytes(load_candidate(candidate)['baseline'].encode())
        accept_candidate(candidate, model='test-model')
        self.file.write_text('Newer human edit')
        with self.assertRaisesRegex(ValueError, 'overwrite newer edits'):
            rollback_candidate(candidate)

    async def test_re_evaluation_failure_invalidates_old_pass(self):
        candidate = self.stage()
        await self.compare(candidate)
        with self.assertRaises(RuntimeError):
            await evaluate_candidate(candidate, self.cases, AsyncMock(side_effect=RuntimeError('offline')), model='test-model')
        self.assertEqual(load_candidate(candidate)['status'], 'pending')
        with self.assertRaises(ValueError):
            accept_candidate(candidate, model='test-model')

    async def test_cancelled_evaluation_invalidates_old_pass(self):
        candidate = self.stage()
        await self.compare(candidate)
        entered = asyncio.Event()
        async def query(system, prompt):
            entered.set()
            await asyncio.Future()
        task = asyncio.create_task(evaluate_candidate(candidate, self.cases, query, model='test-model'))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(load_candidate(candidate)['status'], 'pending')

    async def test_rejected_candidate_cannot_be_resurrected_by_evaluation(self):
        candidate = self.stage()
        async def query(system, prompt):
            reject_candidate(candidate)
            return 'Summary: result'
        with self.assertRaises(ValueError):
            await evaluate_candidate(candidate, self.cases, query, model='test-model')
        self.assertEqual(load_candidate(candidate)['status'], 'rejected')

    async def test_invalid_cases_and_stale_baseline_do_not_spend_requests(self):
        self.existing()
        candidate = self.stage('merge')
        query = AsyncMock()
        for cases in [[], [{}], [{'prompt': 'task'}], [{'prompt': 'task', 'must_include': ['']}],
                      [{'prompt': 'task', 'must_include': 'not a list'}]]:
            self.cases.write_text(json.dumps(cases))
            with self.assertRaises(ValueError):
                await evaluate_candidate(candidate, self.cases, query, model='test-model')
        query.assert_not_awaited()
        self.cases.write_text(json.dumps([{'prompt': 'task', 'exact': 'answer'}]))
        self.file.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Active skill changed'):
            await evaluate_candidate(candidate, self.cases, query, model='test-model')
        query.assert_not_awaited()

    async def test_candidate_edits_and_corrupt_pass_report_are_blocked(self):
        candidate = self.stage()
        await self.compare(candidate)
        path = self.project / '.bear/skill-evolution/candidates' / f'{candidate}.json'
        record = load_candidate(candidate)
        record['evaluation']['rows'][0]['candidate_answer'] = 'Failed answer'
        path.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            accept_candidate(candidate, model='test-model')
        record['proposed'] += '\nUnvalidated change'
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'content changed'):
            load_candidate(candidate)
        self.assertIn('invalid', list_candidates())
        with self.assertRaises(ValueError):
            load_candidate('../outside')

    async def test_failed_state_save_compensates_active_file(self):
        original = self.existing()
        candidate = self.stage('merge')
        await self.compare(candidate)
        with patch('agents.skill_validation._write_json', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                accept_candidate(candidate, model='test-model')
        self.assertEqual(self.file.read_bytes(), original)
        self.assertEqual(load_candidate(candidate)['status'], 'validated')

    async def test_model_skill_tools_only_stage(self):
        result = json.loads(await execute_tool('skill_create', {
            'name': 'summary-rules', 'description': 'Summaries', 'instructions': 'Begin with Summary:'}))
        self.assertEqual(result['action'], 'staged')
        self.assertFalse(self.file.exists())
        self.existing()
        original = self.file.read_bytes()
        result = json.loads(await execute_tool('skill_evolve', {'skill_name': 'summary-rules', 'lesson': 'Begin with Summary:'}))
        self.assertEqual(result['action'], 'staged')
        self.assertEqual(self.file.read_bytes(), original)

    async def test_online_extraction_stages_and_discard_is_respected(self):
        candidate = OnlineSkillCandidate(name='summary-rules', description='Summaries', instructions='Begin with Summary:')
        decision = AsyncMock(return_value='{"action":"add"}')
        result = await maintain_online_skill_candidate(candidate=candidate, side_query=decision)
        self.assertEqual(result['action'], 'staged')
        self.assertFalse(self.file.exists())
        self.existing()
        decision = AsyncMock(return_value='{"action":"discard"}')
        result = await maintain_online_skill_candidate(candidate=candidate, side_query=decision)
        self.assertEqual(result['action'], 'discard')

    async def test_malformed_extractor_output_is_ignored(self):
        result = await online_ingest(messages=[], side_query=AsyncMock(return_value='[]'))
        self.assertEqual(result['action'], 'none')

    async def test_repl_workflow_enforces_plan_and_deny_rules(self):
        from agents.agent import Agent
        agent = Agent(model='test-model', api_base='https://example.invalid/v1', api_key='test-placeholder',
                      custom_system_prompt='test')
        self.addAsyncCleanup(agent._openai_client.close)
        candidate = self.stage()
        agent.permission_mode = 'plan'
        self.assertTrue((await agent.skill_workflow('diff', [candidate]))['ok'])
        for command, args in [('eval', [candidate, str(self.cases)]), ('accept', [candidate]),
                              ('rollback', [candidate]), ('reject', [candidate])]:
            with self.subTest(command=command):
                self.assertFalse((await agent.skill_workflow(command, args))['ok'])
        agent.permission_mode = 'default'
        await self.compare(candidate)
        with patch('agents.agent.check_permission', return_value={'action': 'deny', 'message': 'locked'}):
            result = await agent.skill_workflow('accept', [candidate])
        self.assertFalse(result['ok'])
        self.assertFalse(self.file.exists())
        with patch('agents.agent.check_permission', return_value={'action': 'confirm', 'message': 'new file'}):
            result = await agent.skill_workflow('accept', [candidate])
        self.assertTrue(result['ok'])
        self.assertTrue(self.file.exists())

    async def test_repl_eval_and_quoted_case_path(self):
        from agents.agent import Agent
        from agents.main import run_repl
        agent = Agent(model='test-model', api_base='https://example.invalid/v1', api_key='test-placeholder',
                      custom_system_prompt='test')
        self.addAsyncCleanup(agent._openai_client.close)
        candidate = self.stage()
        async def query(system, prompt):
            return 'Summary: result' if 'Begin summaries' in prompt else 'Result'
        with patch.object(agent, '_build_side_query', return_value=query):
            result = await agent.skill_workflow('eval', [candidate, str(self.cases)])
        self.assertTrue(result['passed'])
        self.assertIn('baseline=1/2', result['text'])
        with patch.object(agent, '_build_side_query', return_value=AsyncMock(side_effect=Exception('provider failure'))):
            result = await agent.skill_workflow('eval', [candidate, str(self.cases)])
        self.assertFalse(result['ok'])
        self.assertEqual(load_candidate(candidate)['status'], 'pending')
        with patch('builtins.input', side_effect=[f'/skill-eval {candidate} "cases with spaces.json"', 'exit']), \
             patch('agents.main.signal.signal'), patch('agents.main.print_welcome'), \
             patch('agents.main.print_user_prompt'), patch('agents.main.print_goodbye'), \
             patch('agents.main.print_info'), \
             patch.object(agent, 'skill_workflow', AsyncMock(return_value={'ok': True})) as workflow:
            await run_repl(agent)
        workflow.assert_awaited_once_with('eval', [candidate, 'cases with spaces.json'])

    async def test_retargeted_symlink_blocks_activation(self):
        candidate = self.stage()
        await self.compare(candidate)
        outside = self.project.parent / 'outside'
        outside.mkdir()
        self.file.parent.parent.mkdir(parents=True)
        self.file.parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'destination'):
            accept_candidate(candidate, model='test-model')
        self.assertFalse((outside / 'SKILL.md').exists())

    async def test_agent_abort_cancels_evaluation_without_leaving_old_pass(self):
        from agents.agent import Agent
        agent = Agent(model='test-model', api_base='https://example.invalid/v1', api_key='test-placeholder',
                      custom_system_prompt='test')
        self.addAsyncCleanup(agent._openai_client.close)
        candidate = self.stage()
        await self.compare(candidate)
        entered = asyncio.Event()
        async def query(system, prompt):
            entered.set()
            await asyncio.Future()
        with patch.object(agent, '_build_side_query', return_value=query):
            task = asyncio.create_task(agent.skill_workflow('eval', [candidate, str(self.cases)]))
            await entered.wait()
            self.assertTrue(agent.is_processing)
            agent.abort()
            result = await task
        self.assertFalse(result['ok'])
        self.assertFalse(agent.is_processing)
        self.assertEqual(load_candidate(candidate)['status'], 'pending')

    def test_usage_judgments_do_not_prune_by_default(self):
        self.existing()
        judgments = [{'name': 'summary-rules', 'source': 'user', 'skill_dir': str(self.file.parent),
                      'relevant': False, 'used': False}] * 45
        result = record_skill_usage_judgments(judgments)
        self.assertFalse(result['pruned'])
        self.assertTrue(self.file.exists())


if __name__ == '__main__':
    unittest.main()
