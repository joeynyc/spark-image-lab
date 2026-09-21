# Generation History

The area previously occupied by fixed demo prompts now lists completed local
generations, newest first. Columns: prompt, original reference filenames, width,
height, steps, seed, and generation time in seconds. The image gallery below
uses the same order. Rows are paginated by Gradio in groups of ten.

Every successful generation refreshes both views in the submitting browser.
Reloading the page reads history from disk, including after a server restart.
Other browser sessions refresh when reloaded or after their next generation;
this release does not push live history updates between sessions.

Select a table row or gallery image to restore its prompt, references,
dimensions, steps, seed, result preview, runtime, and download files. Selection
does not generate an image. "Use as reference" makes the selected result the
reference input for a subsequent edit; it replaces the current reference list.

To remove a generation, select it, enable "Confirm permanent deletion," and
choose "Delete permanently." The app removes the generation PNG and JSON record.
Saved reference copies are removed only when no remaining generation uses them.
Deletion cannot be undone.

## Storage

Each generation writes `<id>.png` and `<id>.json` in `outputs/`. JSON is written
atomically after the PNG. Only a complete record with a present output image is
listed. Missing or malformed records are skipped with a server log warning.
Reference originals are stored under `outputs/references/`, addressed by SHA-256
to deduplicate identical uploads. Treat them as private data, including any
embedded camera metadata. Generated PNGs do not copy that reference metadata.

Version 1 records contain:

- `schema_version`, app version, `id`, and UTC `created_at`.
- Model identifier, pinned revision, and relevant library versions.
- Prompt, width, height, steps, seed, guidance, and KV-cache settings.
- `elapsed_seconds`, `peak_allocated_gib`, image mode, and alpha extrema.
- Reference filename, content hash, and relative persistent path.

Timing excludes model loading and disk persistence; peak allocated GPU memory
is not total system memory usage. Same seeds/settings help reproduce results
but do not promise bitwise identity across different libraries or hardware.

Existing prototype PNG/JSON pairs are shown without rewriting them. Their
reference records may have only names and hashes, not reusable copies. Selecting
such an edit warns about missing references; re-upload the originals before
regenerating it. Standalone PNG files without generation records are not listed.

## Retention and Backup

No automatic deletion is enabled. Back up the entire `outputs/` directory,
including `references/`. Backups and `.gitignore` protect against accidental
commits, not against deletion in the app or local users with filesystem access.
