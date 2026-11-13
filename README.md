# Beyond the Venue Reel Studio

A local Streamlit app for turning event-decoration images into branded, vertical MP4 Reels. It uses the existing Python 3.13 virtual environment, MoviePy, Pillow, and FFmpeg.

## Start the app

1. Put the **original** brand logo PNG at `assets/brand_logo.png`, or upload it in the app and choose **Save original logo**. The uploaded file is copied byte-for-byte; the app does not redraw or recolor it.
2. Double-click `run_app.bat`. The app listens only on this computer (`127.0.0.1`).
3. Choose an image folder or upload images, review/edit their order, choose duration and style, then select **GENERATE REEL**.
4. The new MP4 is saved under `output/` with a unique timestamped name. Existing videos are not overwritten.

If needed, install the app dependencies into the existing environment with:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The original `create_reel.py` and `output/royal_engagement_reel.mp4` remain available and unchanged.

## Image handling and editing

- PNG, JPEG, WebP, and BMP files are supported, including in subfolders. Unsupported image formats and unreadable files are reported and block export until corrected; documents and other non-image files are ignored.
- Images are naturally sorted by filename, or by capture time when every image has usable EXIF capture metadata. Names such as `before`, `setup`, `final`, `finished`, and `after` can further guide endpoints. The table allows manual reordering.
- Similar-looking images are reported, never dropped. Unreadable files are explicitly reported and block export until corrected or removed by the user.
- The export is 1080×1920 at 30 fps. Images are static, consistently fitted photographs with no zoom, pan, shake, bounce, or other simulated object movement. Choose Smooth Crossfade (default), Gentle Fade, Clean Cut, or No Transition. The last two both produce a direct cut without an intermediate transition. A subtle logo watermark and static original-logo end card remain included.
- The export contains no audio or music. The renderer verifies the MP4 stream, dimensions, duration, and absence of audio before saving.

Event type is inferred only from image filenames. No vision model or online service inspects project photos.

## Optional image-to-video prompt

The app also includes the supplied universal prompt at `assets/ai_video_prompt.txt`. Expand **Optional: prepare a free AI image-to-video prompt**, choose an image, and prepare a ZIP containing that original image plus an event-specific prompt text file. You can manually take the pair to an external image-to-video tool. Preparing the bundle does not upload the image or generate a video. Check the service's current terms and free allowance yourself; the app never enables billing, buys credits, or calls an AI provider.

## AI video generation and cost

No generative-video service is called by the app. [Google Flow](https://flow.google.com/) is a sign-in-based web product; [Google's AI-credit documentation](https://support.google.com/googleone/answer/16287445?hl=en) describes plan-dependent limits and credits, and the Flow page does not provide a documented, unattended free API for this workflow. The app therefore does not attempt to sign in, spend credits, or claim generated human motion.

Open-source local image-to-video models such as [Wan2.1](https://github.com/Wan-Video/Wan2.1) are an alternative, but their weights are large and realistic generation needs substantial local GPU resources. The repository reports about 8.19 GB VRAM even for its 1.3B text-to-video model; the available machine reports integrated AMD Radeon graphics and no NVIDIA CUDA device, so local generated clips are not enabled. The app reliably uses cinematic animation of the original stills instead.
