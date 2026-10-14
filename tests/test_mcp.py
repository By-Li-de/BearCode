import asyncio
import json
import sys
import unittest
from types import SimpleNamespace

from agents.mcp_client import McpConnection


SERVER = r'''
import json, sys
previous = None
for line in sys.stdin:
    request = json.loads(line)
    if 'id' not in request:
        continue
    method = request['method']
    if method == 'hang':
        previous = request['id']
        continue
    if method == 'exit':
        sys.exit(0)
    if method == 'noise':
        sys.stderr.write('diagnostic' * 30000)
        sys.stderr.flush()
        print('not JSON', flush=True)
        print('[]', flush=True)
    if previous is not None:
        print(json.dumps({'id': previous, 'result': 'late'}), flush=True)
        previous = None
    result = {'tools': []} if method == 'tools/list' else {'content': [{'type': 'text', 'text': 'ok'}]}
    if method == 'long':
        result = {'content': [{'type': 'text', 'text': 'x' * 70000}]}
    print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}), flush=True)
'''


class McpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = McpConnection('test', sys.executable, ['-u', '-c', SERVER], request_timeout=0.5)
        await self.conn.connect()

    async def asyncTearDown(self):
        process = self.conn._process
        await self.conn.aclose()
        if process:
            self.assertIsNotNone(process.returncode)

    async def test_handshake_and_tool_call(self):
        await self.conn.initialize()
        self.assertEqual(await self.conn.list_tools(), [])
        self.assertEqual(await self.conn.call_tool('example', {}), 'ok')

    async def test_timeout_then_late_response_does_not_break_next_request(self):
        self.conn.request_timeout = 0.05
        with self.assertRaises(TimeoutError):
            await self.conn._send_request('hang')
        self.assertFalse(self.conn._pending)
        self.conn.request_timeout = 0.5
        self.assertEqual(await self.conn.call_tool('example', {}), 'ok')

    async def test_disconnect_fails_pending_request(self):
        with self.assertRaises(ConnectionError):
            await self.conn._send_request('exit')
        self.assertFalse(self.conn._pending)

    async def test_cancel_cleans_request_and_connection_can_continue(self):
        task = asyncio.create_task(self.conn._send_request('hang'))
        while not self.conn._pending:
            await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.conn._pending)
        self.assertEqual(await self.conn.call_tool('example', {}), 'ok')

    async def test_stderr_and_malformed_lines_do_not_block_responses(self):
        response = await self.conn._send_request('noise')
        self.assertEqual(response['content'][0]['text'], 'ok')

    async def test_response_larger_than_default_stream_buffer(self):
        response = await self.conn._send_request('long')
        self.assertEqual(len(response['content'][0]['text']), 70000)

    async def test_close_fails_pending_request(self):
        task = asyncio.create_task(self.conn._send_request('hang'))
        while not self.conn._pending:
            await asyncio.sleep(0)
        await self.conn.aclose()
        with self.assertRaises(ConnectionError):
            await task
        self.assertFalse(self.conn._pending)

    async def test_response_during_drain_is_not_lost(self):
        reader = asyncio.StreamReader()

        class Writer:
            def write(self, data):
                self.request = json.loads(data)

            async def drain(self):
                reader.feed_data(json.dumps({'id': self.request['id'], 'result': 'fast'}).encode() + b'\n')
                await asyncio.sleep(0)

        conn = McpConnection('fast', 'unused', request_timeout=0.1)
        conn._process = SimpleNamespace(stdin=Writer(), stdout=reader, returncode=None)
        reading = asyncio.create_task(conn._read_loop())
        try:
            self.assertEqual(await conn._send_request('test'), 'fast')
        finally:
            reading.cancel()
            await asyncio.gather(reading, return_exceptions=True)


if __name__ == '__main__':
    unittest.main()
