from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from sklearn.cluster import KMeans


BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"


def read_image_unicode(path: Path) -> np.ndarray | None:
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def save_image_unicode(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix or ".png"
    ok, encoded = cv2.imencode(suffix, image)
    if ok:
        encoded.tofile(str(path))


def load_face_cascade() -> cv2.CascadeClassifier | None:
    candidates = [
        MODEL_DIR / "lbpcascade_animeface.xml",
        Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml",
    ]
    for path in candidates:
        if not path.exists():
            continue
        cascade = cv2.CascadeClassifier(str(path))
        if not cascade.empty():
            return cascade
    return None


def get_main_color(image: np.ndarray, k: int = 5) -> tuple[int, int, int]:
    if image is None or image.size == 0:
        return (0, 0, 0)

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    pixels = hsv.reshape((-1, 3))
    valid_pixels = []

    for h, s, v in pixels:
        if v < 40 or v > 245:
            continue
        if s < 40:
            continue
        valid_pixels.append([h, s, v])

    if not valid_pixels:
        return (0, 0, 0)

    valid_pixels = np.array(valid_pixels, dtype=np.float32)
    model = KMeans(n_clusters=min(k, len(valid_pixels)), random_state=42, n_init=10)
    model.fit(valid_pixels)

    counts = np.bincount(model.labels_)
    main_hsv = np.uint8([[model.cluster_centers_[np.argmax(counts)]]])
    main_bgr = cv2.cvtColor(main_hsv, cv2.COLOR_HSV2BGR)[0][0]
    return tuple(map(int, main_bgr))


def color_name(rgb: tuple[int, int, int] | np.ndarray) -> str:
    r, g, b = [int(value) for value in rgb]
    hsv = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV)[0][0]
    h, s, v = [int(value) for value in hsv]

    if v < 50:
        return "黑色"
    if s < 25 and v > 200:
        return "白色"
    if s < 25:
        return "灰色"
    if h <= 8 or h >= 170:
        return "红色"
    if 8 < h <= 18:
        return "橙色"
    if 18 < h <= 32:
        return "金色" if v > 170 else "黄色"
    if 32 < h <= 85:
        return "绿色"
    if 85 < h <= 100:
        return "青色"
    if 100 < h <= 130:
        return "蓝色"
    if 130 < h <= 155:
        return "紫色"
    if 155 < h < 170:
        return "粉色"
    return "未知"


def detect_face(image: np.ndarray) -> tuple[int, int, int, int]:
    height, width = image.shape[:2]
    cascade = load_face_cascade()
    if cascade is not None:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(80, 80),
        )
        if len(faces) > 0:
            return tuple(max(faces, key=lambda item: item[2] * item[3]))

    side = int(min(width, height) * 0.72)
    x = max(0, (width - side) // 2)
    y = max(0, int(height * 0.16))
    return (x, y, side, min(side, height - y))


def analyze_image(image_path: Path, output_path: Path) -> None:
    image = read_image_unicode(image_path)
    if image is None:
        raise ValueError(f"图片读取失败: {image_path}")

    x, y, w, h = detect_face(image)

    hair_y1 = max(0, y - int(h * 0.55))
    hair_y2 = min(image.shape[0], y + int(h * 0.12))
    hair_x1 = x
    hair_x2 = min(image.shape[1], x + w)
    hair_region = image[hair_y1:hair_y2, hair_x1:hair_x2]
    hair_rgb = get_main_color(hair_region, k=5)[::-1]

    eye_y1 = y + int(h * 0.32)
    eye_y2 = y + int(h * 0.55)
    left_eye = (
        x + int(w * 0.12),
        eye_y1,
        x + int(w * 0.40),
        eye_y2,
    )
    right_eye = (
        x + int(w * 0.60),
        eye_y1,
        x + int(w * 0.88),
        eye_y2,
    )

    eye_colors = []
    for ex1, ey1, ex2, ey2 in (left_eye, right_eye):
        crop = image[
            max(0, ey1) : min(image.shape[0], ey2),
            max(0, ex1) : min(image.shape[1], ex2),
        ]
        eye_colors.append(get_main_color(crop, k=3)[::-1])

    eye_rgb = np.mean(eye_colors, axis=0).astype(int)

    debug = image.copy()
    cv2.rectangle(debug, (x, y), (x + w, y + h), (0, 255, 0), 2)
    cv2.rectangle(debug, (hair_x1, hair_y1), (hair_x2, hair_y2), (255, 0, 0), 2)
    for ex1, ey1, ex2, ey2 in (left_eye, right_eye):
        cv2.rectangle(debug, (ex1, ey1), (ex2, ey2), (0, 0, 255), 2)

    save_image_unicode(output_path, debug)

    print(f"图片: {image_path}")
    print(f"头发颜色: {color_name(hair_rgb)} RGB: {tuple(map(int, hair_rgb))}")
    print(f"眼睛颜色: {color_name(eye_rgb)} RGB: {tuple(map(int, eye_rgb))}")
    print(f"识别结果图: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="动漫角色发色瞳色识别演示脚本")
    parser.add_argument("image", type=Path, help="输入图片路径")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=BASE_DIR / "docs" / "images" / "识别结果.png",
        help="输出带检测框的图片路径",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    analyze_image(args.image, args.output)
