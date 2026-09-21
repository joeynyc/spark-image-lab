"""Real Gradio callback integration, with only expensive inference substituted."""

import asyncio
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

RUNTIME_AVAILABLE = all(importlib.util.find_spec(name) for name in ("gradio", "PIL"))


@unittest.skipUnless(RUNTIME_AVAILABLE, "Install requirements-ci.txt for Gradio integration tests")
class AppTests(unittest.TestCase):
    def setUp(self):
        import lab
        from gradio.state_holder import SessionState

        self.lab = lab
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output_patch = patch.object(lab, "OUTPUTS", self.root)
        self.output_patch.start()
        self.addCleanup(self.output_patch.stop)
        self.app = lab.build_app()
        self.state = SessionState(self.app)
        self.functions = {fn.name: (index, fn.fn) for index, fn in self.app.fns.items()}

    def fake_generate(self, prompt, refs, width, height, steps, seed):
        from PIL import Image
        from history import save_generation

        metadata = dict(prompt=prompt, width=width, height=height, steps=steps,
                        seed=seed, elapsed_seconds=1.25, peak_allocated_gib=1.0)
        return save_generation(self.root, Image.new("RGBA", (width, height), "red"), metadata, refs or [])

    def test_generation_updates_table_gallery_and_selection_snapshot(self):
        with patch.object(self.lab, "generate", self.fake_generate):
            result = asyncio.run(self.app.process_api(
                self.functions["run"][0], ["Test city", None, 512, 512, 4, 99], state=self.state))
        data = result["data"]
        self.assertIn("Test city", str(data[3]))
        self.assertEqual(len(data[4]), 1)
        entries = self.lab.load_history(self.root)
        restored = self.functions["restore"][1](0, [entries[0]["id"]])
        self.assertEqual(restored[:6], ("Test city", [], 512, 512, 4, 99))
        self.assertTrue(Path(restored[6]).is_file())
        self.assertEqual(len(self.functions["refresh"][1]()[1]), 1)

    def test_empty_history_and_stale_selection(self):
        import gradio as gr

        _, gallery, ids = self.functions["refresh"][1]()
        self.assertEqual((gallery, ids), ([], []))
        with self.assertRaises(gr.Error):
            self.functions["restore"][1](0, [])

    def test_failed_generation_does_not_add_history(self):
        import gradio as gr

        with patch.object(self.lab, "generate", side_effect=ValueError("Enter a prompt.")):
            with self.assertRaises(gr.Error):
                self.functions["run"][1]("", None, 512, 512, 4, 0)
        self.assertEqual(self.lab.load_history(self.root), [])

    def test_reference_edit_is_retained_and_restored(self):
        from PIL import Image

        reference = self.root / "uploaded-reference.png"
        Image.new("RGB", (64, 64), "blue").save(reference)
        with patch.object(self.lab, "generate", self.fake_generate):
            response = self.functions["run"][1]("An edited city", [str(reference)], 512, 512, 4, 100)
        reference.unlink()
        restored = self.functions["restore"][1](0, response[5])
        self.assertEqual(restored[0], "An edited city")
        self.assertEqual(len(restored[1]), 1)
        self.assertTrue(Path(restored[1][0]).is_file())
        self.assertEqual(len(response[3].samples), 1)

    def test_delete_selected_requires_confirmation_and_refreshes_history(self):
        import gradio as gr

        with patch.object(self.lab, "generate", self.fake_generate):
            response = self.functions["run"][1]("Disposable city", None, 512, 512, 4, 101)
        identifier = response[5][0]
        self.assertEqual(self.functions["clear_delete_selection"][1](), (None, False))
        with self.assertRaises(gr.Error):
            self.functions["delete_selected"][1](identifier, False)

        deleted = self.functions["delete_selected"][1](identifier, True)

        self.assertEqual(deleted[:6], (None, None, None, "", None, False))
        self.assertEqual(deleted[-2:], ([], []))
        self.assertEqual(self.lab.load_history(self.root), [])

    def test_delete_is_private_and_generate_api_contract_is_unchanged(self):
        endpoints = self.app.get_api_info()["named_endpoints"]
        self.assertEqual(set(endpoints), {"/generate", "/use_reference"})
        self.assertEqual(len(endpoints["/generate"]["returns"]), 5)


if __name__ == "__main__":
    unittest.main()
