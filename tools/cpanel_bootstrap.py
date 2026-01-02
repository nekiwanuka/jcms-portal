import os
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> None:
	print("\n$", " ".join(cmd), flush=True)
	subprocess.check_call(cmd)


def main() -> int:
	project_root = Path(__file__).resolve().parent.parent
	requirements = project_root / "requirements.txt"
	if not requirements.exists():
		print(f"ERROR: requirements.txt not found at {requirements}")
		return 2

	python = sys.executable
	print(f"Python: {python}")
	print(f"Project root: {project_root}")

	# 1) Upgrade pip tooling first (fixes many pyproject metadata failures)
	_run([python, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])

	# 2) Install dependencies
	_run([python, "-m", "pip", "install", "-r", str(requirements)])

	# Optional: run migrations/collectstatic if explicitly enabled.
	# This is off by default so it won't fail if DB env vars aren't ready.
	if os.getenv("JCMS_RUN_MIGRATE") == "1":
		_run([python, "manage.py", "migrate"])
	if os.getenv("JCMS_RUN_COLLECTSTATIC") == "1":
		_run([python, "manage.py", "collectstatic", "--noinput"])

	print("\nDone.")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
