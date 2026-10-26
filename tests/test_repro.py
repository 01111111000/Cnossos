import re
import shutil
import subprocess
import unittest
from pathlib import Path


class ReproTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('git'),'git required')
    def test_default_synthetic_output_is_untracked(self):
        # A clean clone contains results/synthetic, so `make synthetic`/`make all` must write elsewhere.
        text=Path('Makefile').read_text()
        out=re.search(r'^SYNTHETIC_OUT \?= (\S+)$',text,re.M).group(1)
        self.assertIn('--output $(SYNTHETIC_OUT)',text)
        tracked=subprocess.run(['git','ls-files','--',out],capture_output=True,text=True,check=True).stdout
        self.assertEqual(tracked,'')
