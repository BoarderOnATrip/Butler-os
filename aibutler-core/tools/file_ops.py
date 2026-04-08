#!/usr/bin/env python3
"""
aiButler File Operations — format conversion, compression, background removal,
annotation, and basic editing. Wraps ImageMagick, ffmpeg, rembg, Pillow, and
system tools into callable functions for OpenClaw skills.

Every function returns a dict: {"ok": bool, "output": str, "error": str | None}
"""
import os
import subprocess
import shutil
import tempfile
import zipfile
import tarfile
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Format Conversion
# ──────────────────────────────────────────────────────────────────────────────

def convert_image(src: str, dst: str, quality: int = 90, resize: str = None) -> dict:
    """Convert between image formats (jpg, png, tiff, webp, bmp, gif, pdf).
    Uses ImageMagick. Optional resize (e.g. '1920x1080', '50%')."""
    src, dst = Path(src), Path(dst)
    if not src.exists():
        return {"ok": False, "output": "", "error": f"Source not found: {src}"}

    cmd = ["magick", str(src)]
    if resize:
        cmd.extend(["-resize", resize])
    cmd.extend(["-quality", str(quality), str(dst)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return {"ok": False, "output": result.stdout, "error": result.stderr.strip()}
        return {"ok": True, "output": str(dst), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


def convert_video(src: str, dst: str, codec: str = "libx264",
                  resolution: str = None, audio_codec: str = "aac") -> dict:
    """Convert between video/audio formats using ffmpeg."""
    src = Path(src)
    if not src.exists():
        return {"ok": False, "output": "", "error": f"Source not found: {src}"}

    cmd = ["ffmpeg", "-y", "-i", str(src)]
    if resolution:
        cmd.extend(["-vf", f"scale={resolution}"])
    cmd.extend(["-c:v", codec, "-c:a", audio_codec, str(dst)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            return {"ok": False, "output": result.stdout, "error": result.stderr[-500:]}
        return {"ok": True, "output": str(dst), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


def extract_audio(src: str, dst: str, fmt: str = "mp3", quality: str = "0") -> dict:
    """Extract audio from video file."""
    cmd = ["ffmpeg", "-y", "-i", str(src), "-vn", "-acodec",
           {"mp3": "libmp3lame", "m4a": "aac", "wav": "pcm_s16le",
            "flac": "flac", "ogg": "libvorbis"}.get(fmt, fmt),
           "-q:a", quality, str(dst)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return {"ok": False, "output": "", "error": result.stderr[-500:]}
        return {"ok": True, "output": str(dst), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


def images_to_pdf(image_paths: list, dst: str) -> dict:
    """Combine multiple images into a single PDF."""
    cmd = ["magick"] + [str(p) for p in image_paths] + [str(dst)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return {"ok": False, "output": "", "error": result.stderr.strip()}
        return {"ok": True, "output": str(dst), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


def pdf_to_images(src: str, dst_dir: str, fmt: str = "png", dpi: int = 200) -> dict:
    """Split PDF pages into individual images."""
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["magick", "-density", str(dpi), str(src),
           str(dst_dir / f"page-%03d.{fmt}")]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return {"ok": False, "output": "", "error": result.stderr.strip()}
        files = sorted(dst_dir.glob(f"page-*.{fmt}"))
        return {"ok": True, "output": ", ".join(str(f) for f in files), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# Compression
# ──────────────────────────────────────────────────────────────────────────────

def zip_files(paths: list, dst: str) -> dict:
    """Create a zip archive from a list of files/directories."""
    try:
        with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zf:
            for p in paths:
                p = Path(p)
                if p.is_dir():
                    for f in p.rglob('*'):
                        if f.is_file():
                            zf.write(f, f.relative_to(p.parent))
                else:
                    zf.write(p, p.name)
        return {"ok": True, "output": str(dst), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


def unzip(src: str, dst_dir: str = None) -> dict:
    """Extract a zip archive."""
    src = Path(src)
    if dst_dir is None:
        dst_dir = src.parent / src.stem
    try:
        with zipfile.ZipFile(str(src), 'r') as zf:
            zf.extractall(str(dst_dir))
        return {"ok": True, "output": str(dst_dir), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


def tar_gz(paths: list, dst: str) -> dict:
    """Create a .tar.gz archive."""
    try:
        with tarfile.open(dst, 'w:gz') as tf:
            for p in paths:
                tf.add(p, arcname=Path(p).name)
        return {"ok": True, "output": str(dst), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


def untar(src: str, dst_dir: str = None) -> dict:
    """Extract a tar/tar.gz/tar.bz2 archive."""
    src = Path(src)
    if dst_dir is None:
        dst_dir = src.parent / src.stem.replace('.tar', '')
    try:
        with tarfile.open(str(src), 'r:*') as tf:
            tf.extractall(str(dst_dir))
        return {"ok": True, "output": str(dst_dir), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# Background Removal
# ──────────────────────────────────────────────────────────────────────────────

def remove_background(src: str, dst: str = None) -> dict:
    """Remove background from an image using AI (rembg/u2net)."""
    src = Path(src)
    if dst is None:
        dst = src.parent / f"{src.stem}_nobg.png"

    try:
        from rembg import remove
        from PIL import Image
        import io

        with open(src, 'rb') as f:
            input_data = f.read()

        output_data = remove(input_data)

        with open(str(dst), 'wb') as f:
            f.write(output_data)

        return {"ok": True, "output": str(dst), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# Photo Editing & Annotation
# ──────────────────────────────────────────────────────────────────────────────

def crop_image(src: str, dst: str, box: tuple) -> dict:
    """Crop an image. box = (left, top, right, bottom) in pixels."""
    try:
        from PIL import Image
        img = Image.open(src)
        cropped = img.crop(box)
        cropped.save(dst)
        return {"ok": True, "output": str(dst), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


def resize_image(src: str, dst: str, width: int = None, height: int = None) -> dict:
    """Resize image. Provide width, height, or both. Maintains aspect if one is None."""
    try:
        from PIL import Image
        img = Image.open(src)
        w, h = img.size
        if width and not height:
            height = int(h * (width / w))
        elif height and not width:
            width = int(w * (height / h))
        elif not width and not height:
            return {"ok": False, "output": "", "error": "Provide width and/or height"}
        resized = img.resize((width, height), Image.LANCZOS)
        resized.save(dst)
        return {"ok": True, "output": str(dst), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


def annotate_image(src: str, dst: str, text: str,
                   position: tuple = (10, 10), color: str = "red",
                   font_size: int = 24) -> dict:
    """Add text annotation to an image."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.open(src)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        except Exception:
            font = ImageFont.load_default()
        draw.text(position, text, fill=color, font=font)
        img.save(dst)
        return {"ok": True, "output": str(dst), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


def draw_rectangle(src: str, dst: str, box: tuple,
                   outline: str = "red", width: int = 3) -> dict:
    """Draw a rectangle on an image. box = (left, top, right, bottom)."""
    try:
        from PIL import Image, ImageDraw
        img = Image.open(src)
        draw = ImageDraw.Draw(img)
        draw.rectangle(box, outline=outline, width=width)
        img.save(dst)
        return {"ok": True, "output": str(dst), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


def add_arrow(src: str, dst: str, start: tuple, end: tuple,
              color: str = "red", width: int = 3) -> dict:
    """Draw an arrow on an image from start to end point."""
    try:
        from PIL import Image, ImageDraw
        import math
        img = Image.open(src)
        draw = ImageDraw.Draw(img)
        draw.line([start, end], fill=color, width=width)
        # Arrowhead
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        arrow_len = 15
        for offset in [2.5, -2.5]:
            ax = end[0] - arrow_len * math.cos(angle + offset * 0.2)
            ay = end[1] - arrow_len * math.sin(angle + offset * 0.2)
            draw.line([end, (int(ax), int(ay))], fill=color, width=width)
        img.save(dst)
        return {"ok": True, "output": str(dst), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# Video Frame Extraction
# ──────────────────────────────────────────────────────────────────────────────

def extract_frame(src: str, dst: str, timestamp: str = "00:00:01") -> dict:
    """Extract a single frame from a video at the given timestamp (HH:MM:SS or seconds)."""
    cmd = ["ffmpeg", "-y", "-ss", str(timestamp), "-i", str(src),
           "-frames:v", "1", "-q:v", "2", str(dst)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {"ok": False, "output": "", "error": result.stderr[-300:]}
        return {"ok": True, "output": str(dst), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# File Info
# ──────────────────────────────────────────────────────────────────────────────

def file_info(path: str) -> dict:
    """Get file metadata: size, format, dimensions (if image/video)."""
    p = Path(path)
    if not p.exists():
        return {"ok": False, "output": "", "error": f"Not found: {path}"}

    info = {
        "name": p.name,
        "size_bytes": p.stat().st_size,
        "size_mb": round(p.stat().st_size / 1048576, 2),
        "extension": p.suffix.lower(),
    }

    # Image dimensions
    try:
        from PIL import Image
        img = Image.open(path)
        info["width"], info["height"] = img.size
        info["mode"] = img.mode
    except Exception:
        pass

    # Video dimensions/duration
    if p.suffix.lower() in ('.mp4', '.mkv', '.webm', '.avi', '.mov'):
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", str(path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                import json
                probe = json.loads(result.stdout)
                fmt = probe.get("format", {})
                info["duration_seconds"] = float(fmt.get("duration", 0))
                for stream in probe.get("streams", []):
                    if stream.get("codec_type") == "video":
                        info["width"] = stream.get("width")
                        info["height"] = stream.get("height")
                        info["codec"] = stream.get("codec_name")
                        break
        except Exception:
            pass

    return {"ok": True, "output": info, "error": None}


# ──────────────────────────────────────────────────────────────────────────────
# Tool Registry (for OpenClaw skill discovery)
# ──────────────────────────────────────────────────────────────────────────────

TOOLS = {
    "convert_image": {
        "fn": convert_image,
        "description": "Convert between image formats (jpg, png, tiff, webp, pdf). Optional resize and quality.",
        "params": {"src": "str", "dst": "str", "quality": "int=90", "resize": "str=None"},
    },
    "convert_video": {
        "fn": convert_video,
        "description": "Convert between video formats (mp4, mkv, webm, avi, mov).",
        "params": {"src": "str", "dst": "str", "codec": "str=libx264", "resolution": "str=None"},
    },
    "extract_audio": {
        "fn": extract_audio,
        "description": "Extract audio from video as mp3, m4a, wav, flac, or ogg.",
        "params": {"src": "str", "dst": "str", "fmt": "str=mp3"},
    },
    "images_to_pdf": {
        "fn": images_to_pdf,
        "description": "Combine multiple images into a single PDF.",
        "params": {"image_paths": "list[str]", "dst": "str"},
    },
    "pdf_to_images": {
        "fn": pdf_to_images,
        "description": "Split PDF pages into individual images.",
        "params": {"src": "str", "dst_dir": "str", "fmt": "str=png", "dpi": "int=200"},
    },
    "zip_files": {
        "fn": zip_files,
        "description": "Create a zip archive from files or directories.",
        "params": {"paths": "list[str]", "dst": "str"},
    },
    "unzip": {
        "fn": unzip,
        "description": "Extract a zip archive.",
        "params": {"src": "str", "dst_dir": "str=None"},
    },
    "tar_gz": {
        "fn": tar_gz,
        "description": "Create a .tar.gz archive.",
        "params": {"paths": "list[str]", "dst": "str"},
    },
    "untar": {
        "fn": untar,
        "description": "Extract a tar/tar.gz/tar.bz2 archive.",
        "params": {"src": "str", "dst_dir": "str=None"},
    },
    "remove_background": {
        "fn": remove_background,
        "description": "Remove background from an image using AI (u2net model).",
        "params": {"src": "str", "dst": "str=None"},
    },
    "crop_image": {
        "fn": crop_image,
        "description": "Crop an image to a rectangular region.",
        "params": {"src": "str", "dst": "str", "box": "(left, top, right, bottom)"},
    },
    "resize_image": {
        "fn": resize_image,
        "description": "Resize an image. Maintains aspect ratio if only width or height given.",
        "params": {"src": "str", "dst": "str", "width": "int=None", "height": "int=None"},
    },
    "annotate_image": {
        "fn": annotate_image,
        "description": "Add text annotation to an image.",
        "params": {"src": "str", "dst": "str", "text": "str", "position": "(x,y)", "color": "str=red"},
    },
    "draw_rectangle": {
        "fn": draw_rectangle,
        "description": "Draw a rectangle on an image for highlighting.",
        "params": {"src": "str", "dst": "str", "box": "(left,top,right,bottom)", "outline": "str=red"},
    },
    "add_arrow": {
        "fn": add_arrow,
        "description": "Draw an arrow on an image pointing from start to end.",
        "params": {"src": "str", "dst": "str", "start": "(x,y)", "end": "(x,y)"},
    },
    "extract_frame": {
        "fn": extract_frame,
        "description": "Extract a single frame from a video at a given timestamp.",
        "params": {"src": "str", "dst": "str", "timestamp": "str=00:00:01"},
    },
    "file_info": {
        "fn": file_info,
        "description": "Get file metadata: size, format, dimensions, codec, duration.",
        "params": {"path": "str"},
    },
}
