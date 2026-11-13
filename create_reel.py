
from pathlib import Path
from datetime import datetime
from PIL import Image
from moviepy import (
    ImageClip,
    concatenate_videoclips,
    vfx
)

# --------------------------------------------------
# PROJECT SETTINGS
# --------------------------------------------------

PROJECT_DIR = Path(__file__).parent
PREPARED_DIR = PROJECT_DIR / "output" / "prepared_images"
OUTPUT_DIR = PROJECT_DIR / "output"

OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_STEM = "royal_engagement_reel_stable"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

TOTAL_DURATION = 15
TRANSITION_DURATION = 0.25

# The first 11 images receive 1.25 seconds each.
# The final image receives 4 seconds.
# Crossfades overlap adjacent clips by 0.25 seconds.
TIMELINE = [
    ("1.png", 1.25),
    ("2.png", 1.25),
    ("3.png", 1.25),
    ("4.png", 1.25),
    ("5.png", 1.25),
    ("6.png", 1.25),
    ("7.png", 1.25),
    ("8.png", 1.25),
    ("9.png", 1.25),
    ("10.png", 1.25),
    ("11.png", 1.25),
    ("final.png", 4.0),
]


# --------------------------------------------------
# CREATE SMOOTH IMAGE CLIPS
# --------------------------------------------------

def create_image_clip(filename, duration):

    image_path = PREPARED_DIR / filename

    if not image_path.exists():
        raise FileNotFoundError(
            f"Prepared image not found: {filename}"
        )

    with Image.open(image_path) as image:
        if image.size != (WIDTH, HEIGHT):
            raise ValueError(
                f"{filename} has incorrect dimensions: {image.size}"
            )

    # Load the image
    clip = ImageClip(str(image_path)).with_duration(duration)

    # Apply smooth fade transitions
    return clip.with_effects([
        vfx.CrossFadeIn(TRANSITION_DURATION),
        vfx.CrossFadeOut(TRANSITION_DURATION)
    ])



# --------------------------------------------------
# BUILD FINAL VIDEO
# --------------------------------------------------

def create_reel():

    output_file = OUTPUT_DIR / (
        f"{OUTPUT_STEM}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    )
    counter = 2
    while output_file.exists():
        output_file = OUTPUT_DIR / (
            f"{OUTPUT_STEM}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{counter}.mp4"
        )
        counter += 1

    print("\nPreparing video clips...\n")

    clips = []

    for filename, duration in TIMELINE:

        print(f"Processing: {filename}")

        clip = create_image_clip(filename, duration)
        clips.append(clip)

    print("\nCombining clips with crossfade transitions...")

    final_video = concatenate_videoclips(
        clips,
        method="compose",
        padding=-TRANSITION_DURATION
    )

    # Ensure the final duration is exactly 15 seconds
    final_video = final_video.with_duration(TOTAL_DURATION)

    print("\nRendering final Reel...")
    print(f"Resolution: {WIDTH}x{HEIGHT}")
    print(f"FPS: {FPS}")
    print(f"Duration: {TOTAL_DURATION} seconds")

    final_video.write_videofile(
        str(output_file),
        fps=FPS,
        codec="libx264",
        audio=False,
        preset="medium",
        bitrate="8000k",
        threads=4
    )

    # Release resources
    final_video.close()

    for clip in clips:
        clip.close()

    print("\nVIDEO CREATED SUCCESSFULLY!")
    print(f"Saved at: {output_file}")


if __name__ == "__main__":
    create_reel()
