from __future__ import annotations

import hashlib
import io
import subprocess
import tempfile
import zipfile
from pathlib import Path

import streamlit as st
from PIL import Image

from reel_engine import (
    BRAND_NAME,
    ImageAsset,
    TRANSITION_OPTIONS,
    build_image_to_video_prompt,
    create_branded_reel,
    discover_images,
    find_similar_images,
    infer_event_type,
    order_images,
    unique_output_path,
)


PROJECT_DIR = Path(__file__).resolve().parent
LOGO_PATH = PROJECT_DIR / "assets" / "brand_logo.png"
PROMPT_TEMPLATE_PATH = PROJECT_DIR / "assets" / "ai_video_prompt.txt"
OUTPUT_DIR = PROJECT_DIR / "output"

st.set_page_config(
    page_title="Beyond the Venue | Reel Studio",
    page_icon="🎞️",
    layout="wide",
)
st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(155deg, #fffafb 0%, #f8eff1 52%, #f6f0e9 100%); }
    .block-container { max-width: 1180px; padding-top: 2rem; }
    .brand-title { color: #634c46; font-family: Georgia, serif; letter-spacing: .11em; }
    .brand-subtitle { color: #9c8060; letter-spacing: .08em; }
    div.stButton > button[kind="primary"] {
      background: #8d6d5f; border: 0; color: white; min-height: 3.2rem;
      font-weight: 700; letter-spacing: .08em;
    }
    div.stButton > button[kind="primary"]:hover { background: #715548; color: white; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(f"<h1 class='brand-title'>{BRAND_NAME}</h1>", unsafe_allow_html=True)
st.markdown(
    "<p class='brand-subtitle'>CELEBRATE MORE. SPEND SMARTER. &nbsp;·&nbsp; "
    "CINEMATIC REEL STUDIO</p>",
    unsafe_allow_html=True,
)
st.caption("Choose a project, review the sequence, and generate a branded, music-free Reel.")

with st.sidebar:
    st.subheader("Brand identity")
    if LOGO_PATH.is_file():
        st.image(str(LOGO_PATH), caption="Official logo in use", width="stretch")
        st.success("The original logo is ready.")
    else:
        st.warning("Add the official PNG logo to assets/brand_logo.png to enable generation.")

    logo_upload = st.file_uploader(
        "Or upload the official logo (PNG)",
        type=["png"],
        help="The original PNG bytes are saved unchanged to assets/brand_logo.png.",
        key="brand_logo_upload",
    )
    if logo_upload is not None:
        try:
            with Image.open(io.BytesIO(logo_upload.getvalue())) as image:
                image.verify()
            st.image(logo_upload.getvalue(), caption="Logo preview", width="stretch")
            if st.button("Save original logo", width="stretch"):
                LOGO_PATH.parent.mkdir(parents=True, exist_ok=True)
                LOGO_PATH.write_bytes(logo_upload.getvalue())
                st.success("Original PNG saved unchanged to assets/brand_logo.png.")
                st.rerun()
        except (OSError, ValueError) as error:
            st.error(f"That PNG could not be opened as an image: {error}")

    st.divider()
    st.subheader("Watermark")
    watermark_width = st.slider("Logo width (pixels)", 100, 320, 180, 10)
    watermark_opacity = st.slider("Watermark opacity", 5, 60, 28, 1) / 100
    st.caption("The logo keeps its proportions and original colors.")

source_mode = st.radio(
    "Choose your image source",
    ["Folder", "Upload images"],
    horizontal=True,
)
assets: list[ImageAsset] = []
invalid_images: list[str] = []
temporary_directory: tempfile.TemporaryDirectory[str] | None = None

if source_mode == "Folder":
    default_folder = str(PROJECT_DIR / "input_images")
    if "folder_path" not in st.session_state:
        st.session_state["folder_path"] = default_folder
    folder_text = st.text_input("Images folder", key="folder_path")
    browse_col, _ = st.columns([1, 4])
    with browse_col:
        if st.button("Browse for folder"):
            try:
                import tkinter
                from tkinter import filedialog
            except ImportError as error:
                st.error(f"Folder picker could not open: {error}. Enter a folder path instead.")
            else:
                try:
                    root = tkinter.Tk()
                    root.withdraw()
                    root.attributes("-topmost", True)
                    chosen_folder = filedialog.askdirectory(
                        initialdir=folder_text or default_folder
                    )
                    root.destroy()
                    if chosen_folder:
                        st.session_state["folder_path"] = chosen_folder
                        st.rerun()
                except (OSError, tkinter.TclError) as error:
                    st.error(f"Folder picker failed: {error}. Enter a folder path instead.")
    try:
        assets, invalid_images = discover_images(Path(folder_text).expanduser())
    except (FileNotFoundError, NotADirectoryError, PermissionError) as error:
        st.error(str(error))
else:
    uploaded_images = st.file_uploader(
        "Choose multiple project images",
        type=["png", "jpg", "jpeg", "webp", "bmp"],
        accept_multiple_files=True,
        help="Every supported uploaded image is retained in the Reel unless you remove it here.",
        key="project_image_uploads",
    )
    if uploaded_images:
        temporary_directory = tempfile.TemporaryDirectory(prefix="beyond_venue_upload_")
        upload_root = Path(temporary_directory.name)
        for index, uploaded in enumerate(uploaded_images, start=1):
            staged_path = upload_root / f"{index:04d}_{Path(uploaded.name).name}"
            staged_path.write_bytes(uploaded.getvalue())
            try:
                with Image.open(staged_path) as image:
                    image.verify()
                assets.append(ImageAsset(path=staged_path, name=uploaded.name))
            except (OSError, ValueError) as error:
                invalid_images.append(f"{uploaded.name}: {error}")
        assets = order_images(assets)

if invalid_images:
    st.warning(
        "These image files cannot be included. They have not been deleted; convert, "
        "replace, or remove them before generating:\n\n"
        + "\n".join(f"- {name}" for name in invalid_images)
    )
assets_fingerprint = ""
if assets:
    similar = find_similar_images(assets)
    st.info(f"Detected project type: **{infer_event_type(assets)}** · {len(assets)} image(s)")
    if similar:
        st.warning(
            "Some images look similar. None are removed automatically: "
            + "; ".join(f"{first} / {second}" for first, second, _ in similar)
        )

    st.subheader("Review and arrange your images")
    st.caption(
        "Automatic order uses capture time when all images have it; otherwise natural "
        "filename order is used, with clearly named final/before images placed at the ends. "
        "Edit Order to rearrange; duplicate-looking images are always kept."
    )
    rows = []
    for index, asset in enumerate(assets, start=1):
        with Image.open(asset.path) as image:
            dimensions = f"{image.width} × {image.height}"
        rows.append(
            {"Order": index, "Image": asset.name, "Resolution": dimensions}
        )
    sequence_hash = hashlib.sha256()
    for asset in assets:
        sequence_hash.update(asset.name.encode("utf-8"))
        with asset.path.open("rb") as image_file:
            for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
                sequence_hash.update(chunk)
    fingerprint = sequence_hash.hexdigest()[:10]
    assets_fingerprint = fingerprint
    edited = st.data_editor(
        rows,
        key=f"image_order_{fingerprint}",
        hide_index=True,
        num_rows="fixed",
        width="stretch",
        column_config={
            "Order": st.column_config.NumberColumn(
                "Order", min_value=1, max_value=len(assets), step=1, format="%d"
            ),
            "Image": st.column_config.TextColumn("Image", disabled=True),
            "Resolution": st.column_config.TextColumn("Resolution", disabled=True),
        },
    )
    edited_rows = edited if isinstance(edited, list) else edited.to_dict("records")
    order_values = []
    invalid_order = False
    for index, row in enumerate(edited_rows):
        try:
            order_values.append(int(row["Order"]))
        except (TypeError, ValueError):
            order_values.append(index + 1)
            invalid_order = True
    if invalid_order:
        st.warning("Blank or invalid order values were set to their current row positions.")
    ordered_assets = [
        asset
        for _, asset in sorted(
            enumerate(assets),
            key=lambda pair: (order_values[pair[0]], pair[0]),
        )
    ]

    preview_columns = st.columns(4)
    for index, asset in enumerate(ordered_assets):
        with preview_columns[index % len(preview_columns)]:
            st.image(str(asset.path), width="stretch")
            st.caption(f"{index + 1}. {asset.name}")
else:
    ordered_assets = []

with st.expander("Optional: prepare a free AI image-to-video prompt", expanded=False):
    st.caption(
        "This uses your supplied master prompt to prepare a text-and-image download for "
        "manual use in an external service. It does not generate video, upload your photo, "
        "or bypass the service's free-use limits. The Reel generator still uses local "
        "cinematic still-image animation."
    )
    if assets:
        selected_prompt_image = st.selectbox(
            "Choose a reference image",
            options=assets,
            format_func=lambda asset: asset.name,
            key="ai_prompt_reference_image",
        )
        if st.button("Prepare image prompt", key="prepare_ai_image_prompt"):
            try:
                master_prompt = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
                prompt = build_image_to_video_prompt(
                    master_prompt,
                    selected_prompt_image.name,
                    infer_event_type(assets),
                )
                bundle = io.BytesIO()
                prompt_filename = (
                    f"{Path(selected_prompt_image.name).stem}_image_to_video_prompt.txt"
                )
                with zipfile.ZipFile(bundle, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr(
                        Path(selected_prompt_image.name).name,
                        selected_prompt_image.path.read_bytes(),
                    )
                    archive.writestr(prompt_filename, prompt)
                st.session_state["prepared_ai_prompt"] = prompt
                st.session_state["prepared_ai_prompt_bundle"] = bundle.getvalue()
                st.session_state["prepared_ai_prompt_filename"] = (
                    f"{Path(selected_prompt_image.name).stem}_ai_video_reference.zip"
                )
                st.session_state["prepared_ai_prompt_assets_fingerprint"] = assets_fingerprint
                st.session_state["prepared_ai_prompt_image_path"] = str(
                    selected_prompt_image.path.resolve()
                )
            except (OSError, ValueError, zipfile.BadZipFile) as error:
                st.error(f"Could not prepare the prompt bundle: {error}")

        prompt_value = st.session_state.get("prepared_ai_prompt")
        prompt_bundle = st.session_state.get("prepared_ai_prompt_bundle")
        if (
            prompt_value
            and prompt_bundle
            and st.session_state.get("prepared_ai_prompt_assets_fingerprint")
            == assets_fingerprint
            and st.session_state.get("prepared_ai_prompt_image_path")
            == str(selected_prompt_image.path.resolve())
        ):
            st.text_area(
                "Prompt preview",
                value=prompt_value,
                height=280,
                disabled=True,
                key="ai_video_prompt_preview",
            )
            st.download_button(
                "Download selected image + prompt",
                data=prompt_bundle,
                file_name=st.session_state["prepared_ai_prompt_filename"],
                mime="application/zip",
                width="stretch",
            )
    else:
        st.info("Select or upload images to prepare a prompt for one of them.")

st.divider()
settings_col, transition_col = st.columns(2)
with settings_col:
    duration = st.slider("Total Reel duration (seconds)", 6, 60, 15, 1)
with transition_col:
    transition = st.selectbox(
        "Photo transition",
        TRANSITION_OPTIONS,
        index=0,
        help=(
            "Smooth Crossfade and Gentle Fade add a subtle opacity transition. "
            "Clean Cut and No Transition both switch directly between still images."
        ),
    )

st.caption(
    "Images remain completely still after fitting the vertical frame. No zoom, pan, "
    "shake, bounce, or music is added. Only the selected photo transition, watermark, "
    "and branded end card are applied."
)
if st.button(
    "GENERATE REEL",
    type="primary",
    width="stretch",
    disabled=not assets or not LOGO_PATH.is_file(),
):
    if invalid_images:
        st.error("Fix or remove the unreadable images before generating so none are silently skipped.")
    else:
        progress = st.progress(0, text="Preparing the project…")
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            def update_progress(value: float) -> None:
                progress.progress(min(100, int(value * 100)), text="Rendering the Reel…")

            result = create_branded_reel(
                ordered_assets,
                LOGO_PATH,
                unique_output_path(OUTPUT_DIR),
                duration=duration,
                transition=transition,
                watermark_width=watermark_width,
                watermark_opacity=watermark_opacity,
                progress_callback=update_progress,
            )
            st.success(
                f"Reel created: {result.output_path.name} · "
                f"{result.duration:.2f}s · {result.width}×{result.height} · {result.fps} fps · no audio"
            )
            st.video(str(result.output_path))
            st.download_button(
                "Download finished Reel",
                data=result.output_path.read_bytes(),
                file_name=result.output_path.name,
                mime="video/mp4",
                width="stretch",
            )
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            st.error(f"Reel generation failed: {error}")
        finally:
            progress.empty()

if temporary_directory is not None:
    temporary_directory.cleanup()
