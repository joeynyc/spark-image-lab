import argparse
import importlib.metadata
import json
import logging
import os
import threading
import time

from PIL import Image, ImageOps

try:
    from torch import OutOfMemoryError as TorchOutOfMemoryError
except ImportError:
    class TorchOutOfMemoryError(RuntimeError):
        """Fallback used by CPU-only callback tests."""

from history import (delete_generation, load_history, restore_generation,
                     save_generation, validate_request)
from manage import model_install_error
from settings import (APP_VERSION, MODEL_DIR, MODEL_ID, MODEL_REVISION, OUTPUTS,
                      ROOT, prepare_output_directory)

DEMOS = json.loads((ROOT / "demos.json").read_text())
LOCK = threading.Lock()
HISTORY_LOCK = threading.Lock()
PIPE = None


def pipeline():
    global PIPE
    if PIPE is None:
        import torch
        from diffusers import QwenImage21Pipeline

        model_error = model_install_error(MODEL_DIR)
        if model_error:
            raise RuntimeError(model_error)
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable. Start the container with GPU access; see docs/troubleshooting.md.")
        started = time.perf_counter()
        print("Loading Qwen Image 2.1 in BF16 on CUDA", flush=True)
        PIPE = QwenImage21Pipeline.from_pretrained(
            str(MODEL_DIR), torch_dtype=torch.bfloat16,
            local_files_only=True,
        ).to("cuda")
        print(f"Model loaded in {time.perf_counter() - started:.1f}s", flush=True)
    return PIPE


def generate(prompt, references=None, width=1024, height=1024, steps=40, seed=42):
    import torch

    prepare_output_directory()
    prompt, width, height, steps, seed = validate_request(prompt, width, height, steps, seed)
    references = references or []
    if len(references) > 10:
        raise ValueError("Use at most 10 reference images.")
    images = []
    for reference in references:
        with Image.open(reference) as source:
            images.append(ImageOps.exif_transpose(source).convert("RGBA"))
    with LOCK, torch.inference_mode():
        pipe = pipeline()
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        try:
            image = pipe(
                prompt=prompt, image=images or None, width=width, height=height,
                num_inference_steps=steps, true_cfg_scale=1.0, use_kv_cache=True,
                generator=torch.Generator("cuda").manual_seed(seed),
            ).images[0]
            torch.cuda.synchronize()
        except Exception:
            torch.cuda.empty_cache()
            raise
        elapsed = time.perf_counter() - started
        memory_gib = torch.cuda.max_memory_allocated() / 2**30
    alpha = image.getchannel("A") if image.mode == "RGBA" else None
    alpha_extrema = alpha.getextrema() if alpha is not None else None
    metadata = {
        "app_version": APP_VERSION,
        "model": MODEL_ID, "revision": MODEL_REVISION,
        "prompt": prompt,
        "width": image.width, "height": image.height, "steps": steps,
        "seed": seed, "true_cfg_scale": 1.0, "use_kv_cache": True,
        "elapsed_seconds": round(elapsed, 2), "peak_allocated_gib": round(memory_gib, 2),
        "mode": image.mode, "alpha_extrema": alpha_extrema,
        "versions": {p: importlib.metadata.version(p) for p in ("torch", "diffusers", "transformers")},
    }
    with HISTORY_LOCK:
        result = save_generation(OUTPUTS, image, metadata, references)
    print(f"Saved {result[2]['id']} in {elapsed:.1f}s", flush=True)
    return result


def batch(limit):
    results = {}
    for demo in DEMOS[:limit]:
        reference = demo.get("reference")
        image, _, _ = generate(
            demo["prompt"], [results[reference]] if reference else None,
            demo["width"], demo["height"], 40, demo["seed"],
        )
        results[demo["name"]] = image
        manifest = OUTPUTS / "demo-manifest.json"
        manifest.write_text(json.dumps(results, indent=2) + "\n")


