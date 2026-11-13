from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from moviepy import ImageClip, VideoClip, concatenate_videoclips
from proglog import ProgressBarLogger


WIDTH = 1080
HEIGHT = 1920
FPS = 30
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
UNSUPPORTED_IMAGE_EXTENSIONS = {".gif", ".tif", ".tiff", ".heic", ".heif", ".avif"}
BRAND_NAME = "BEYOND THE VENUE"
TAGLINE = "Celebrate More. Spend Smarter."
TRANSITION_OPTIONS = (
    "Smooth Crossfade",
    "Gentle Fade",
    "Clean Cut",
    "No Transition",
)
TRANSITION_DURATIONS = {
    "Smooth Crossfade": 0.45,
    "Gentle Fade": 0.50,
    "Clean Cut": 0.0,
    "No Transition": 0.0,
}
CARD_DURATION = 2.0
FADE_COLOR = (249, 239, 241)


@dataclass(frozen=True)
class ImageAsset:
    path: Path
    name: str


@dataclass(frozen=True)
class ReelResult:
    output_path: Path
    duration: float
    image_names: tuple[str, ...]
    width: int = WIDTH
    height: int = HEIGHT
    fps: int = FPS
    has_audio: bool = False


def _natural_key(value: str) -> tuple[tuple[int, object], ...]:
    parts = re.split(r"(\d+)", value.casefold())
    return tuple((1, int(part)) if part.isdigit() else (0, part) for part in parts)


def _capture_time(path: Path) -> str | None:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            return exif.get(36867) or exif.get(306)
    except (OSError, ValueError):
        return None


def discover_images(folder: Path) -> tuple[list[ImageAsset], list[str]]:
    if not folder.exists():
        raise FileNotFoundError(f"Image folder does not exist: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Image location is not a folder: {folder}")

    assets: list[ImageAsset] = []
    invalid: list[str] = []
    candidates: list[Path] = []
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        extension = path.suffix.casefold()
        if extension in SUPPORTED_EXTENSIONS:
            candidates.append(path)
        elif extension in UNSUPPORTED_IMAGE_EXTENSIONS:
            invalid.append(
                f"{path.relative_to(folder)}: unsupported image format; "
                f"convert it to one of {', '.join(sorted(SUPPORTED_EXTENSIONS))}."
            )
    for path in sorted(
        candidates, key=lambda item: _natural_key(str(item.relative_to(folder)))
    ):
        try:
            with Image.open(path) as image:
                image.verify()
            assets.append(ImageAsset(path=path, name=str(path.relative_to(folder))))
        except (OSError, ValueError) as error:
            invalid.append(f"{path.name}: {error}")
    return order_images(assets), invalid


def order_images(assets: Iterable[ImageAsset]) -> list[ImageAsset]:
    items = list(assets)
    if len(items) < 2:
        return items

    capture_times = {item.name: _capture_time(item.path) for item in items}
    if all(capture_times.values()):
        return sorted(
            items,
            key=lambda item: (capture_times[item.name], _natural_key(item.name)),
        )

    end_words = ("final", "finished", "complete", "completed", "after")
    start_words = ("before", "empty", "setup", "start")

    def key(item: ImageAsset) -> tuple[int, tuple[tuple[int, object], ...]]:
        name = Path(item.name).stem.casefold()
        tokens = set(re.findall(r"[a-z]+", name))
        if tokens.intersection(end_words):
            rank = 2
        elif tokens.intersection(start_words):
            rank = 0
        else:
            rank = 1
        return rank, _natural_key(item.name)

    return sorted(items, key=key)


def _difference_hash(path: Path) -> int:
    with Image.open(path) as image:
        sample = ImageOps.grayscale(image).resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(sample.getdata())
    value = 0
    for row in range(8):
        for column in range(8):
            value = (value << 1) | int(
                pixels[row * 9 + column] > pixels[row * 9 + column + 1]
            )
    return value


def find_similar_images(
    assets: Iterable[ImageAsset], max_distance: int = 5
) -> list[tuple[str, str, int]]:
    items = list(assets)
    hashes = [(item.name, _difference_hash(item.path)) for item in items]
    matches: list[tuple[str, str, int]] = []
    for index, (first_name, first_hash) in enumerate(hashes):
        for second_name, second_hash in hashes[index + 1:]:
            distance = (first_hash ^ second_hash).bit_count()
            if distance <= max_distance:
                matches.append((first_name, second_name, distance))
    return matches


