from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from moviepy import ImageClip

from reel_engine import (
    ImageAsset,
    HEIGHT,
    TRANSITION_OPTIONS,
    WIDTH,
    _brand_card,
    _load_watermark,
    _make_scene,
    _transition_clip,
    build_image_to_video_prompt,
    discover_images,
    find_similar_images,
    infer_event_type,
    order_images,
    unique_output_path,
)


class ReelEngineTests(unittest.TestCase):
    def test_folder_images_use_natural_order_and_final_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for name in ("10.png", "2.png", "final.png", "1.png"):
                Image.new("RGB", (12, 16), color=(20, 40, 60)).save(folder / name)

            assets, invalid = discover_images(folder)

            self.assertEqual([], invalid)
            self.assertEqual(["1.png", "2.png", "10.png", "final.png"], [a.name for a in assets])

    def test_corrupt_file_is_reported_not_used(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            Image.new("RGB", (12, 16)).save(folder / "good.png")
            (folder / "broken.png").write_bytes(b"not an image")

            assets, invalid = discover_images(folder)

            self.assertEqual(["good.png"], [a.name for a in assets])
            self.assertEqual(1, len(invalid))
            self.assertIn("broken.png", invalid[0])

    def test_unsupported_image_format_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            Image.new("RGB", (12, 16)).save(folder / "good.png")
            (folder / "animation.gif").write_bytes(b"GIF image not supported")

            assets, invalid = discover_images(folder)

            self.assertEqual(["good.png"], [asset.name for asset in assets])
            self.assertEqual(1, len(invalid))
            self.assertIn("animation.gif", invalid[0])

    def test_similar_images_are_reported_but_not_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            image = Image.new("RGB", (80, 80), "white")
            image.save(folder / "first.png")
            image.save(folder / "copy.png")
            assets = [
                ImageAsset(folder / "first.png", "first.png"),
                ImageAsset(folder / "copy.png", "copy.png"),
            ]

            self.assertEqual([("first.png", "copy.png", 0)], find_similar_images(assets))
            self.assertEqual(2, len(assets))

    def test_event_name_and_unique_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            assets = [ImageAsset(folder / "engagement_stage.png", "engagement_stage.png")]
            self.assertEqual("Engagement", infer_event_type(assets))

            first = unique_output_path(folder)
            first.touch()
            second = unique_output_path(folder)
            self.assertNotEqual(first, second)

    def test_build_prompt_includes_selected_image_context_and_master_prompt(self) -> None:
        prompt = build_image_to_video_prompt(
            "Preserve the source photograph.",
            r"folder\engagement_01.png",
            "Engagement",
        )

        self.assertIn("REFERENCE IMAGE FILE: engagement_01.png", prompt)
        self.assertIn("EVENT CONTEXT: Engagement", prompt)
        self.assertIn("Preserve the source photograph.", prompt)
        self.assertIn("do not purchase credits", prompt)

    def test_build_prompt_rejects_empty_master_prompt(self) -> None:
        with self.assertRaisesRegex(ValueError, "master prompt is empty"):
            build_image_to_video_prompt("  ", "stage.png", "Engagement")

    def test_non_numeric_names_use_stage_labels_and_stable_natural_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            names = ["Finished.png", "flowers.png", "setup.png"]
            assets = [ImageAsset(folder / name, name) for name in names]
            self.assertEqual(
                ["setup.png", "flowers.png", "Finished.png"],
                [asset.name for asset in order_images(assets)],
            )

    def test_watermark_is_composited_with_opacity_on_the_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            image_path = folder / "scene.png"
            logo_path = folder / "logo.png"
            Image.new("RGB", (20, 20), "white").save(image_path)
            Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(logo_path)
            watermark = _load_watermark(logo_path, width=100, opacity=0.5)
            scene = _make_scene(
                ImageAsset(image_path, image_path.name), 1.0, watermark
            )
            frame = scene.get_frame(0)
            self.assertTrue((frame == scene.get_frame(0.5)).all())
            self.assertTrue((frame == scene.get_frame(0.99)).all())
            scene.close()

            pixel = frame[HEIGHT - 150, WIDTH - 100]
            self.assertGreater(int(pixel[0]), int(pixel[1]))
            self.assertGreater(int(pixel[1]), 80)

    def test_transition_choices_and_static_transition_frames(self) -> None:
        self.assertEqual(
            ("Smooth Crossfade", "Gentle Fade", "Clean Cut", "No Transition"),
            TRANSITION_OPTIONS,
        )
        first_frame = Image.new("RGB", (WIDTH, HEIGHT), (180, 30, 50))
        second_frame = Image.new("RGB", (WIDTH, HEIGHT), (20, 70, 180))
        first = ImageClip(np.asarray(first_frame)).with_duration(1)
        second = ImageClip(np.asarray(second_frame)).with_duration(1)

        crossfade = _transition_clip(first, second, 0.5, "Smooth Crossfade")
        midpoint = crossfade.get_frame(0.25)
        self.assertLess(abs(int(midpoint[HEIGHT // 2, WIDTH // 2][0]) - 100), 5)
        crossfade.close()

        gentle_fade = _transition_clip(first, second, 0.5, "Gentle Fade")
        fade_midpoint = gentle_fade.get_frame(0.25)
        self.assertEqual((249, 239, 241), tuple(fade_midpoint[HEIGHT // 2, WIDTH // 2]))
        gentle_fade.close()
        first.close()
        second.close()

    def test_end_card_has_a_blush_background_and_the_original_logo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            logo_path = Path(temporary) / "logo.png"
            Image.new("RGBA", (120, 80), (180, 20, 40, 255)).save(logo_path)
            card = _brand_card(logo_path, duration=2.0)
            frame = card.get_frame(0.5)
            self.assertTrue((frame == card.get_frame(0)).all())
            self.assertTrue((frame == card.get_frame(1.9)).all())
            card.close()

            self.assertGreater(int(frame[100, 100, 0]), 180)
            center = frame[HEIGHT // 2 - 80, WIDTH // 2]
            self.assertGreater(int(center[0]), int(center[1]))


if __name__ == "__main__":
    unittest.main()