def build_app():
    import gradio as gr

    def stats_text(stats):
        return f"{stats.get('elapsed_seconds', 0):.1f}s | {stats['width']} x {stats['height']} | Seed {stats['seed']} | Peak {stats.get('peak_allocated_gib', 0):.1f} GiB"

    def refresh():
        entries = load_history(OUTPUTS)
        samples = [[r['prompt'], ", ".join(ref.get('filename', 'Reference')
                                         for ref in r.get('references', [])),
                    r['width'], r['height'],
                    r['steps'], r['seed'], r.get('elapsed_seconds', 0)] for r in entries]
        return gr.Dataset(samples=samples), [r['image_path'] for r in entries], [r['id'] for r in entries]

    def run(prompt, refs, width, height, steps, seed):
        try:
            image, metadata, stats = generate(prompt, refs, width, height, steps, seed)
        except ValueError as error:
            raise gr.Error(str(error)) from error
        except TorchOutOfMemoryError as error:
            raise gr.Error("GPU memory exhausted. Reduce the image dimensions or reference count.") from error
        except (OSError, Image.DecompressionBombError) as error:
            logging.exception("Image input or output failed")
            raise gr.Error("Could not read an image or save the result. Check the image files, free disk space, and output permissions.") from error
        return image, [image, metadata], stats_text(stats), *refresh()

    def restore(index, identifiers):
        if not isinstance(index, int) or not 0 <= index < len(identifiers):
            raise gr.Error("Select an available generation.")
        try:
            entry = restore_generation(OUTPUTS, identifiers[index])
        except (ValueError, OSError) as error:
            raise gr.Error("This generation is unavailable. Refresh the page to reload history.") from error
        if entry['missing_references']:
            gr.Warning("Some original reference images are unavailable. Re-upload them before regenerating this edit.")
        return (entry['prompt'], entry['reference_paths'], entry['width'], entry['height'],
                entry['steps'], entry['seed'], entry['image_path'],
                [entry['image_path'], entry['metadata_path']], stats_text(entry),
                entry['id'], False)

    def select_image(identifiers, event: gr.SelectData):
        return restore(event.index, identifiers)

    def use_reference(path):
        if not path:
            raise gr.Error("Generate an image first.")
        return [path]

    def delete_selected(identifier, confirmed):
        if not identifier:
            raise gr.Error("Select a generation to delete.")
        if confirmed is not True:
            raise gr.Error("Confirm permanent deletion first.")
        try:
            with HISTORY_LOCK:
                delete_generation(OUTPUTS, identifier)
        except ValueError as error:
            raise gr.Error(str(error)) from error
        except OSError as error:
            logging.exception("Generation deletion failed")
            raise gr.Error("Could not delete every generation file. Check output permissions.") from error
        return None, None, None, "", None, False, *refresh()

    def clear_delete_selection():
        return None, False

    with gr.Blocks(title="Spark Image Lab") as app:
        gr.Markdown("# Spark Image Lab\nQwen-Image-2.1 · DGX Spark")
        identifiers = gr.State([])
        selected_identifier = gr.State(None)
        with gr.Row():
            with gr.Column(scale=1):
                prompt = gr.Textbox(label="Prompt", lines=7)
                refs = gr.File(label="Reference images", file_count="multiple", file_types=["image"], type="filepath")
                with gr.Row():
                    width = gr.Slider(512, 2752, value=1024, step=32, label="Width")
                    height = gr.Slider(512, 2752, value=1024, step=32, label="Height")
                with gr.Row():
                    steps = gr.Slider(1, 80, value=40, step=1, label="Steps")
                    seed = gr.Number(label="Seed", value=42, precision=0, minimum=0, maximum=4294967295)
                create = gr.Button("Generate", variant="primary")
            with gr.Column(scale=1):
                result = gr.Image(label="Result", type="filepath", image_mode="RGBA", format="png", interactive=False, height=580)
                reuse = gr.Button("Use as reference")
                stats = gr.Textbox(label="Generation", interactive=False)
                files = gr.File(label="PNG and generation record", file_count="multiple")
                delete_confirm = gr.Checkbox(label="Confirm permanent deletion", value=False)
                delete = gr.Button("Delete permanently", variant="stop")
        history = gr.Dataset(components=[prompt, gr.Textbox(render=False), width, height, steps, seed, gr.Number(render=False)],
                             headers=["Prompt", "Reference images", "Width", "Height", "Steps", "Seed", "Time (s)"],
                             samples=[], type="index", layout="table", samples_per_page=10,
                             label="Generation history", elem_id="generation-history")
        gallery = gr.Gallery(label="Generated images", columns=4, height=320, preview=False)
        refresh_outputs = [history, gallery, identifiers]
        restore_outputs = [prompt, refs, width, height, steps, seed, result, files, stats,
                           selected_identifier, delete_confirm]
        app.load(refresh, outputs=refresh_outputs, queue=False, api_name=False)
        generation = create.click(run, inputs=[prompt, refs, width, height, steps, seed],
                                  outputs=[result, files, stats, *refresh_outputs],
                                  concurrency_limit=1, show_progress_on=[result],
                                  api_name="generate")
        generation.then(clear_delete_selection,
                        outputs=[selected_identifier, delete_confirm],
                        queue=False, api_name=False)
        history.click(restore, inputs=[history, identifiers], outputs=restore_outputs, queue=False, api_name=False)
        gallery.select(select_image, inputs=identifiers, outputs=restore_outputs, queue=False, api_name=False)
        reuse.click(use_reference, inputs=result, outputs=refs, queue=False)
        delete.click(delete_selected, inputs=[selected_identifier, delete_confirm],
                     outputs=[refs, result, files, stats, selected_identifier,
                              delete_confirm, *refresh_outputs], queue=False, api_name=False)
    return app.queue(max_size=8)


def serve():
    prepare_output_directory()
    pipeline()
    build_app().launch(server_name=os.environ.get("SPARK_HOST", "127.0.0.1"),
                       server_port=int(os.environ.get("SPARK_PORT", "7860")), share=False,
                       allowed_paths=[str(OUTPUTS)], footer_links=[], run_history=False,
                       max_file_size="25mb",
                       css="@media (max-width: 640px) { #generation-history table { min-width: 800px; } #generation-history td:first-child { min-width: 260px; } }")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--batch", action="store_true")
    parser.add_argument("--limit", type=int, default=len(DEMOS))
    args = parser.parse_args()
    if not (args.serve or args.batch):
        parser.error("Choose --serve or --batch.")
    if args.batch:
        batch(args.limit)
    if args.serve:
        serve()
