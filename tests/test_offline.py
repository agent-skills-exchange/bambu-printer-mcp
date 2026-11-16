"""Portable checks: no printer, credentials, network or Briar runtime."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client import stdio as stdio_transport

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from status_service import StatusCache


class OfflineTests(unittest.TestCase):
    def test_synthetic_cache_is_explicit(self):
        cache = StatusCache(synthetic=True)
        cache.connection(True)
        cache.ingest('{"print":{"gcode_state":"IDLE","mc_percent":0}}')
        result = cache.snapshot()
        self.assertTrue(result["synthetic"])
        self.assertEqual(result["telemetry"]["state"], "IDLE")

    def test_disconnected_cache_has_no_telemetry(self):
        result = StatusCache().snapshot()
        self.assertEqual(result["freshness"], "disconnected")
        self.assertEqual(result["telemetry"], {})

    def test_service_lock_matches_package(self):
        lock = json.loads((ROOT / "service-lock.json").read_text())
        for name, expected in lock["files"].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)

    def test_manifest_does_not_advertise_printer_mode(self):
        manifest = json.loads((ROOT / "dependencies.json").read_text())
        self.assertEqual(manifest["features"], ["guidance", "offline-status"])
        self.assertEqual(manifest["skills"], [])
        self.assertEqual(manifest["credentials"], [])
        self.assertTrue(all(not item["required"] for item in manifest["network"]))


class OfflineProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_status_and_rejection_then_process_exit(self):
        processes = []
        original = stdio_transport._create_platform_compatible_process

        async def record_process(*args, **kwargs):
            process = await original(*args, **kwargs)
            processes.append(process)
            return process

        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(ROOT / "scripts/status_service.py"), "--fixture"],
            env={"PYTHONDONTWRITEBYTECODE": "1"},
        )
        # Observe the real child, without replacing its execution or cleanup.
        with patch.object(stdio_transport, "_create_platform_compatible_process", record_process):
            with anyio.fail_after(20):
                async with stdio_transport.stdio_client(parameters) as (reader, writer):
                    async with ClientSession(reader, writer) as client:
                        await client.initialize()
                        tools = (await client.list_tools()).tools
                        self.assertEqual([tool.name for tool in tools], ["get_printer_status"])
                        self.assertEqual(tools[0].inputSchema.get("properties", {}), {})
                        result = await client.call_tool("get_printer_status", {})
                        self.assertFalse(result.isError)
                        # A bare dict return uses JSON text with this pinned SDK.
                        status = result.structuredContent or json.loads(result.content[0].text)
                        self.assertTrue(status["synthetic"])
                        self.assertEqual(status["telemetry"]["state"], "IDLE")
                        denied = await client.call_tool("print_file", {})
                        self.assertTrue(denied.isError)
                        injected = await client.call_tool("get_printer_status", {"command": "print"})
                        self.assertTrue(injected.isError)
        self.assertEqual(len(processes), 1)
        self.assertEqual(processes[0].returncode, 0)


if __name__ == "__main__":
    unittest.main()
