"""Inactive skill package's narrow stdio MCP; no printer command surface.

Importing this module starts no connection. The CLI requires an explicit fixture
mode or a named runtime configuration file. No Bambu library is imported.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import signal
import ssl
import threading
import time

import paho.mqtt.client as mqtt


class StatusCache:
    STATES = {"IDLE", "PREPARE", "RUNNING", "PAUSE", "FINISH", "FAILED", "SLICING", "INIT"}
    FIELDS = {
        "gcode_state": ("state", str),
        "mc_percent": ("progress_percent", int),
        "layer_num": ("current_layer", int),
        "total_layer_num": ("total_layers", int),
        "mc_remaining_time": ("remaining_minutes", int),
    }

    def __init__(self, stale_after=30.0, synthetic=False, clock=time.monotonic):
        if not math.isfinite(stale_after) or stale_after <= 0:
            raise ValueError("stale_after must be positive and finite")
        self.stale_after = stale_after
        self.synthetic = synthetic
        self.clock = clock
        self.lock = threading.Lock()
        self.connected = False
        self.updated = None
        self.received_at = None
        self.values = {}
        self.field_updated = {}

    def connection(self, connected):
        with self.lock:
            if connected and not self.connected:
                # Never label retained data from a previous connection as current.
                self.updated = None
                self.received_at = None
                self.values = {}
                self.field_updated = {}
            self.connected = bool(connected)

    def ingest(self, payload):
        try:
            record = json.loads(payload)
        except (ValueError, UnicodeError, TypeError):
            return False
        if not isinstance(record, dict) or not isinstance(record.get("print"), dict):
            return False
        values = {}
        for source, (target, kind) in self.FIELDS.items():
            value = record["print"].get(source)
            if type(value) is not kind:
                continue
            if kind is int and (value < 0 or (source == "mc_percent" and value > 100)):
                continue
            if source == "gcode_state" and value not in self.STATES:
                continue
            values[target] = value
        if not values:
            return False
        with self.lock:
            if not self.connected:
                return False
            self.values.update(values)
            self.updated = self.clock()
            self.field_updated.update({key: self.updated for key in values})
            self.received_at = datetime.now(timezone.utc).isoformat()
        return True

    def snapshot(self):
        with self.lock:
            age = None if self.updated is None else max(0.0, self.clock() - self.updated)
            ages = {key: round(max(0.0, self.clock() - updated), 3) for key, updated in self.field_updated.items()}
            stale_fields = [key for key, age in ages.items() if age > self.stale_after]
            state = "disconnected" if not self.connected else "no_telemetry" if age is None else "stale" if stale_fields else "current"
            return {
                "synthetic": self.synthetic,
                "connection": "connected" if self.connected else "disconnected",
                "freshness": state,
                "age_seconds": None if age is None else round(age, 3),
                "received_at": self.received_at,
                "telemetry": dict(self.values),
                "field_age_seconds": ages,
                "stale_fields": stale_fields,
            }


@dataclass(frozen=True)
class ConnectionConfig:
    host: str
    serial: str
    password_env: str
    port: int = 8883
    username: str = "bblp"
    cafile: str | None = None
    fixture: bool = False

    def __post_init__(self):
        if not isinstance(self.host, str) or not self.host or "/" in self.host:
            raise ValueError("A single MQTT hostname is required")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("Invalid MQTT port")
        if not isinstance(self.serial, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", self.serial):
            raise ValueError("A single exact serial without topic wildcards is required")
        if not isinstance(self.password_env, str) or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", self.password_env):
            raise ValueError("password_env must be an environment-variable reference")
        if not isinstance(self.username, str) or not self.username:
            raise ValueError("MQTT username is required")
        if self.cafile is not None and (not isinstance(self.cafile, str) or not Path(self.cafile).is_absolute()):
            raise ValueError("cafile must be an absolute runtime-local path")
        if type(self.fixture) is not bool or (self.fixture and self.host not in ("localhost", "127.0.0.1", "::1")):
            raise ValueError("Synthetic MQTT fixtures must use a loopback hostname")

    @property
    def topic(self):
        return f"device/{self.serial}/report"

    @classmethod
    def from_file(cls, path):
        record = json.loads(Path(path).read_text())
        if not isinstance(record, dict):
            raise ValueError("Runtime configuration must be an object")
        # Dataclass construction rejects unexpected keys, including raw passwords.
        return cls(**record)


class SubscribeOnlyClient(mqtt.Client):
    def publish(self, *args, **kwargs):
        raise PermissionError("Publishing is not part of this status service")


class MqttCollector:
    def __init__(self, config, cache):
        self.config = config
        self.cache = cache
        self.ready = threading.Event()
        self.failure = None
        self.client = None
        self.stop_lock = threading.RLock()
        self.socket_lock = threading.Lock()
        self.tls_sockets = []
        self.stopping = threading.Event()

    def start(self):
        if self.stopping.is_set():
            raise RuntimeError("A stopped collector cannot be restarted")
        password = os.environ.get(self.config.password_env)
        if not password:
            raise ValueError("Required runtime credential reference is unavailable")
        context = ssl.create_default_context(cafile=self.config.cafile)
        original_wrap = context.wrap_socket

        def track_socket(*args, **kwargs):
            # Paho defers the TLS handshake until after wrap_socket returns.
            # Retain ownership so failure before Client._sock assignment cannot
            # leave that socket awaiting finalization. Validation is delegated
            # unchanged to the original standard-library SSLContext method.
            owned_socket = original_wrap(*args, **kwargs)
            with self.socket_lock:
                if self.stopping.is_set():
                    owned_socket.close()
                    raise RuntimeError("Collector stopped during TLS startup")
                self.tls_sockets.append(owned_socket)
            return owned_socket

        context.wrap_socket = track_socket
        # Never CERT_NONE, tls_insecure_set, extracted certificates or silent trust changes.
        self.client = SubscribeOnlyClient(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311, reconnect_on_failure=False)
        self.client.connect_timeout = 5.0
        self.client.tls_set_context(context)
        self.client.username_pw_set(self.config.username, password)
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        try:
            self.client.connect(self.config.host, self.config.port, keepalive=30)
            self.client.loop_start()
            if not self.ready.wait(5):
                raise TimeoutError("MQTT subscription did not become ready")
            if self.failure:
                raise RuntimeError(self.failure)
        except BaseException:
            self.stop()
            raise

    def _on_connect(self, client, userdata, flags, reason, properties):
        if reason.is_failure:
            self.failure = "MQTT connection rejected"
            self.ready.set()
            return
        result, _ = client.subscribe(self.config.topic, qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            self.failure = "MQTT subscription request failed"
            self.ready.set()

    def _on_subscribe(self, client, userdata, mid, reasons, properties):
        if any(reason.is_failure for reason in reasons):
            self.failure = "MQTT subscription rejected"
        else:
            self.cache.connection(True)
        self.ready.set()

    def _on_disconnect(self, client, userdata, flags, reason, properties):
        self.cache.connection(False)
        if not self.ready.is_set():
            self.failure = "MQTT disconnected before subscription"
            self.ready.set()

    def _on_message(self, client, userdata, message):
        if message.topic == self.config.topic:
            self.cache.ingest(message.payload)

    def stop(self):
        with self.stop_lock:
            self.stopping.set()
            self.cache.connection(False)
            try:
                if self.client:
                    try:
                        self.client.disconnect()
                    finally:
                        self.client.loop_stop()
            finally:
                with self.socket_lock:
                    sockets, self.tls_sockets = self.tls_sockets, []
                for owned_socket in sockets:
                    owned_socket.close()
                self.client = None


def build_server(cache, collector=None):
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.exceptions import ToolError
    from mcp.types import ToolAnnotations

    class StatusServer(FastMCP):
        async def call_tool(self, name, arguments):
            # FastMCP's generated argument model otherwise ignores extra keys.
            # Validate the raw request before SDK coercion discards them.
            if name != "get_printer_status" or arguments != {}:
                raise ToolError("Only get_printer_status with no arguments is supported")
            return await super().call_tool(name, arguments)

    @asynccontextmanager
    async def lifespan(server):
        try:
            if collector:
                await asyncio.to_thread(collector.start)
            yield {}
        finally:
            if collector:
                await asyncio.to_thread(collector.stop)

    server = StatusServer("bambu-status-only", lifespan=lifespan, log_level="WARNING")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def get_printer_status() -> dict:
        """Read cached status for the explicitly selected printer; never sends commands."""
        return cache.snapshot()

    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", action="store_true", help="Synthetic cached status; no network or credentials")
    mode.add_argument("--mqtt-config", type=Path, help="Explicit runtime-local connection file; requires separate connection authority")
    args = parser.parse_args()
    cache = StatusCache(synthetic=args.fixture)
    collector = None
    if args.fixture:
        cache.connection(True)
        cache.ingest('{"print":{"gcode_state":"IDLE","mc_percent":0}}')
    else:
        config = ConnectionConfig.from_file(args.mqtt_config)
        cache.synthetic = config.fixture
        collector = MqttCollector(config, cache)

    def terminate(signum, frame):
        # Codex removal may signal the process rather than closing stdin first.
        # Disconnect the owned MQTT session before allowing process termination.
        if collector:
            collector.stop()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    # Fixed stdio: no HTTP transport option and no auxiliary listener.
    build_server(cache, collector).run(transport="stdio")


if __name__ == "__main__":
    main()
