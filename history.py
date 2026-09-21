"""Disk-backed generation history; independent of the GPU and UI runtimes."""

from datetime import datetime, timezone
import hashlib
import json
import logging
import math
from pathlib import Path
import re
import uuid

LOG = logging.getLogger(__name__)
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}\Z")


def validate_request(prompt, width, height, steps, seed):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Enter a prompt.")
    values = (width, height, steps, seed)
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or (isinstance(v, float) and (not math.isfinite(v) or not v.is_integer()))
           for v in values):
        raise ValueError("Dimensions, steps, and seed must be whole numbers.")
    width, height, steps, seed = map(int, values)
    if not (512 <= width <= 2752 and 512 <= height <= 2752):
        raise ValueError("Dimensions must be between 512 and 2752 pixels.")
    if width % 32 or height % 32:
        raise ValueError("Dimensions must be multiples of 32.")
    if not 1 <= steps <= 80 or not 0 <= seed < 2**32:
        raise ValueError("Use 1-80 steps and a seed between 0 and 4294967295.")
    return prompt.strip(), width, height, steps, seed


def _safe_file(root, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute():
        return None
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
        return None
    return candidate


def _deletable_file(root, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute():
        return None
    candidate = root / relative
    resolved = candidate.resolve()
    if (candidate.is_symlink() or not resolved.is_relative_to(root.resolve())
            or not candidate.is_file()):
        return None
    return candidate


def _recorded_reference_paths(root):
    paths = set()
    for record_path in root.glob("*.json"):
        if record_path.name == "demo-manifest.json":
            continue
        try:
            references = json.loads(record_path.read_text()).get("references", [])
        except (AttributeError, json.JSONDecodeError, OSError):
            continue
        if not isinstance(references, list):
            continue
        for reference in references:
            if isinstance(reference, dict) and isinstance(reference.get("path"), str):
                paths.add(reference["path"])
    return paths


def save_generation(root, image, metadata, references):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    identifier = now.strftime("%Y%m%d-%H%M%S-%f") + "-" + uuid.uuid4().hex[:8]
    image_path = root / f"{identifier}.png"
    record_path = root / f"{identifier}.json"
    temporary = root / f".{identifier}.tmp"
    reference_records = []
    created_references = []
    try:
        for reference in references:
            source = Path(reference)
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            suffix = source.suffix.lower()
            if suffix not in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"):
                suffix = ".img"
            relative = f"references/{digest}{suffix}"
            references_root = root / "references"
            references_root.mkdir(exist_ok=True)
            references_root = references_root.resolve()
            if not references_root.is_relative_to(root):
                raise ValueError("Reference storage must remain inside the output directory.")
            destination = references_root / f"{digest}{suffix}"
            if not destination.exists():
                reference_temp = destination.with_name(f".{digest}-{uuid.uuid4().hex}.tmp")
                try:
                    reference_temp.write_bytes(data)
                    reference_temp.replace(destination)
                    created_references.append(destination)
                finally:
                    reference_temp.unlink(missing_ok=True)
            reference_records.append({"filename": source.name, "sha256": digest, "path": relative})
        record = dict(metadata, schema_version=1, id=identifier, created_at=now.isoformat(),
                      references=reference_records)
        image.save(image_path, format="PNG")
        temporary.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
        # The JSON rename is the commit point; readers never see a partial generation.
        temporary.replace(record_path)
    except Exception:
        image_path.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        for path in created_references:
            path.unlink(missing_ok=True)
        raise
    return str(image_path), str(record_path), record


def restore_generation(root, identifier):
    root = Path(root).resolve()
    if not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier):
        raise ValueError("Invalid history entry.")
    record_path = _safe_file(root, f"{identifier}.json")
    image_path = _safe_file(root, f"{identifier}.png")
    if record_path is None or image_path is None:
        raise ValueError("This generation is no longer available.")
    try:
        record = json.loads(record_path.read_text())
        validate_request(*(record[k] for k in ("prompt", "width", "height", "steps", "seed")))
        references = record.get("references", [])
        if not isinstance(references, list) or len(references) > 10:
            raise ValueError("Invalid reference list.")
        if any(not isinstance(ref, dict) or not isinstance(ref.get("filename", "Reference"), str)
               for ref in references):
            raise ValueError("Invalid reference record.")
        reference_paths = []
        for reference in references:
            path = _safe_file(root, reference.get("path"))
            if path is not None:
                reference_paths.append(str(path))
        for key in ("elapsed_seconds", "peak_allocated_gib"):
            value = record.get(key, 0)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid {key}.")
        return dict(record, id=identifier, image_path=str(image_path),
                    metadata_path=str(record_path), reference_paths=reference_paths,
                    missing_references=len(references) - len(reference_paths))
    except (KeyError, TypeError, OverflowError, json.JSONDecodeError) as error:
        raise ValueError("Invalid generation record.") from error


def delete_generation(root, identifier):
    root = Path(root).resolve()
    entry = restore_generation(root, identifier)
    image_path = _deletable_file(root, f"{identifier}.png")
    record_path = _deletable_file(root, f"{identifier}.json")
    if image_path is None or record_path is None:
        raise ValueError("This generation cannot be deleted safely.")

    reference_paths = {
        reference["path"] for reference in entry.get("references", [])
        if isinstance(reference, dict) and isinstance(reference.get("path"), str)
    }
    token = uuid.uuid4().hex
    staged = []
    try:
        for source in (image_path, record_path):
            kind = source.suffix.lstrip(".")
            target = root / f".delete-{identifier}-{token}-{kind}.tombstone"
            source.replace(target)
            staged.append((source, target))
    except OSError:
        for source, target in reversed(staged):
            target.replace(source)
        raise

    remaining_references = _recorded_reference_paths(root)
    for _, target in staged:
        target.unlink()
    for relative in reference_paths - remaining_references:
        reference_path = _deletable_file(root, relative)
        if reference_path is not None:
            reference_path.unlink()
    references_root = root / "references"
    if references_root.is_dir() and not references_root.is_symlink():
        try:
            references_root.rmdir()
        except OSError:
            pass
    return entry


def load_history(root):
    root = Path(root)
    entries = []
    for path in sorted(root.glob("*.json"), reverse=True):
        if path.name == "demo-manifest.json":
            continue
        try:
            entries.append(restore_generation(root, path.stem))
        except (ValueError, OSError) as error:
            LOG.warning("Skipping history record %s: %s", path.name, error)
    return entries
