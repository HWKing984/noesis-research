"""Run the shipped UI's native JavaScript check; no added browser dependency."""
import shutil
import subprocess
from pathlib import Path


def test_course_ui_workflow():
    node = shutil.which('node')
    assert node, 'Node is required to run the native UI check'
    result = subprocess.run([node,str(Path(__file__).with_suffix('.cjs'))],capture_output=True,text=True,timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
