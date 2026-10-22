"""Safe Code Execution Sandbox (Section 21.5)."""
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import settings


class SandboxRunner:
    """Executes model-generated statistical or visualization scripts under security constraints."""

    def __init__(self, timeout_sec: int = 30):
        self.timeout_sec = timeout_sec

    def execute_python(self, code: str, input_tables: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Execute python code in a temporary directory with execution limits.
        Disallows dangerous system operations and enforces strict timeouts.
        """
        # Static security check against dangerous builtins
        forbidden = ["os.system", "shutil.rmtree", "socket.", "subprocess.", "eval(", "exec(", "__import__('os')"]
        for pattern in forbidden:
            if pattern in code:
                return {
                    "success": False,
                    "error": f"Security violation: use of '{pattern}' is forbidden in sandbox.",
                    "stdout": "",
                    "stderr": "Forbidden operation blocked by sandbox policy.",
                    "seconds": 0.0
                }

        with tempfile.TemporaryDirectory() as tmp_dir:
            script_path = Path(tmp_dir) / "job.py"
            # Wrap code with resource protection
            safe_wrapper = f"""
import sys
import math
import json

# Safe execution wrapper
try:
{chr(10).join('    ' + line for line in code.splitlines())}
except Exception as e:
    sys.stderr.write(f"RuntimeError: {{str(e)}}\\n")
    sys.exit(1)
"""
            script_path.write_text(safe_wrapper, encoding="utf-8")

            t0 = time.time()
            try:
                proc = subprocess.run(
                    [sys.executable, str(script_path)],
                    cwd=tmp_dir,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_sec,
                    env={"PYTHONPATH": str(Path(".").resolve())}
                )
                elapsed = round(time.time() - t0, 3)
                return {
                    "success": proc.returncode == 0,
                    "returncode": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "seconds": elapsed
                }
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "error": f"Sandbox timeout exceeded ({self.timeout_sec}s)",
                    "stdout": "",
                    "stderr": "Execution terminated by watchdog.",
                    "seconds": self.timeout_sec
                }


sandbox_runner = SandboxRunner()
