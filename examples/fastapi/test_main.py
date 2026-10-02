import json
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request


class HealthTest(unittest.TestCase):
    def test_health(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        server = subprocess.Popen([
            sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port),
        ], stdout=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health?verbose=true", timeout=1) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(json.load(response), {"ok": True})
                    break
                except urllib.error.URLError:
                    if server.poll() is not None or time.monotonic() >= deadline:
                        self.fail("Uvicorn did not start")
                    time.sleep(0.05)
        finally:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
