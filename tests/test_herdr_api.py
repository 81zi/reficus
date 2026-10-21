import json
import os
import shutil
import socket
import tempfile
import threading
import unittest

import helpers  # noqa: F401  (puts src/ on sys.path)

import herdr_api
from herdr_api import HerdrError, rpc


class FakeHerdr:
    """One-shot Unix socket server; `reply(request)` returns raw bytes to send."""

    def __init__(self, reply):
        # Short dir: AF_UNIX paths are limited to ~104 bytes on macOS.
        self.dir = tempfile.mkdtemp(dir="/tmp")
        self.path = os.path.join(self.dir, "s")
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen(1)
        self.requests = []
        self.thread = threading.Thread(target=self._serve, args=(reply,), daemon=True)
        self.thread.start()

    def _serve(self, reply):
        conn, _ = self.server.accept()
        with conn:
            buf = b""
            while not buf.endswith(b"\n"):
                buf += conn.recv(65536)
            request = json.loads(buf)
            self.requests.append(request)
            data = reply(request)
            if data:
                conn.sendall(data)

    def close(self):
        self.thread.join(timeout=2)
        self.server.close()
        shutil.rmtree(self.dir, ignore_errors=True)


def answer(**fields):
    return lambda req: (json.dumps(dict({"id": req["id"]}, **fields)) + "\n").encode()


class RpcTest(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def serve(self, reply):
        fake = FakeHerdr(reply)
        self.addCleanup(fake.close)
        os.environ["HERDR_SOCKET_PATH"] = fake.path
        return fake

    def test_returns_result_and_sends_request(self):
        fake = self.serve(answer(result={"pane": {"pane_id": "w1:p1"}}))
        self.assertEqual(rpc("pane.current", {"x": 1}), {"pane": {"pane_id": "w1:p1"}})
        self.assertEqual(fake.requests[0]["method"], "pane.current")
        self.assertEqual(fake.requests[0]["params"], {"x": 1})

    def test_error_response(self):
        self.serve(answer(error={"code": "not_found"}))
        with self.assertRaisesRegex(HerdrError, "pane.get: .*not_found"):
            rpc("pane.get")

    def test_mismatched_id(self):
        self.serve(lambda req: b'{"id": "other", "result": {}}\n')
        with self.assertRaisesRegex(HerdrError, "unexpected response"):
            rpc("pane.list")

    def test_empty_response(self):
        self.serve(lambda req: b"")
        with self.assertRaisesRegex(HerdrError, "no valid response"):
            rpc("pane.list")

    def test_missing_socket_env(self):
        os.environ.pop("HERDR_SOCKET_PATH", None)
        with self.assertRaisesRegex(HerdrError, "HERDR_SOCKET_PATH"):
            rpc("pane.list")

    def test_unreachable_socket_is_herdr_error(self):
        os.environ["HERDR_SOCKET_PATH"] = "/nonexistent/herdr.sock"
        with self.assertRaisesRegex(HerdrError, "cannot reach herdr"):
            rpc("pane.list")

    def test_timeout_is_herdr_error(self):
        release = threading.Event()
        self.addCleanup(release.set)
        self.serve(lambda req: release.wait(5) and b"")
        old, herdr_api.TIMEOUT = herdr_api.TIMEOUT, 0.2
        self.addCleanup(setattr, herdr_api, "TIMEOUT", old)
        with self.assertRaisesRegex(HerdrError, "did not answer"):
            rpc("pane.list")

    def test_toast_swallows_errors(self):
        os.environ.pop("HERDR_SOCKET_PATH", None)
        herdr_api.toast("hello")


if __name__ == "__main__":
    unittest.main()
