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

DATABASES = {
    "aa_hub.db": "AA_DB_PATH",
    "tx_hub.db": "TX_DB_PATH",
    "study_time.db": "STUDY_TIME_DB_PATH",
}


def backup(root, output):
    root = root.resolve()
    output = output.resolve()
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing backup: " + str(output))
    if not root.is_dir():
        raise NotADirectoryError(root)
    output.parent.mkdir(parents=True, exist_ok=True)

    sources = {
        name: Path(os.environ[env_var]).resolve() if os.getenv(env_var) else (root / name)
        for name, env_var in DATABASES.items()
    }
    board_directory = Path(os.environ["BOARD_STORAGE_PATH"]).resolve() if os.getenv("BOARD_STORAGE_PATH") else root / "board_data"
    sources["study_board.sqlite3"] = board_directory / "study_board.sqlite3"
    present = {name: path for name, path in sources.items() if path.is_file()}
    if not present and not (board_directory / "documents").is_dir():
        raise FileNotFoundError("No study databases or Study Board files found in configured paths or " + str(root))
    os.umask(0o077)
    with tempfile.TemporaryDirectory() as temp:
        snapshots = []
        for name, database_path in present.items():
            src = sqlite3.connect("file:" + database_path.as_posix() + "?mode=ro", uri=True)
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
            "databases": list(present),
            "excluded": [".env", "hosting API keys", "CricEdge files"],
        }
        with ZipFile(output, "x", compression=ZIP_DEFLATED) as z:
            for p in snapshots:
                z.write(p, p.name)
            board_files = []
            doc_dir = board_directory / "documents"
            if doc_dir.is_dir():
                for item in doc_dir.iterdir():
                    if item.is_file() and not item.is_symlink():
                        z.write(item, "study-board/documents/" + item.name)
                        board_files.append(item.name)
            manifest["study_board_uploaded_documents"] = board_files
            z.writestr("backup_manifest.json", json.dumps(manifest, indent=2))
    return output, list(present)


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
