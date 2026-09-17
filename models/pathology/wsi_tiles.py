"""Slide geometry, tissue detection and tile reading shared by extraction and inference.

All tiles are 224×224 px at ~0.5 µm/px: the pyramid level closest to (but not coarser
than) the target resolution is read and resized. Tissue is detected on a ≤2048 px
thumbnail (HSV saturation + brightness); a tile is kept when at least ``min_tissue`` of
its footprint is tissue. Tile images are never written to disk; only coordinates and
embeddings are stored.
"""

from __future__ import annotations

import numpy as np
import torch
from PIL import Image, ImageDraw
from torch.utils.data import Dataset

TILE_PX = 224
TARGET_MPP = 0.5


def open_slide(path):
    import openslide  # noqa: PLC0415

    return openslide.OpenSlide(str(path))


def slide_geometry(slide, target_mpp: float = TARGET_MPP, tile_px: int = TILE_PX) -> dict:
    import openslide  # noqa: PLC0415

    props = slide.properties
    mpp = props.get(openslide.PROPERTY_NAME_MPP_X) or props.get("aperio.MPP")
    if mpp is None:
        raise ValueError("slide has no MPP metadata; cannot standardise resolution")
    base_mpp = float(mpp)
    downsamples = [float(d) for d in slide.level_downsamples]
    candidates = [i for i, d in enumerate(downsamples) if base_mpp * d <= target_mpp * 1.05]
    level = max(candidates, key=lambda i: downsamples[i]) if candidates else 0
    ds = downsamples[level]
    level_mpp = base_mpp * ds
    read_px = int(round(tile_px * target_mpp / level_mpp))
    return {"base_mpp": base_mpp, "level": level, "downsample": ds, "level_mpp": level_mpp, "read_px": read_px, "step0": int(round(read_px * ds)), "tile_px": tile_px, "target_mpp": target_mpp, "dimensions": list(slide.dimensions), "app_mag": props.get("aperio.AppMag"), "vendor": props.get("openslide.vendor")}


def tissue_mask(slide, thumb_max: int = 2048, sat_threshold: int = 20, bright_threshold: int = 235):
    thumb = slide.get_thumbnail((thumb_max, thumb_max)).convert("RGB")
    hsv = np.asarray(thumb.convert("HSV"))
    rgb = np.asarray(thumb)
    mask = (hsv[..., 1] > sat_threshold) & (rgb.mean(axis=2) < bright_threshold)
    return thumb, mask


def tissue_coords(geom: dict, mask: np.ndarray, thumb_size: tuple[int, int], min_tissue: float = 0.6) -> list[tuple[int, int]]:
    W0, H0 = geom["dimensions"]
    step = geom["step0"]
    sx = thumb_size[0] / W0
    sy = thumb_size[1] / H0
    coords = []
    for y0 in range(0, H0 - step + 1, step):
        ty0, ty1 = int(y0 * sy), max(int((y0 + step) * sy), int(y0 * sy) + 1)
        row = mask[ty0:ty1]
        if row.size == 0:
            continue
        for x0 in range(0, W0 - step + 1, step):
            tx0, tx1 = int(x0 * sx), max(int((x0 + step) * sx), int(x0 * sx) + 1)
            block = row[:, tx0:tx1]
            if block.size and float(block.mean()) >= min_tissue:
                coords.append((x0, y0))
    return coords


def subsample_coords(coords: list[tuple[int, int]], max_tiles: int | None, seed: int) -> list[tuple[int, int]]:
    if max_tiles is None or len(coords) <= max_tiles:
        return coords
    rng = np.random.default_rng(seed)
    idx = np.sort(rng.choice(len(coords), size=max_tiles, replace=False))
    return [coords[i] for i in idx]


class TileDataset(Dataset):
    """Reads tiles from one slide; the OpenSlide handle is opened lazily in each worker."""

    def __init__(self, slide_path, coords, geom: dict):
        self.slide_path = str(slide_path)
        self.coords = coords
        self.geom = geom
        self._slide = None

    def __len__(self):
        return len(self.coords)

    def __getitem__(self, idx):
        if self._slide is None:
            self._slide = open_slide(self.slide_path)
        x0, y0 = self.coords[idx]
        g = self.geom
        region = self._slide.read_region((int(x0), int(y0)), g["level"], (g["read_px"], g["read_px"])).convert("RGB")
        if g["read_px"] != g["tile_px"]:
            region = region.resize((g["tile_px"], g["tile_px"]), Image.BILINEAR)
        arr = torch.from_numpy(np.asarray(region, dtype=np.uint8).copy()).permute(2, 0, 1)  # CHW uint8
        return arr, idx


IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def normalize_batch(x: torch.Tensor) -> torch.Tensor:
    """uint8 CHW batch → float normalised with ImageNet statistics (DINOv2 convention)."""
    mean = torch.tensor(IMAGENET_MEAN, device=x.device).view(1, 3, 1, 1)
    std = torch.tensor(IMAGENET_STD, device=x.device).view(1, 3, 1, 1)
    return (x.float().div_(255.0) - mean) / std


def overlay_values(thumb: Image.Image, coords, values, geom: dict, alpha: float = 0.55, cmap: str = "jet") -> Image.Image:
    """Paint one colour per tile (values in [0,1]) onto the thumbnail."""
    import matplotlib  # noqa: PLC0415

    W0, H0 = geom["dimensions"]
    sx = thumb.width / W0
    sy = thumb.height / H0
    base = thumb.convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cm = matplotlib.colormaps[cmap]
    step = geom["step0"]
    for (x0, y0), v in zip(coords, values):
        r, g, b, _ = cm(float(np.clip(v, 0, 1)))
        draw.rectangle([x0 * sx, y0 * sy, (x0 + step) * sx, (y0 + step) * sy], fill=(int(r * 255), int(g * 255), int(b * 255), int(alpha * 255)))
    return Image.alpha_composite(base, layer).convert("RGB")