def infer_event_type(assets: Iterable[ImageAsset]) -> str:
    names = " ".join(Path(item.name).stem.casefold() for item in assets)
    event_names = {
        "engagement": ("engagement", "ring ceremony"),
        "wedding": ("wedding", "marriage", "bridal"),
        "birthday": ("birthday", "cake"),
        "baby shower": ("baby shower", "babyshower"),
        "corporate": ("corporate", "conference", "launch"),
        "anniversary": ("anniversary",),
        "reception": ("reception",),
    }
    for label, terms in event_names.items():
        if any(term in names for term in terms):
            return label.title()
    return "Event decoration"


def build_image_to_video_prompt(
    master_prompt: str, image_name: str, event_type: str
) -> str:
    if not master_prompt.strip():
        raise ValueError("The image-to-video master prompt is empty.")
    if not image_name.strip():
        raise ValueError("Select an image before preparing its prompt.")
    if not event_type.strip():
        raise ValueError("Enter an event type before preparing the prompt.")
    return (
        f"REFERENCE IMAGE FILE: {Path(image_name).name}\n"
        f"EVENT CONTEXT: {event_type.strip()}\n"
        "Attach this exact image as the image-to-video reference. "
        "Analyse this image independently and follow the master instructions below. "
        "Generate only if the selected service offers genuinely free usage; do not "
        "purchase credits, enable billing, or exceed its free allowance.\n\n"
        f"{master_prompt.strip()}\n"
    )


def _load_watermark(logo_path: Path, width: int, opacity: float) -> Image.Image:
    with Image.open(logo_path) as source:
        logo = source.convert("RGBA")
    logo.thumbnail((width, width), Image.Resampling.LANCZOS)
    alpha = logo.getchannel("A").point(lambda value: round(value * opacity))
    logo.putalpha(alpha)
    return logo


def _make_scene(
    asset: ImageAsset,
    duration: float,
    watermark: Image.Image,
) -> VideoClip:
    with Image.open(asset.path) as source:
        frame = ImageOps.fit(
            source.convert("RGB"),
            (WIDTH, HEIGHT),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        ).convert("RGBA")
        x = WIDTH - watermark.width - 56
        y = HEIGHT - watermark.height - 100
        frame.alpha_composite(watermark, (x, y))

    return ImageClip(np.asarray(frame.convert("RGB"))).with_duration(duration).with_fps(FPS)


