from pathlib import Path
import shutil
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent

CONFIG_FILES = [
    PROJECT_ROOT / "config" / "benches.csv",
    PROJECT_ROOT / "config" / "overrides.json",
    PROJECT_ROOT / "config" / "notes.json",
    PROJECT_ROOT / "config" / "dashboard_settings.json", ]

BACKUP_ROOT = PROJECT_ROOT / "backups"


def timestamp_folder_name():
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def backup_config_files():
    backup_folder = BACKUP_ROOT / timestamp_folder_name()
    backup_folder.mkdir(parents=True, exist_ok=True)

    copied_count = 0

    for source_file in CONFIG_FILES:
        if not source_file.exists():
            continue

        destination_file = backup_folder / source_file.name
        shutil.copy2(source_file, destination_file)
        copied_count += 1

    return backup_folder, copied_count


def remove_old_backups(keep_latest=50):
    if not BACKUP_ROOT.exists():
        return 0

    backup_folders = [
        path for path in BACKUP_ROOT.iterdir()
        if path.is_dir()
    ]

    backup_folders.sort(
        key=lambda path: path.name,
        reverse=True
    )

    old_folders = backup_folders[keep_latest:]
    removed_count = 0

    for folder in old_folders:
        shutil.rmtree(folder, ignore_errors=True)
        removed_count += 1

    return removed_count


if __name__ == "__main__":
    backup_folder, copied_count = backup_config_files()
    removed_count = remove_old_backups()

    print()
    print("===================================")
    print("LINEUP Config Backup Complete")
    print("===================================")
    print(f"Backup folder : {backup_folder}")
    print(f"Files copied  : {copied_count}")
    print(f"Old backups removed: {removed_count}")
    print()