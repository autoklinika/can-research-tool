from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from app.combined_filters import CombinedActiveFilterSet
from app.filter_preferences import ProjectFilterPreferences
from app.filters import CanFrameRecord, FilterCompiler, ProjectFilterRepository
from app.project import CrtProject


DEFAULT_IDS = (0x18DAF900, 0x18DA00F9, 0x18FEEE30)


def _parse_can_id(value: str) -> int:
    text = value.strip().lower().replace("_", "")
    return int(text, 16) if text.startswith("0x") else int(text, 16)


def _git_head() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect persisted CRT Live filters and evaluate selected CAN IDs."
    )
    parser.add_argument("project", type=Path, help="CRT project directory")
    parser.add_argument(
        "--id",
        dest="can_ids",
        action="append",
        default=[],
        help="CAN ID in hex; may be repeated",
    )
    args = parser.parse_args()

    project = CrtProject.open(args.project)
    repository = ProjectFilterRepository(project.database_path)
    preferences = ProjectFilterPreferences(project.database_path)
    presets = repository.list_presets()
    mode = preferences.combination_mode()
    active = CombinedActiveFilterSet(presets, scope="live", combination_mode=mode)
    compiler = FilterCompiler()

    print(f"git_head={_git_head()}")
    print(f"project={project.root}")
    print(f"combination_mode={mode.value}")
    print(f"stored_presets={len(presets)}")
    print(f"active_live_presets={active.active_count}")
    print(f"active_live_names={list(active.active_names)!r}")
    print(f"affects_raw_visibility={active.affects_raw_visibility}")
    print(f"affects_logical_visibility={active.affects_visibility}")
    print()

    for index, preset in enumerate(presets, start=1):
        issues = compiler.validate(preset)
        print(f"PRESET {index}")
        print(f"  name={preset.name!r}")
        print(f"  enabled={preset.enabled}")
        print(f"  mode={preset.mode.value}")
        print(f"  scope={preset.scope!r}")
        print(f"  validation={[issue.message for issue in issues]!r}")
        print(f"  root={json.dumps(preset.root, ensure_ascii=False, sort_keys=True)}")
        print()

    can_ids = tuple(_parse_can_id(value) for value in args.can_ids) or DEFAULT_IDS
    print("RAW DECISIONS")
    for can_id in can_ids:
        decision = active.decide(
            CanFrameRecord(
                can_id=can_id,
                extended=can_id > 0x7FF,
                dlc=8,
                relative_time_us=0,
                channel=0,
            )
        )
        print(
            f"  0x{can_id:08X}: visible={decision.visible} "
            f"highlighted={decision.highlighted} "
            f"unavailable={list(decision.unavailable_reasons)!r}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
