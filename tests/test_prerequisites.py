"""Focused WP-0.4 local prerequisite report tests."""

from __future__ import annotations

import io
import subprocess
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from tools.check_prerequisites import (
    FIELDS,
    CollectionError,
    collect,
    main,
    render,
    validate,
)


def completed(command, capture_output, text, check, timeout):
    versions = {"git": "git version 2.50.1\n", "python3": "Python 3.13.7\n"}
    return subprocess.CompletedProcess(command, 0, stdout=versions[command[0]], stderr="")


def sample() -> dict[str, str]:
    return {
        "Schema-Version": "1",
        "OS-Family": "Darwin",
        "OS-Version": "15.7.1",
        "CPU-Architecture": "arm64",
        "Git-Version": "2.50.1",
        "Python-Version": "3.13.7",
        "Executable-git": "Available",
        "Executable-python3": "Available",
        "Executable-terraform": "Unavailable",
        "Executable-az": "Unavailable",
    }


class PrerequisiteTests(unittest.TestCase):
    @patch("tools.check_prerequisites.platform.machine", return_value="arm64")
    @patch("tools.check_prerequisites.platform.mac_ver", return_value=("15.7.1", (), ""))
    @patch("tools.check_prerequisites.platform.system", return_value="Darwin")
    def test_collection_and_validation(self, _system, _mac, _machine):
        report = collect(lambda name: name if name in {"git", "python3"} else None, completed)
        self.assertEqual(report, sample())
        self.assertEqual(validate(render(report)), [])

    @patch("tools.check_prerequisites.platform.release", return_value="6.12.0")
    @patch("tools.check_prerequisites.platform.machine", return_value="x86_64")
    @patch("tools.check_prerequisites.platform.system", return_value="Linux")
    def test_unavailable_tools_are_exact(self, _system, _machine, _release):
        report = collect(lambda _name: None, completed)
        for name in ("git", "python3", "terraform", "az"):
            self.assertEqual(report[f"Executable-{name}"], "Unavailable")
        self.assertEqual(report["Git-Version"], "Unavailable")
        self.assertEqual(report["Python-Version"], "Unavailable")

    def test_malformed_line_fails(self):
        self.assertTrue(any("malformed" in item for item in validate(render(sample()) + "bad\n")))

    def test_duplicate_field_fails(self):
        text = render(sample()) + "OS-Family: Darwin\n"
        self.assertTrue(any("duplicate" in item for item in validate(text)))

    def test_unknown_field_fails(self):
        text = render(sample()) + "Hostname: workstation\n"
        self.assertTrue(any("unknown" in item for item in validate(text)))

    def test_empty_field_fails(self):
        text = render(sample()).replace("OS-Version: 15.7.1", "OS-Version: ")
        self.assertTrue(any("empty field" in item for item in validate(text)))

    def test_render_is_deterministic_and_ordered(self):
        expected = [f"{field}:" for field in FIELDS]
        first = render(dict(reversed(list(sample().items()))))
        self.assertEqual(first, render(sample()))
        self.assertEqual([line.split()[0] for line in first.splitlines()], expected)

    def test_out_of_order_fields_fail(self):
        lines = render(sample()).splitlines()
        lines[1], lines[2] = lines[2], lines[1]
        self.assertIn("fields are not in required order", validate("\n".join(lines) + "\n"))

    def test_privacy_sensitive_shapes_fail_visibly(self):
        for sensitive in (
            "OS-Version: /Users/example/private",
            "OS-Version: person@example.test",
            "OS-Version: Bearer abcdefghijklmnopqrstuvwxyz",
            "OS-Version: eyJabc.def.ghi",
        ):
            with self.subTest(sensitive=sensitive):
                text = render(sample()).replace("OS-Version: 15.7.1", sensitive)
                self.assertTrue(any("privacy-sensitive" in item for item in validate(text)))

    def test_version_command_failure_and_cli_failure_are_visible(self):
        def failed(command, **_kwargs):
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="failure")

        with self.assertRaises(CollectionError):
            collect(lambda name: name, failed)
        stderr = io.StringIO()
        with patch("tools.check_prerequisites.collect", side_effect=CollectionError("git version command failed")):
            with redirect_stderr(stderr):
                self.assertEqual(main([]), 2)
        self.assertIn("ERROR: git version command failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
