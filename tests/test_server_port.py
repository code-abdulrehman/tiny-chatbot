"""Port fallback checks without starting a web server."""
import errno
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server_port import choose_port


class PortTests(unittest.TestCase):
    def test_skips_busy_port(self):
        with patch('server_port.socket.socket') as factory:
            probe = factory.return_value.__enter__.return_value
            probe.bind.side_effect = [OSError(errno.EADDRINUSE, 'Busy'), None]
            self.assertEqual(choose_port(8501), 8502)

    def test_rejects_invalid_port(self):
        for port in [0, -1, 65536]:
            with self.assertRaises(ValueError):
                choose_port(port)

    def test_reports_permission_failure(self):
        with patch('server_port.socket.socket') as factory:
            probe = factory.return_value.__enter__.return_value
            probe.bind.side_effect = PermissionError(errno.EACCES, 'Denied')
            with self.assertRaises(PermissionError):
                choose_port()

    def test_reports_exhausted_ports(self):
        with patch('server_port.socket.socket') as factory:
            probe = factory.return_value.__enter__.return_value
            probe.bind.side_effect = OSError(errno.EADDRINUSE, 'Busy')
            with self.assertRaises(RuntimeError):
                choose_port(65535)
