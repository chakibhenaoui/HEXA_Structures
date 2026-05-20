from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "resources" / "icons"
PNG_PATH = ICON_DIR / "hexa_structures_icon.png"
ICO_PATH = ICON_DIR / "hexa_structures.ico"


def _scaled_points(scale: int) -> list[tuple[int, int]]:
    points = [
        (256, 106),
        (374, 174),
        (374, 310),
        (256, 378),
        (138, 310),
        (138, 174),
    ]
    return [(x * scale, y * scale) for x, y in points]


def _draw_icon(size: int = 512, scale: int = 4) -> Image.Image:
    canvas_size = size * scale
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def box(values: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        return tuple(value * scale for value in values)

    background = box((38, 38, 474, 474))
    draw.rounded_rectangle(
        background,
        radius=72 * scale,
        fill=(247, 249, 251, 255),
        outline=(215, 221, 229, 255),
        width=4 * scale,
    )

    points = _scaled_points(scale)
    center = (256 * scale, 242 * scale)

    outer_width = 15 * scale
    inner_width = 8 * scale
    node_radius = 17 * scale
    center_radius = 15 * scale

    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        draw.line([point, next_point], fill=(30, 58, 138, 255), width=outer_width)

    for index in (0, 1, 3, 4):
        draw.line([points[index], center], fill=(100, 116, 139, 255), width=inner_width)
    draw.line([points[5], points[2]], fill=(100, 116, 139, 255), width=inner_width)
    draw.line([points[1], points[4]], fill=(100, 116, 139, 255), width=inner_width)

    for x, y in [*points, center]:
        radius = center_radius if (x, y) == center else node_radius
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(37, 99, 235, 255),
        )

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    image = _draw_icon()
    image.save(PNG_PATH)
    image.save(ICO_PATH, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"PNG: {PNG_PATH}")
    print(f"ICO: {ICO_PATH}")


if __name__ == "__main__":
    main()
