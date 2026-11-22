"""Seed full-image model caches into persistent data, preserving existing files."""
import os
import shutil
from pathlib import Path


def seed_cache(source: Path, destination: Path):
    if not source.is_dir():
        return
    for root, _, files in os.walk(source):
        target = destination / Path(root).relative_to(source)
        target.mkdir(parents=True, exist_ok=True)
        for name in files:
            output = target/name
            if output.exists() or output.is_symlink():
                continue
            original = Path(root)/name
            temporary = target/(name+'.anamnesis-seed-tmp')
            # Dereference bundled HF snapshot links: Windows Docker bind mounts
            # need not support creating Unix symlinks. Atomic copies also let a
            # restart retry an interrupted first-start cache population.
            shutil.copyfile(original, temporary)
            temporary.replace(output)
