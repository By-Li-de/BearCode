import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agents.agent import Agent, _get_context_windows, _get_max_output_tokens
from agents.session import save_session, load_session
from agents.tools import check_permission, execute_tool


class PermissionsTests(unittest.TestCase):
    def test_shell_code_needs_confirmation_even_without_dangerous_keywords(self):
        with patch('agents.tools._check_permission_rules', return_value=None):
            self.assertEqual(check_permission('run_shell', {'command': 'python script.py'}, 'default')['action'], 'confirm')
            self.assertEqual(check_permission('run_shell', {'command': 'echo hi'}, 'dontAsk')['action'], 'deny')

    def test_symlink_write_is_checked_against_real_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / 'project'
            project.mkdir()
            outside = Path(folder) / 'outside'
            outside.mkdir()
            (project / 'link').symlink_to(outside, target_is_directory=True)
            with patch('agents.tools.Path.cwd', return_value=project), \
                 patch('agents.tools._check_permission_rules', return_value=None):
                self.assertEqual(check_permission('write_file', {'file_path': str(project / 'link/new.txt')},
                                                  'acceptEdits')['action'], 'confirm')

    def test_deny_rule_beats_allow_and_auto_edits(self):
        with patch('agents.tools._check_permission_rules', return_value='deny'):
            self.assertEqual(check_permission('read_file', {'file_path': 'source.py'})['action'], 'deny')
            self.assertEqual(check_permission('write_file', {'file_path': 'source.py'}, 'acceptEdits')['action'], 'deny')

    def test_user_skills_require_confirmation(self):
        with patch('agents.tools._check_permission_rules', return_value=None):
            self.assertEqual(check_permission('skill_create', {'name': 'new', 'target': 'user'},
                                              'acceptEdits')['action'], 'confirm')

    def test_invalid_write_path_is_denied_in_plan_and_yolo(self):
        for mode in ['plan', 'bypassPermissions']:
            for value in ['', 123, ['path']]:
                with self.subTest(mode=mode, value=value):
                    self.assertEqual(check_permission('write_file', {'file_path': value}, mode)['action'], 'deny')

    def test_skill_creation_checks_symlink_at_specific_skill_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / 'project'
            (project / '.bear/skills').mkdir(parents=True)
            outside = Path(folder) / 'outside'
            outside.mkdir()
            (project / '.bear/skills/new').symlink_to(outside, target_is_directory=True)
            with patch('agents.tools.Path.cwd', return_value=project), \
                 patch('agents.tools._check_permission_rules', return_value=None):
                self.assertEqual(check_permission('skill_create', {'name': 'new'},
                                                  'acceptEdits')['action'], 'confirm')

    def test_active_skill_checks_actual_destination_even_with_stale_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / 'project'
            project.mkdir()
            home = Path(folder) / 'home'
            skill = home / '.bear/skills/new/SKILL.md'
            skill.parent.mkdir(parents=True)
            skill.write_text('---\nname: new\ndescription: test\n---\nInstructions')
            with patch('agents.tools.Path.cwd', return_value=project), \
                 patch('agents.tools.Path.home', return_value=home), \
                 patch('agents.skills.get_skill_by_name', return_value=None), \
                 patch('agents.tools._check_permission_rules', return_value=None):
                self.assertEqual(check_permission('skill_evolve', {'skill_name': 'new', 'target': 'ACTIVE'},
                                                  'acceptEdits')['action'], 'confirm')

    def test_allow_rule_cannot_override_plan_mode(self):
        with patch('agents.tools._check_permission_rules', return_value='allow'):
            for name, inp in [('run_shell', {'command': 'echo hi'}),
                              ('write_file', {'file_path': 'source.py'}),
                              ('mcp__browser__click', {})]:
                with self.subTest(tool=name):
                    self.assertEqual(check_permission(name, inp, 'plan')['action'], 'deny')

    def test_plan_file_exception_is_only_for_file_edits(self):
        with patch('agents.tools._check_permission_rules', return_value=None):
            self.assertEqual(check_permission('write_file', {'file_path': '/tmp/plan.md'},
                                              'plan', '/tmp/plan.md')['action'], 'allow')
            self.assertEqual(check_permission('skill_create', {'file_path': '/tmp/plan.md'},
                                              'plan', '/tmp/plan.md')['action'], 'deny')

    def test_mcp_requires_confirmation(self):
        with patch('agents.tools._check_permission_rules', return_value=None):
            self.assertEqual(check_permission('mcp__browser__click', {}, 'default')['action'], 'confirm')
            self.assertEqual(check_permission('mcp__browser__click', {}, 'dontAsk')['action'], 'deny')

    def test_outside_workspace_write_requires_confirmation(self):
        with patch('agents.tools._check_permission_rules', return_value=None):
            self.assertEqual(check_permission('write_file', {'file_path': '../outside.txt'},
                                              'acceptEdits')['action'], 'confirm')


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.agent = Agent(api_base='https://example.invalid/v1', api_key='test-placeholder',
                           custom_system_prompt='test', is_sub_agent=True)

    async def asyncTearDown(self):
        await self.agent._openai_client.close()

    async def test_multiple_openai_tools_execute_once_and_in_order(self):
        calls = [{'id': str(i), 'type': 'function',
                  'function': {'name': 'write_file', 'arguments': '{"file_path":"file.txt"}'}}
                 for i in range(2)]
        self.agent._call_openai_stream = AsyncMock(side_effect=[
            {'choices': [{'message': {'role': 'assistant', 'tool_calls': calls}}]},
            {'choices': [{'message': {'role': 'assistant', 'content': 'done'}}]},
        ])
        self.agent._execute_tool_call = AsyncMock(return_value='ok')
        with patch('agents.agent.check_permission', return_value={'action': 'allow'}), \
             patch('agents.agent.print_tool_call'), patch('agents.agent.print_tool_result'):
            await self.agent._chat_openai('task')
        self.assertEqual(self.agent._execute_tool_call.await_count, 2)
        results = [m['tool_call_id'] for m in self.agent._openai_messages if m['role'] == 'tool']
        self.assertEqual(results, ['0', '1'])

    async def test_openai_compaction_uses_chat_and_preserves_last_user(self):
        self.agent._openai_messages += [
            {'role': 'user', 'content': 'earlier'}, {'role': 'assistant', 'content': 'answer'},
            {'role': 'user', 'content': 'current task'},
        ]
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='summary'))],
                                   usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3))
        create = AsyncMock(return_value=response)
        with patch.object(self.agent._openai_client.chat.completions, 'create', create):
            await self.agent._compact_openai()
        create.assert_awaited_once()
        self.assertIn('summary', self.agent._openai_messages[1]['content'])
        self.assertEqual(self.agent._openai_messages[-1]['content'], 'current task')

    async def test_sub_agent_keeps_parent_permissions_and_credentials(self):
        self.agent.permission_mode = 'dontAsk'
        self.agent.confirm_fn = AsyncMock(return_value=False)
        child = SimpleNamespace(run_once=AsyncMock(return_value={
            'text': 'done', 'tokens': {'input': 1, 'output': 2}}),
            total_input_tokens=1, total_output_tokens=2, current_turns=0,
            use_openai=True, _openai_client=SimpleNamespace(close=AsyncMock()))
        with patch('agents.agent.Agent', return_value=child) as constructor, \
             patch('agents.agent.print_sub_agent_start'), patch('agents.agent.print_sub_agent_end'):
            await self.agent._execute_agent_tool({'prompt': 'task'})
        kwargs = constructor.call_args.kwargs
        self.assertEqual(kwargs['permission_mode'], 'dontAsk')
        self.assertEqual(kwargs.get('api_key'), 'test-placeholder')
        self.assertIs(kwargs.get('confirm_fn'), self.agent.confirm_fn)
        self.assertEqual(self.agent.total_input_tokens, 1)
        child._openai_client.close.assert_awaited_once()

    async def test_unavailable_tool_cannot_be_invoked_by_model(self):
        self.agent.tools = []
        with patch('agents.agent.execute_tool', AsyncMock()) as execute:
            result = await self.agent._execute_tool_call('write_file', {'file_path': 'hidden.txt', 'content': 'x'})
        self.assertIn('Action denied', result)
        execute.assert_not_awaited()

    async def test_empty_tool_grant_omits_api_tools_field(self):
        self.agent.tools = []
        async def empty_stream():
            if False:
                yield None
        create = AsyncMock(return_value=empty_stream())
        with patch.object(self.agent._openai_client.chat.completions, 'create', create):
            await self.agent._call_openai_stream()
        self.assertNotIn('tools', create.call_args.kwargs)

    async def test_denied_tool_returns_result_without_execution(self):
        self.agent.permission_mode = 'dontAsk'
        self.agent._call_openai_stream = AsyncMock(side_effect=[
            {'choices': [{'message': {'role': 'assistant', 'tool_calls': [
                {'id': 'call', 'type': 'function', 'function': {'name': 'run_shell', 'arguments': '{"command":"echo hi"}'}}]}}]},
            {'choices': [{'message': {'role': 'assistant', 'content': 'done'}}]},
        ])
        self.agent._execute_tool_call = AsyncMock()
        with patch('agents.tools._check_permission_rules', return_value=None), \
             patch('agents.agent.print_info'), patch('agents.agent.print_tool_call'):
            await self.agent._chat_openai('task')
        self.agent._execute_tool_call.assert_not_awaited()
        self.assertIn('Action denied', self.agent._openai_messages[3]['content'])

    async def test_failed_child_still_counts_usage(self):
        child = SimpleNamespace(run_once=AsyncMock(side_effect=RuntimeError('failed')),
                                total_input_tokens=8, total_output_tokens=3, current_turns=2,
                                use_openai=True, _openai_client=SimpleNamespace(close=AsyncMock()))
        with self.assertRaises(RuntimeError):
            await self.agent._run_sub_agent(child, 'task')
        self.assertEqual(self.agent.get_token_usage(), {'input': 8, 'output': 3})
        self.assertEqual(self.agent.current_turns, 2)

    async def test_budget_exhausted_before_next_model_call(self):
        self.agent.max_turns = 0
        self.agent._call_openai_stream = AsyncMock()
        with patch('agents.agent.print_info'):
            await self.agent._chat_openai('task')
        self.agent._call_openai_stream.assert_not_awaited()

    async def test_one_turn_budget_allows_one_tool_round(self):
        self.agent.max_turns = 1
        self.agent._call_openai_stream = AsyncMock(return_value={
            'choices': [{'message': {'role': 'assistant', 'tool_calls': [
                {'id': 'call', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{}'}}]}}]})
        self.agent._execute_tool_call = AsyncMock(return_value='ok')
        with patch('agents.agent.print_info'), patch('agents.agent.print_tool_call'), \
             patch('agents.agent.print_tool_result'):
            await self.agent._chat_openai('task')
        self.agent._call_openai_stream.assert_awaited_once()
        self.agent._execute_tool_call.assert_awaited_once()

    async def test_one_shot_plan_cannot_exit_without_approval(self):
        self.agent.is_sub_agent = False
        self.agent.permission_mode = 'plan'
        result = await self.agent._execute_plan_mode_tool('exit_plan_mode')
        self.assertIn('approval is required', result)
        self.assertEqual(self.agent.permission_mode, 'plan')

    async def test_fork_skill_uses_parent_permissions(self):
        self.agent.permission_mode = 'dontAsk'
        child = SimpleNamespace(run_once=AsyncMock(return_value={'text': 'done'}),
                                total_input_tokens=0, total_output_tokens=0, current_turns=0,
                                use_openai=True, _openai_client=SimpleNamespace(close=AsyncMock()))
        skill = {'context': 'fork', 'prompt': 'instructions', 'allowed_tools': ['read_file']}
        with patch('agents.skills.execute_skill', return_value=skill), \
             patch('agents.agent.Agent', return_value=child) as constructor, \
             patch('agents.agent.print_sub_agent_start'), patch('agents.agent.print_sub_agent_end'):
            self.assertEqual(await self.agent._execute_skill_tool({'skill_name': 'example'}), 'done')
        self.assertEqual(constructor.call_args.kwargs['permission_mode'], 'dontAsk')
        self.assertEqual([t['name'] for t in constructor.call_args.kwargs['custom_tools']], ['read_file'])

    async def test_anthropic_sub_agent_keeps_custom_endpoint_and_key(self):
        agent = Agent(anthropic_base_url='https://example.invalid/anthropic', api_key='test-placeholder',
                      permission_mode='dontAsk', custom_system_prompt='test')
        self.addAsyncCleanup(agent._anthropic_client.close)
        child = agent._create_sub_agent('test', [])
        self.addAsyncCleanup(child._anthropic_client.close)
        self.assertFalse(child.use_openai)
        self.assertEqual(child._anthropic_client.base_url, agent._anthropic_client.base_url)
        self.assertEqual(child._anthropic_client.api_key, 'test-placeholder')
        self.assertEqual(child.permission_mode, 'dontAsk')
        self.assertEqual(child.tools, [])

    async def test_thinking_constructor_uses_existing_capability_method(self):
        agent = Agent(api_key='test-placeholder', model='claude-sonnet-4-6', thinking=True,
                      custom_system_prompt='test')
        self.addAsyncCleanup(agent._anthropic_client.close)
        self.assertEqual(agent._thinking_mode, 'adaptive')

    async def test_plan_approval_is_awaited_and_changes_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'plan.md'
            file.write_text('Implementation plan')
            self.agent.permission_mode = 'plan'
            self.agent.is_sub_agent = False
            self.agent._plan_file_path = str(file)
            approval = AsyncMock(return_value={'choice': 'execute'})
            self.agent.set_plan_approval_fn(approval)
            with patch('agents.agent.print_info'):
                result = await self.agent._execute_plan_mode_tool('exit_plan_mode')
        approval.assert_awaited_once_with('Implementation plan')
        self.assertEqual(self.agent.permission_mode, 'acceptEdits')
        self.assertIn('Implementation plan', result)

    async def test_anthropic_tools_execute_once_and_return_all_results(self):
        agent = Agent(api_key='test-placeholder', custom_system_prompt='test', is_sub_agent=True)
        self.addAsyncCleanup(agent._anthropic_client.close)
        tools = [SimpleNamespace(type='tool_use', id=str(i), name='read_file', input={'file_path': 'source.py'})
                 for i in range(2)]
        usage = SimpleNamespace(input_tokens=10, output_tokens=2)
        agent._call_anthropic_stream = AsyncMock(side_effect=[
            SimpleNamespace(content=tools, usage=usage), SimpleNamespace(content=[], usage=usage)])
        agent._execute_tool_call = AsyncMock(return_value='ok')
        with patch('agents.agent.check_permission', return_value={'action': 'allow'}), \
             patch('agents.agent.print_tool_call'), patch('agents.agent.print_tool_result'):
            await agent._chat_anthropic('task')
        self.assertEqual(agent._execute_tool_call.await_count, 2)
        results = agent._anthropic_messages[2]['content']
        self.assertEqual([r['tool_use_id'] for r in results], ['0', '1'])

    async def test_tool_failure_is_returned_to_openai_model(self):
        self.agent._call_openai_stream = AsyncMock(side_effect=[
            {'choices': [{'message': {'role': 'assistant', 'tool_calls': [
                {'id': 'call', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{}'}}]}}]},
            {'choices': [{'message': {'role': 'assistant', 'content': 'done'}}]},
        ])
        self.agent._execute_tool_call = AsyncMock(side_effect=RuntimeError('tool broke'))
        with patch('agents.agent.check_permission', return_value={'action': 'allow'}), \
             patch('agents.agent.print_tool_call'), patch('agents.agent.print_tool_result'):
            await self.agent._chat_openai('task')
        self.assertIn('tool broke', self.agent._openai_messages[3]['content'])

    async def test_shell_can_be_cancelled_and_times_out(self):
        import shlex
        import sys
        command = shlex.quote(sys.executable) + ' -c ' + shlex.quote('import time; time.sleep(60)')
        result = await execute_tool('run_shell', {'command': command, 'timeout': 30})
        self.assertIn('timed out', result)
        task = asyncio.create_task(execute_tool('run_shell', {'command': command}))
        await asyncio.sleep(0.03)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)

    async def test_edit_rejects_stale_read(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'source.txt'
            file.write_text('before')
            state = {}
            await execute_tool('read_file', {'file_path': str(file)}, state)
            os.utime(file, (0, 0))
            result = await execute_tool('edit_file', {'file_path': str(file),
                                                    'old_string': 'before', 'new_string': 'after'}, state)
            self.assertIn('modified externally', result)
            self.assertEqual(file.read_text(), 'before')

    def test_unknown_model_has_conservative_context(self):
        self.assertLessEqual(_get_context_windows('custom-deployment'), 32768)

    async def test_cost_uses_configured_prices(self):
        with patch.dict(os.environ, {'BEAR_INPUT_PRICE_PER_MTOK': '1', 'BEAR_OUTPUT_PRICE_PER_MTOK': '2'}):
            agent = Agent(api_base='https://example.invalid/v1', api_key='test-placeholder',
                          custom_system_prompt='test')
        self.addAsyncCleanup(agent._openai_client.close)
        agent.total_input_tokens = 1_000_000
        agent.total_output_tokens = 1_000_000
        self.assertEqual(agent._get_current_cost_usd(), 3)

    def test_price_and_limit_validation(self):
        self.assertIsNone(self.agent._get_current_cost_usd())
        with self.assertRaisesRegex(ValueError, 'requires BEAR_INPUT_PRICE'):
            Agent(api_key='test-placeholder', custom_system_prompt='test', max_cost_usd=1)
        with patch.dict(os.environ, {'BEAR_CONTEXT_WINDOW': '8192', 'BEAR_MAX_OUTPUT_TOKENS': '2048'}):
            self.assertEqual(_get_context_windows('deployment'), 8192)
            self.assertEqual(_get_max_output_tokens('deployment'), 2048)
        for value in ['-1', 'nan', 'inf']:
            with self.subTest(value=value), patch.dict(os.environ, {'BEAR_INPUT_PRICE_PER_MTOK': value}):
                with self.assertRaises(ValueError):
                    Agent(api_key='test-placeholder', custom_system_prompt='test')

    async def test_modern_openai_model_uses_completion_limit(self):
        agent = Agent(api_base='https://example.invalid/v1', api_key='test-placeholder',
                      model='gpt-5.2', custom_system_prompt='test')
        self.addAsyncCleanup(agent._openai_client.close)
        self.assertEqual(agent._openai_output_limit(256), {'max_completion_tokens': 256})


class SessionTests(unittest.TestCase):
    def test_failed_save_keeps_existing_session_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder, patch('agents.session.SESSION_DIR', Path(folder)):
            save_session('session', {'text': '原记录'})
            with patch('agents.session.os.replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    save_session('session', {'text': 'new'})
            self.assertEqual(load_session('session'), {'text': '原记录'})
            self.assertEqual([p.name for p in Path(folder).iterdir()], ['session.json'])


if __name__ == '__main__':
    unittest.main()
