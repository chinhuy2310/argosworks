import os
import io
from PIL import Image

def optimize_and_save_file(file_data: bytes, dest_path: str, max_dimension: int = 2560, quality: int = 82) -> int:
    """
    Saves binary file data to disk.
    If the file is a raster image (JPEG, PNG, WEBP), it optimizes and resizes it to reduce disk usage
    while preserving visual quality. For non-images or on failure, it saves raw bytes.
    Returns the final written file size in bytes.
    """
    ext = os.path.splitext(dest_path)[1].lower()
    if ext in [".jpg", ".jpeg", ".png", ".webp"]:
        try:
            with Image.open(io.BytesIO(file_data)) as img:
                # Handle EXIF orientation if present
                try:
                    from PIL import ImageOps
                    img = ImageOps.exif_transpose(img)
                except Exception:
                    pass

                # Downscale if image is excessively large
                w, h = img.size
                if w > max_dimension or h > max_dimension:
                    img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

                # Save optimized based on format
                if ext in [".jpg", ".jpeg"]:
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    img.save(dest_path, "JPEG", quality=quality, optimize=True)
                elif ext == ".png":
                    # If RGBA, keep RGBA; optimize PNG compression
                    img.save(dest_path, "PNG", optimize=True)
                elif ext == ".webp":
                    img.save(dest_path, "WEBP", quality=quality, method=4)
                
                return os.path.getsize(dest_path)
        except Exception:
            # Fallback to direct raw write on any image processing error
            pass

    # Non-image or fallback
    with open(dest_path, "wb") as f:
        f.write(file_data)
    return len(file_data)
