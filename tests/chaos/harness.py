"""Chaos levers: containers on fixed ports that tests stop, pause, and restart."""

import socket
import time
from dataclasses import dataclass
from typing import Any

POSTGRES_IMAGE = "pgvector/pgvector:0.8.0-pg17"
REDIS_IMAGE = "redis:7.4-alpine"
REDPANDA_IMAGE = "docker.redpanda.com/redpandadata/redpanda:v24.2.18"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def wait_for(condition: Any, timeout: float = 60.0, interval: float = 0.25) -> float:
    """Poll until condition() is truthy; returns the seconds it took."""
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        try:
            if condition():
                return time.monotonic() - started
        except Exception:  # noqa: S110 - the dependency is expected to fail while down
            pass
        time.sleep(interval)
    raise TimeoutError(f"condition not met within {timeout} s")


@dataclass
class Controlled:
    """A running container plus the chaos levers."""

    container: Any
    url: str

    @property
    def docker(self) -> Any:
        return self.container.get_wrapped_container()

    def stop(self) -> None:
        self.docker.stop(timeout=1)

    def start(self) -> None:
        self.docker.start()

    def restart(self) -> None:
        self.docker.restart(timeout=1)

    def pause(self) -> None:
        self.docker.pause()

    def unpause(self) -> None:
        self.docker.unpause()

    def ensure_running(self) -> None:
        """Undo a test's chaos so teardown and the next test find it up."""
        self.docker.reload()
        if self.docker.status == "paused":
            self.unpause()
        elif self.docker.status != "running":
            self.start()


def _pg_ready(url: str) -> bool:
    import psycopg

    with psycopg.connect(url.replace("postgresql+psycopg", "postgresql"), connect_timeout=2):
        return True


def wait_for_postgres(pg: Controlled, timeout: float = 60.0) -> float:
    return wait_for(lambda: _pg_ready(pg.url), timeout)


class OidcStub:
    """OIDC discovery and JWKS for a throwaway key, so a real API process can verify tokens."""

    def __init__(self, public_key: Any, kid: str) -> None:
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        import jwt

        jwk = {**jwt.algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True), "kid": kid}
        port = free_port()
        self.issuer = f"http://127.0.0.1:{port}/realms/opspilot"
        documents = {
            "/realms/opspilot/.well-known/openid-configuration": {
                "issuer": self.issuer,
                "jwks_uri": f"{self.issuer}/protocol/openid-connect/certs",
            },
            "/realms/opspilot/protocol/openid-connect/certs": {"keys": [jwk]},
        }

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                body = json.dumps(documents.get(self.path, {})).encode()
                self.send_response(200 if self.path in documents else 404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class ApiProcess:
    """The API as a separate process (`python -m opspilot_api`) we can SIGKILL and start again."""

    def __init__(self, env: dict[str, str], log_path: str) -> None:
        import os

        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.env = {**os.environ, **env, "API_HOST": "127.0.0.1", "API_PORT": str(self.port)}
        self.log_path = log_path
        self.process: Any = None
        self.log: Any = None

    def start(self, timeout: float = 60.0) -> float:
        import subprocess
        import sys
        import urllib.request

        self._close_log()
        self.log = open(self.log_path, "ab")  # noqa: SIM115 - closed when the process ends
        self.process = subprocess.Popen(
            [sys.executable, "-m", "opspilot_api"], env=self.env, stdout=self.log, stderr=self.log
        )

        def healthy() -> bool:
            with urllib.request.urlopen(f"{self.url}/api/v1/health", timeout=1) as r:  # noqa: S310
                return bool(r.status == 200)

        return wait_for(healthy, timeout)

    def kill(self) -> None:
        """SIGKILL: no graceful shutdown, open streams just drop."""
        self.process.kill()
        self.process.wait(timeout=10)
        self._close_log()

    def _close_log(self) -> None:
        if self.log is not None:
            self.log.close()
            self.log = None

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=10)
        self._close_log()


class FlakyModelServer:
    """An Ollama-compatible endpoint that fails on demand: `mode` is "503" or "hang"."""

    def __init__(self, mode: str, hang_seconds: float = 5.0) -> None:
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        self.mode = mode
        self.requests = 0
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                server.requests += 1
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if server.mode == "hang":
                    time.sleep(hang_seconds)
                self.send_response(503)
                self.end_headers()

            def log_message(self, *args: Any) -> None:
                pass

        port = free_port()
        self.url = f"http://127.0.0.1:{port}"
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class HangingKubeApi:
    """A Kubernetes API server that accepts every PATCH and never answers in time."""

    def __init__(self, hang_seconds: float = 30.0) -> None:
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        self.patches: list[bytes] = []
        self.received: list[float] = []
        server = self
        lock = threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def do_PATCH(self) -> None:
                with lock:
                    server.patches.append(self.rfile.read(int(self.headers["Content-Length"])))
                    server.received.append(time.monotonic())
                try:
                    time.sleep(hang_seconds)
                    self.send_response(504)
                    self.end_headers()
                except OSError:
                    pass  # the client gave up first

            def log_message(self, *args: Any) -> None:
                pass

        port = free_port()
        self.url = f"http://127.0.0.1:{port}"
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def kubeconfig(self, path: str) -> str:
        with open(path, "w") as f:
            f.write(
                "apiVersion: v1\nkind: Config\ncurrent-context: chaos\n"
                f"clusters: [{{name: chaos, cluster: {{server: '{self.url}'}}}}]\n"
                "users: [{name: chaos, user: {}}]\n"
                "contexts: [{name: chaos, context: {cluster: chaos, user: chaos}}]\n"
            )
        return path

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
