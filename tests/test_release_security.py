from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAW_API = ROOT / "scripts" / "law_api.sh"


class PublicReleaseSurfaceTests(unittest.TestCase):
    def test_runtime_paths_are_ignored_by_tracked_gitignore(self) -> None:
        candidates = (
            ".env",
            ".env.local",
            ".harness/sentinel",
            ".omc/sentinel",
            ".omx/sentinel",
            "node_modules/sentinel",
            "tests/__pycache__/sentinel.pyc",
            "runtime.log",
            "runtime.jsonl",
        )
        for candidate in candidates:
            result = subprocess.run(
                ["git", "check-ignore", "-v", "--no-index", candidate],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn(".gitignore:", result.stdout, candidate)
            self.assertNotIn(".git/info/exclude", result.stdout, candidate)

    def test_package_is_private_and_pack_excludes_runtime_state(self) -> None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertIs(package.get("private"), True)
        self.assertEqual(package["engines"]["node"], ">=20.9.0")
        self.assertEqual(package["engines"]["npm"], ">=10")

        result = subprocess.run(
            ["npm", "pack", "--dry-run", "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        paths = [item["path"] for item in payload[0]["files"]]
        forbidden_dirs = (".harness/", ".omc/", ".omx/", "node_modules/")
        for path in paths:
            self.assertFalse(path.endswith(".jsonl"), path)
            self.assertFalse(path != ".env.example" and (path == ".env" or path.startswith(".env.")), path)
            self.assertFalse(any(path.startswith(item) for item in forbidden_dirs), path)

    def test_annex_verifier_does_not_invoke_a_shell_for_paths(self) -> None:
        script = (ROOT / "scripts" / "verify_annex.mjs").read_text(encoding="utf-8")
        self.assertIn("execFileSync('pdftotext'", script)
        self.assertNotIn("execSync(`pdftotext", script)


class ApiWrapperSecurityTests(unittest.TestCase):
    def api_env(self, cache_dir: Path, bin_dir: Path | None = None) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "LAW_API_OC": "secret-user",
                "LAW_API_CACHE_DIR": str(cache_dir),
                "LAW_API_TIMEOUT": "1",
            }
        )
        if bin_dir is not None:
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
        return env

    def run_api(self, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(LAW_API), *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_untrusted_structural_arguments_are_rejected_before_http(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "executed"
            env = self.api_env(root / "cache")
            cases = (
                ("search", "law&target=prec", "query", "10"),
                ("search", "law", "query", "101"),
                ("get", "law", f"1;touch {marker}"),
                ("get", "law", "1", "2026-01-01"),
                ("get-article", "law", "1", "1';__import__(\"os\").system(\"touch x\")"),
                ("get-annex", "1", "2", "zip", str(root)),
            )
            for args in cases:
                result = self.run_api(*args, env=env)
                self.assertEqual(result.returncode, 2, (args, result.stderr))
                self.assertIn("invalid", result.stderr)
            self.assertFalse(marker.exists())

    def test_error_output_redacts_raw_and_encoded_oc_forms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_curl = bin_dir / "curl"
            fake_curl.write_text(
                "#!/usr/bin/env bash\n"
                "cat >/dev/null\n"
                "printf '%s\\n' '{\"error\":\"?oc=secret-user&x=1\",\"LAW_API_OC\":\"secret-user\"}'\n"
                "printf '%s\\n' '__HTTP_CODE__:500'\n",
                encoding="utf-8",
            )
            fake_curl.chmod(0o700)
            result = self.run_api(
                "search", "law", "환경", "1", env=self.api_env(root / "cache", bin_dir)
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("secret-user", result.stderr)
            self.assertIn("<redacted>", result.stderr)

    def test_search_query_is_encoded_as_data_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            marker = root / "executed"
            capture = root / "curl-args"
            fake_curl = bin_dir / "curl"
            fake_curl.write_text(
                "#!/usr/bin/env bash\n"
                "cat > \"$FAKE_CURL_CAPTURE\"\n"
                "printf '%s\\n' '{\"LawSearch\":{\"totalCnt\":\"1\"}}'\n"
                "printf '%s\\n' '__HTTP_CODE__:200'\n",
                encoding="utf-8",
            )
            fake_curl.chmod(0o700)
            env = self.api_env(root / "cache", bin_dir)
            env["FAKE_CURL_CAPTURE"] = str(capture)
            query = f"환경&target=prec\n$(touch {marker})"
            result = self.run_api("search", "law", query, "1", env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            config = capture.read_text(encoding="utf-8")
            self.assertIn("query=%ED%99%98%EA%B2%BD%26target%3Dprec%0A%24%28touch%20", config)
            self.assertNotIn("&target=prec", config)
            self.assertFalse(marker.exists())

    def test_cache_permissions_are_private(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_curl = bin_dir / "curl"
            fake_curl.write_text(
                "#!/usr/bin/env bash\n"
                "cat >/dev/null\n"
                "printf '%s\\n' '{\"LawSearch\":{\"totalCnt\":\"1\"}}'\n"
                "printf '%s\\n' '__HTTP_CODE__:200'\n",
                encoding="utf-8",
            )
            fake_curl.chmod(0o700)
            cache = root / "cache"
            result = self.run_api(
                "search", "law", "환경", "1", env=self.api_env(cache, bin_dir)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(stat.S_IMODE(cache.stat().st_mode), 0o700)
            cache_files = list(cache.iterdir())
            self.assertEqual(len(cache_files), 1)
            self.assertEqual(stat.S_IMODE(cache_files[0].stat().st_mode), 0o600)

    def test_annex_http_error_does_not_leave_a_download(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_curl = bin_dir / "curl"
            fake_curl.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \" $* \" == *' --config - '* ]]; then\n"
                "  cat >/dev/null\n"
                "  printf '%s\\n' '{\"법령\":{\"별표\":{\"별표단위\":[{\"별표번호\":\"0001\",\"별표가지번호\":\"00\",\"별표서식파일링크\":\"/error.hwp\",\"별표HWP파일명\":\"error.hwp\",\"별표제목\":\"시험\"}]}}}'\n"
                "  printf '%s\\n' '__HTTP_CODE__:200'\n"
                "  exit 0\n"
                "fi\n"
                "while (($#)); do\n"
                "  if [[ \"$1\" == '-o' ]]; then printf 'HTTP 404' > \"$2\"; break; fi\n"
                "  shift\n"
                "done\n"
                "exit 22\n",
                encoding="utf-8",
            )
            fake_curl.chmod(0o700)
            result = self.run_api(
                "get-annex",
                "1",
                "1",
                "hwp",
                str(root),
                env=self.api_env(root / "cache", bin_dir),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "1_1.hwp").exists())
            self.assertEqual(list(root.glob("1_1.hwp.tmp.*")), [])

    def test_redactor_masks_case_encoded_and_field_variants(self) -> None:
        samples = (
            "https://example.test/?OC=secret-user&target=law",
            "https://example.test/?oc=secret-user&target=law",
            "https://example.test/?Oc%3Dsecret-user&target=law",
            '{"LAW_API_OC":"secret-user"}',
            "LAW_API_OC=secret-user",
        )
        for sample in samples:
            command = (
                "source scripts/load_law_env.sh; "
                "printf '%s' \"$1\" | redact_law_text"
            )
            result = subprocess.run(
                ["bash", "-c", command, "--", sample],
                cwd=ROOT,
                env={**os.environ, "LAW_API_OC": "secret-user"},
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertNotIn("secret-user", result.stdout, sample)
            self.assertIn("<redacted>", result.stdout, sample)

    def test_agent_e2e_suppresses_credential_from_cli_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            for name in ("codex", "claude"):
                executable = bin_dir / name
                executable.write_text(
                    "#!/usr/bin/env bash\n"
                    "printf 'tool failed with %s\\n' \"$LAW_API_OC\" >&2\n"
                    "exit 1\n",
                    encoding="utf-8",
                )
                executable.chmod(0o700)
            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            env["LAW_API_OC"] = "e2e-plain-test-credential"
            result = subprocess.run(
                ["bash", "scripts/test_agent_e2e.sh"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("e2e-plain-test-credential", combined)
            self.assertIn("credential-bearing output was suppressed", combined)


if __name__ == "__main__":
    unittest.main()
