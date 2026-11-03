"""View regression checks; optional Node executes the real page's JavaScript."""
import shutil
import subprocess
import unittest
from pathlib import Path


class GuidedTree(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is unavailable; Python-only repository checks still run")
    def test_recorded_state_stays_inspectable_in_the_guided_tree(self):
        result = subprocess.run(
            ["node", str(Path(__file__).with_name("gui_tree.cjs"))],
            capture_output=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
