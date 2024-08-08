import pathlib
import subprocess

def run(cmd, cwd=pathlib.Path(__file__).parent.parent.resolve()):
    """Convenience wrapper for getting the output of CLI commands"""
    res = subprocess.run(
            cmd, cwd=cwd, capture_output=True, check=True, text=True)

    return res.stdout.strip()
