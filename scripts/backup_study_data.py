"""Create an offline-downloadable backup of the *study* databases.

Run before replacing files on Bot-Hosting:
    python scripts/backup_study_data.py --root . --output ../jay-study-backup.zip

Backs up AA, TX, and focused-time SQLite data safely via SQLite's backup API.
Does not delete anything, and intentionally excludes .env and other secrets.
Download the ZIP off the host and keep it private before any cleanup.
"""
import argparse
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

DATABASES = ("aa_hub.db", "tx_hub.db", "study_time.db")


def backup(root, output):
    root = root.resolve()
    output = output.resolve()
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing backup: " + str(output))
    if not root.is_dir():
        raise NotADirectoryError(root)
    output.parent.mkdir(parents=True, exist_ok=True)

    present = [n for n in DATABASES if (root / n).is_file()]
    if not present:
        raise FileNotFoundError("No study databases found in " + str(root))
    os.umask(0o077)
    with tempfile.TemporaryDirectory() as temp:
        snapshots = []
        for name in present:
            src = sqlite3.connect("file:" + (root / name).as_posix() + "?mode=ro", uri=True)
            dest_path = Path(temp) / name
            dest = sqlite3.connect(str(dest_path))
            try:
                src.backup(dest)
                result = dest.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    raise RuntimeError("Database integrity check failed: " + name)
            finally:
                dest.close()
                src.close()
            snapshots.append(dest_path)

        manifest = {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "Jay Study Hub pre-deployment backup",
            "databases": present,
            "excluded": [".env", "hosting API keys", "CricEdge files"],
        }
        with ZipFile(output, "x", compression=ZIP_DEFLATED) as z:
            for p in snapshots:
                z.write(p, p.name)
            z.writestr("backup_manifest.json", json.dumps(manifest, indent=2))
    return output, present


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output, names = backup(args.root, args.output)
    print("Backup created:", output)
    print("Study databases:", ", ".join(names))
    print("Download and verify the ZIP off-host before deleting anything.")
    print("The .env secret file was NOT included. Keep a separate secure copy.")


if __name__ == "__main__":
    main()
