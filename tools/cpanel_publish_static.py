"""Publish Django static files to public_html on cPanel.

Problem: cPanel/Apache typically serves /static/ from public_html, not from your app root.
Django's collectstatic puts files in STATIC_ROOT (here: BASE_DIR/staticfiles).

This script copies:
- <app>/staticfiles/*  ->  ~/public_html/static/

Optional:
- Set PUBLISH_MEDIA=1 to also copy:
  - <app>/media/*      ->  ~/public_html/media/

Run from: cPanel Setup Python App -> Execute Python Script
- tools/cpanel_publish_static.py
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jambas.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402


def _copy_tree(src: Path, dst: Path) -> tuple[int, int]:
	"""Return (copied_files, skipped_files)."""
	copied = 0
	skipped = 0
	if not src.exists():
		raise SystemExit(f"Source does not exist: {src}")
	dst.mkdir(parents=True, exist_ok=True)

	for root, dirs, files in os.walk(src):
		rel = Path(root).relative_to(src)
		target_dir = dst / rel
		target_dir.mkdir(parents=True, exist_ok=True)
		for d in dirs:
			(target_dir / d).mkdir(parents=True, exist_ok=True)
		for name in files:
			s = Path(root) / name
			d = target_dir / name
			# Copy if missing or changed.
			if d.exists() and d.stat().st_size == s.stat().st_size and int(d.stat().st_mtime) >= int(s.stat().st_mtime):
				skipped += 1
				continue
			shutil.copy2(s, d)
			copied += 1
	return copied, skipped


def main():
	home = Path.home()
	public_html = Path(os.environ.get("CPANEL_PUBLIC_HTML") or (home / "public_html"))

	static_src = Path(str(getattr(settings, "STATIC_ROOT", "")))
	if not static_src:
		raise SystemExit("STATIC_ROOT is not set; cannot publish static.")

	static_dst = public_html / "static"

	print("=== Publish static ===")
	print(f"STATIC_ROOT: {static_src}")
	print(f"Target:      {static_dst}")
	copied, skipped = _copy_tree(static_src, static_dst)
	print(f"Copied files: {copied}")
	print(f"Skipped files: {skipped}")

	if os.environ.get("PUBLISH_MEDIA", "0") == "1":
		media_src = Path(str(getattr(settings, "MEDIA_ROOT", "")))
		media_dst = public_html / "media"
		print("\n=== Publish media ===")
		print(f"MEDIA_ROOT: {media_src}")
		print(f"Target:     {media_dst}")
		copied_m, skipped_m = _copy_tree(media_src, media_dst)
		print(f"Copied files: {copied_m}")
		print(f"Skipped files: {skipped_m}")

	print("\nDone.")


if __name__ == "__main__":
	main()
