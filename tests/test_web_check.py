import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

import check_web

BASE = Path(__file__).resolve().parents[1]
TEMPLATE = BASE / "web_template.html"


class ExtractTests(unittest.TestCase):
    def test_finds_the_template_scripts_and_neutralizes_markers(self):
        scripts = check_web.extract_scripts(TEMPLATE.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(scripts), 2)
        self.assertTrue(any("const DATA" in script for script in scripts))
        self.assertTrue(any("const STEAM_EVENTS" in script for script in scripts))
        for script in scripts:
            self.assertNotIn("/*__STEAM_", script)

    def test_skips_empty_blocks(self):
        self.assertEqual(check_web.extract_scripts('<script src="x.js"></script><script> </script>'), [])

    def test_fails_when_no_scripts_exist(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(check_web.check("<p>sin javascript</p>"), 1)


@unittest.skipUnless(shutil.which("node"), "Node no está instalado")
class NodeTests(unittest.TestCase):
    def test_template_is_valid_javascript(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check_web.main([str(TEMPLATE)]), 0)

    def test_a_syntax_error_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            page = Path(temp) / "page.html"
            page.write_text("<script>const x = ;</script>", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(check_web.main([str(page)]), 1)

    def test_a_missing_file_is_reported(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(check_web.main(["/no/existe/page.html"]), 1)


if __name__ == "__main__":
    unittest.main()