def _brand_card(logo_path: Path, duration: float) -> VideoClip:
    background = Image.new("RGB", (WIDTH, HEIGHT))
    top = (249, 239, 241)
    bottom = (242, 226, 230)
    for y in range(HEIGHT):
        ratio = y / max(1, HEIGHT - 1)
        color = tuple(round(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3))
        ImageDraw.Draw(background).line((0, y, WIDTH, y), fill=color)

    draw = ImageDraw.Draw(background)
    gold = (190, 160, 112)
    draw.rounded_rectangle((76, 76, WIDTH - 76, HEIGHT - 76), radius=16, outline=gold, width=3)
    draw.line((WIDTH // 2 - 90, HEIGHT // 2 + 330, WIDTH // 2 + 90, HEIGHT // 2 + 330), fill=gold, width=2)

    logo_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    with Image.open(logo_path) as source:
        logo = source.convert("RGBA")
    logo.thumbnail((700, 500), Image.Resampling.LANCZOS)
    logo_layer.alpha_composite(logo, ((WIDTH - logo.width) // 2, (HEIGHT - logo.height) // 2 - 80))

    font_path = Path("C:/Windows/Fonts/georgia.ttf")
    try:
        font = ImageFont.truetype(str(font_path), 34)
    except OSError:
        font = ImageFont.load_default(size=34)
    tagline_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    tagline_draw = ImageDraw.Draw(tagline_layer)
    text_box = tagline_draw.textbbox((0, 0), TAGLINE, font=font)
    text_x = (WIDTH - (text_box[2] - text_box[0])) // 2
    tagline_draw.text((text_x, HEIGHT // 2 + 390), TAGLINE, fill=(103, 78, 70), font=font)
    card_overlays = Image.alpha_composite(logo_layer, tagline_layer)
    full_card = Image.alpha_composite(background.convert("RGBA"), card_overlays)

    return ImageClip(
        np.asarray(full_card.convert("RGB"))
    ).with_duration(duration).with_fps(FPS)


def _transition_clip(
    first: VideoClip, second: VideoClip, duration: float, transition: str
) -> VideoClip:
    if transition not in {"Smooth Crossfade", "Gentle Fade"}:
        raise ValueError(f"{transition} does not have a transition clip.")

    first_frame = Image.fromarray(first.get_frame(0))
    second_frame = Image.fromarray(second.get_frame(0))
    fade_background = Image.new("RGB", (WIDTH, HEIGHT), FADE_COLOR)

    def frame_at(time: float) -> np.ndarray:
        progress = min(1.0, max(0.0, time / duration))
        if transition == "Smooth Crossfade":
            frame = Image.blend(first_frame, second_frame, progress)
        elif progress < 0.5:
            frame = Image.blend(first_frame, fade_background, progress * 2)
        else:
            frame = Image.blend(fade_background, second_frame, (progress - 0.5) * 2)
        return np.asarray(frame)

    return VideoClip(frame_function=frame_at, duration=duration).with_fps(FPS)


class _RenderProgress(ProgressBarLogger):
    def __init__(self, callback: Callable[[float], None] | None) -> None:
        super().__init__(logged_bars=[])
        self.progress_callback = callback
        self.last_percent = -1

    def bars_callback(
        self, bar: str, attr: str, value: float, _old_value: float | None = None
    ) -> None:
        _ = _old_value
        if bar not in {"t", "frame_index"} or attr != "index" or self.progress_callback is None:
            return
        total = self.state.get("bars", {}).get(bar, {}).get("total")
        if total:
            progress = min(1.0, max(0.0, float(value) / total))
            percent = round(progress * 100)
            if percent > self.last_percent:
                self.last_percent = percent
                self.progress_callback(progress)


def _probe_video(path: Path) -> tuple[float, bool]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError(
            "FFprobe was not found. Install FFmpeg and add its bin folder to PATH."
        )
    completed = subprocess.run(
        [
            ffprobe, "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"FFprobe could not validate the exported video: {completed.stderr.strip()}")
    try:
        metadata = json.loads(completed.stdout)
        video_streams = [stream for stream in metadata["streams"] if stream.get("codec_type") == "video"]
        duration = float(metadata["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("The exported MP4 has incomplete media metadata.") from error
    if len(video_streams) != 1:
        raise RuntimeError("The exported MP4 must contain exactly one video stream.")
    stream = video_streams[0]
    if stream.get("width") != WIDTH or stream.get("height") != HEIGHT:
        raise RuntimeError(
            f"Exported video dimensions are {stream.get('width')}x{stream.get('height')}, "
            f"expected {WIDTH}x{HEIGHT}."
        )
    if stream.get("codec_name") != "h264":
        raise RuntimeError(f"Expected H.264 video, got {stream.get('codec_name')}.")
    try:
        frame_rate = Fraction(stream["avg_frame_rate"])
    except (KeyError, ValueError, ZeroDivisionError) as error:
        raise RuntimeError("The exported MP4 has no valid average frame rate.") from error
    if frame_rate != FPS:
        raise RuntimeError(f"Exported video frame rate is {frame_rate}, expected {FPS} fps.")
    has_audio = any(stream.get("codec_type") == "audio" for stream in metadata["streams"])
    return duration, has_audio


def create_branded_reel(
    assets: Iterable[ImageAsset],
    logo_path: Path,
    output_path: Path,
    duration: float = 15.0,
    transition: str = "Smooth Crossfade",
    watermark_width: int = 180,
    watermark_opacity: float = 0.28,
    progress_callback: Callable[[float], None] | None = None,
) -> ReelResult:
    selected = list(assets)
    if not selected:
        raise ValueError("Select at least one valid image before generating a Reel.")
    if not logo_path.is_file():
        raise FileNotFoundError(
            f"The original brand logo is required at {logo_path}. "
            "Add assets/brand_logo.png or upload and save the official PNG logo."
        )
    if not 6 <= duration <= 60:
        raise ValueError("Reel duration must be between 6 and 60 seconds.")
    if transition not in TRANSITION_DURATIONS:
        raise ValueError(f"Unknown transition: {transition}")
    if not 80 <= watermark_width <= 360:
        raise ValueError("Watermark width must be between 80 and 360 pixels.")
    if not 0.05 <= watermark_opacity <= 0.8:
        raise ValueError("Watermark opacity must be between 5% and 80%.")
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite an existing video: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    card_duration = min(CARD_DURATION, duration * 0.32)
    requested_transition_duration = TRANSITION_DURATIONS[transition]
    weights = [
        1.35 if re.search(r"\b(final|finished|complete|completed|after)\b", asset.name, re.I)
        else 1.0
        for asset in selected
    ]
    weight_total = sum(weights)
    transition_count = len(selected) if requested_transition_duration else 0
    max_transition = (
        (duration - card_duration) * min(weights)
        / (weight_total + transition_count * min(weights))
    ) if transition_count else 0.0
    transition_duration = min(requested_transition_duration, max_transition)
    if requested_transition_duration and transition_duration < 1.0 / FPS:
        raise ValueError(
            "There are too many images for the selected duration to show every image "
            "clearly. Increase the duration or select fewer images."
        )
    image_duration_budget = (
        duration - card_duration - transition_count * transition_duration
    )
    if image_duration_budget <= 0:
        raise ValueError(
            "There are too many images for this duration. Increase the Reel duration "
            "or select fewer images."
        )
    scene_durations = [image_duration_budget * weight / weight_total for weight in weights]
    watermark = _load_watermark(logo_path, watermark_width, watermark_opacity)

    scenes: list[VideoClip] = []
    transitions: list[VideoClip] = []
    card: VideoClip | None = None
    final_video: VideoClip | None = None
    temp_path = output_path.with_name(f".{output_path.stem}.{uuid.uuid4().hex}.partial.mp4")
    try:
        for asset, scene_duration in zip(selected, scene_durations):
            scenes.append(_make_scene(asset, scene_duration, watermark))
        card = _brand_card(logo_path, card_duration)

        sequence: list[VideoClip] = []
        for index, scene in enumerate(scenes):
            sequence.append(scene)
            if transition_duration:
                next_clip = scenes[index + 1] if index + 1 < len(scenes) else card
                transitions.append(
                    _transition_clip(
                        scene, next_clip, transition_duration, transition
                    )
                )
                sequence.append(transitions[-1])
        sequence.append(card)
        final_video = concatenate_videoclips(sequence, method="compose")
        # Keep the last frame on the requested frame grid despite floating-point
        # rounding in concatenated clip durations.
        final_video = final_video.with_duration(duration + 1e-6)
        logger = _RenderProgress(progress_callback)
        final_video.write_videofile(
            str(temp_path),
            fps=FPS,
            codec="libx264",
            audio=False,
            preset="medium",
            bitrate="8000k",
            threads=4,
            logger=logger,
        )
        if not temp_path.is_file() or temp_path.stat().st_size == 0:
            raise RuntimeError("MoviePy did not produce a non-empty MP4.")
        rendered_duration, has_audio = _probe_video(temp_path)
        if abs(rendered_duration - duration) > (1.0 / FPS) + 0.02:
            raise RuntimeError(
                f"Export duration is {rendered_duration:.3f}s; expected {duration:.3f}s."
            )
        if has_audio:
            raise RuntimeError("The exported video unexpectedly contains an audio stream.")
        temp_path.rename(output_path)
        if progress_callback is not None:
            progress_callback(1.0)
        return ReelResult(
            output_path=output_path,
            duration=rendered_duration,
            image_names=tuple(asset.name for asset in selected),
        )
    finally:
        if final_video is not None:
            final_video.close()
        for clip in [*transitions, *scenes]:
            clip.close()
        if card is not None:
            card.close()
        if temp_path.exists():
            temp_path.unlink()


def unique_output_path(output_dir: Path, now: datetime | None = None) -> Path:
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    candidate = output_dir / f"beyond_the_venue_reel_{stamp}.mp4"
    counter = 2
    while candidate.exists():
        candidate = output_dir / f"beyond_the_venue_reel_{stamp}_{counter}.mp4"
        counter += 1
    return candidate


__all__ = [
    "BRAND_NAME",
    "FPS",
    "HEIGHT",
    "ImageAsset",
    "ReelResult",
    "SUPPORTED_EXTENSIONS",
    "TAGLINE",
    "TRANSITION_OPTIONS",
    "WIDTH",
    "build_image_to_video_prompt",
    "create_branded_reel",
    "discover_images",
    "find_similar_images",
    "infer_event_type",
    "order_images",
    "unique_output_path",
]
