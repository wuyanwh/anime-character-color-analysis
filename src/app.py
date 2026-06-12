from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from flask import Flask, render_template, request, send_from_directory
from sklearn.cluster import KMeans
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "models"
RUNTIME_DIR = BASE_DIR / "runtime"
UPLOAD_DIR = RUNTIME_DIR / "uploads"
DEBUG_DIR = RUNTIME_DIR / "debug"

for directory in (UPLOAD_DIR, DEBUG_DIR):
    directory.mkdir(parents=True, exist_ok=True)

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def load_cascade() -> cv2.CascadeClassifier | None:
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


FACE_CASCADE = load_cascade()
EYE_CASCADE = cv2.CascadeClassifier(
    str(Path(cv2.data.haarcascades) / "haarcascade_eye.xml")
)


def load_character_db() -> list[dict]:
    """Load character metadata from formal data first, then sample data."""
    xlsx_path = DATA_DIR / "characters.xlsx"
    csv_path = DATA_DIR / "characters.csv"
    sample_path = DATA_DIR / "characters_sample.csv"

    try:
        if xlsx_path.exists():
            df = pd.read_excel(xlsx_path)
        elif csv_path.exists():
            df = pd.read_csv(csv_path)
        elif sample_path.exists():
            df = pd.read_csv(sample_path)
        else:
            return []
    except Exception as exc:
        print(f"角色数据库读取失败: {exc}")
        return []

    df = df.fillna("")
    rename_map = {
        "角色名": "name",
        "姓名": "name",
        "名称": "name",
        "发色": "hair",
        "瞳色": "eye",
        "萌点": "chara",
        "特点": "chara",
        "作品": "source",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    for column in ("name", "hair", "eye", "chara", "source"):
        if column not in df.columns:
            df[column] = ""

    return df.to_dict("records")


def sample_table_rows() -> list[dict]:
    return [
        {
            "name": "初音未来",
            "source": "VOCALOID",
            "hair": "青色",
            "eye": "青色",
            "chara": "双马尾、歌姬",
        },
        {
            "name": "示例角色",
            "source": "示例作品",
            "hair": "金色",
            "eye": "蓝色",
            "chara": "元气、学生",
        },
    ]


def read_image_unicode(path: Path) -> np.ndarray | None:
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def save_image_unicode(path: Path, image: np.ndarray) -> None:
    suffix = path.suffix or ".jpg"
    ok, encoded = cv2.imencode(suffix, image)
    if ok:
        encoded.tofile(str(path))


def enhance_image(image: np.ndarray) -> np.ndarray:
    image = cv2.convertScaleAbs(image, alpha=1.12, beta=8)
    return cv2.bilateralFilter(image, 5, 45, 45)


def dominant_color_bgr(image: np.ndarray, k: int = 4) -> tuple[int, int, int]:
    if image is None or image.size == 0:
        return (0, 0, 0)

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    pixels = hsv.reshape((-1, 3))
    valid_pixels = []

    for h, s, v in pixels:
        if v < 35 or v > 250:
            continue
        if s < 30:
            continue
        valid_pixels.append([h, s, v])

    if not valid_pixels:
        return (0, 0, 0)

    valid_pixels = np.array(valid_pixels, dtype=np.float32)
    cluster_count = min(k, len(valid_pixels))
    kmeans = KMeans(n_clusters=cluster_count, random_state=42, n_init=10)
    kmeans.fit(valid_pixels)

    counts = np.bincount(kmeans.labels_)
    main_hsv = np.uint8([[kmeans.cluster_centers_[np.argmax(counts)]]])
    main_bgr = cv2.cvtColor(main_hsv, cv2.COLOR_HSV2BGR)[0][0]
    return tuple(map(int, main_bgr))


def color_name(rgb: tuple[int, int, int] | np.ndarray) -> str:
    r, g, b = [int(x) for x in rgb]
    hsv = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV)[0][0]
    h, s, v = [int(x) for x in hsv]

    if v < 45:
        return "黑色"
    if s < 20 and v > 210:
        return "白色"
    if s < 30:
        return "灰色"
    if h <= 8 or h >= 172:
        return "红色"
    if 8 < h <= 18:
        return "橙色"
    if 18 < h <= 35:
        return "金色" if s < 95 and v > 155 else "黄色"
    if 35 < h <= 85:
        return "绿色"
    if 85 < h <= 100:
        return "青色"
    if 100 < h <= 130:
        return "蓝色"
    if 130 < h <= 155:
        return "紫色"
    if 155 < h < 172:
        return "粉色"
    return "其他"


def detect_face(image: np.ndarray) -> tuple[int, int, int, int]:
    height, width = image.shape[:2]

    if FACE_CASCADE is not None:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        faces = FACE_CASCADE.detectMultiScale(
            gray,
            scaleFactor=1.08,
            minNeighbors=4,
            minSize=(70, 70),
        )
        if len(faces) > 0:
            return tuple(max(faces, key=lambda item: item[2] * item[3]))

    side = int(min(width, height) * 0.72)
    x = max(0, (width - side) // 2)
    y = max(0, int(height * 0.16))
    return (x, y, side, min(side, height - y))


def estimate_regions(
    image: np.ndarray,
    face: tuple[int, int, int, int],
) -> tuple[np.ndarray, list[tuple[int, int, int, int]]]:
    x, y, w, h = face
    image_h, image_w = image.shape[:2]

    hair_y1 = max(0, y - int(h * 0.42))
    hair_y2 = min(image_h, y + int(h * 0.18))
    hair_x1 = max(0, x)
    hair_x2 = min(image_w, x + w)
    hair_region = image[hair_y1:hair_y2, hair_x1:hair_x2]

    face_gray = cv2.cvtColor(image[y : y + h, x : x + w], cv2.COLOR_BGR2GRAY)
    eye_regions = []
    if not EYE_CASCADE.empty():
        eyes = EYE_CASCADE.detectMultiScale(
            face_gray,
            scaleFactor=1.08,
            minNeighbors=4,
            minSize=(18, 18),
        )
        for ex, ey, ew, eh in eyes:
            if ey > h * 0.58:
                continue
            eye_regions.append((x + ex, y + ey, ew, eh))

    if len(eye_regions) < 2:
        eye_y1 = y + int(h * 0.31)
        eye_y2 = y + int(h * 0.56)
        eye_regions = [
            (x + int(w * 0.12), eye_y1, int(w * 0.30), eye_y2 - eye_y1),
            (x + int(w * 0.58), eye_y1, int(w * 0.30), eye_y2 - eye_y1),
        ]

    return hair_region, eye_regions[:2]


def draw_debug(
    image: np.ndarray,
    face: tuple[int, int, int, int],
    eye_regions: list[tuple[int, int, int, int]],
) -> np.ndarray:
    debug = image.copy()
    x, y, w, h = face
    cv2.rectangle(debug, (x, y), (x + w, y + h), (0, 180, 80), 2)

    hair_y1 = max(0, y - int(h * 0.42))
    hair_y2 = min(image.shape[0], y + int(h * 0.18))
    cv2.rectangle(debug, (x, hair_y1), (x + w, hair_y2), (255, 80, 0), 2)

    for ex, ey, ew, eh in eye_regions:
        cv2.rectangle(debug, (ex, ey), (ex + ew, ey + eh), (40, 80, 255), 2)

    return debug


def split_traits(value: str) -> list[str]:
    text = str(value).replace("，", ",").replace("、", ",").replace("/", ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def build_recommendations(results: list[dict], db: list[dict]) -> tuple[list[dict], list[dict]]:
    if not results or not db:
        return [], []

    wanted_hair = Counter(item["hair"] for item in results)
    wanted_eye = Counter(item["eye"] for item in results)
    trait_counter: Counter[str] = Counter()
    recommendations = []

    for character in db:
        hair = str(character.get("hair", "")).strip()
        eye = str(character.get("eye", "")).strip()
        traits = split_traits(character.get("chara", ""))
        score = 0

        if hair in wanted_hair:
            score += 45
        if eye in wanted_eye:
            score += 45
        if traits:
            score += min(10, len(traits))

        if score <= 0:
            continue

        for trait in traits:
            trait_counter[trait] += 1

        recommendations.append(
            {
                "name": character.get("name") or "未命名角色",
                "source": character.get("source", ""),
                "hair": hair,
                "eye": eye,
                "chara": "、".join(traits),
                "matched_traits": traits[:5],
                "score": min(score, 100),
            }
        )

    recommendations.sort(key=lambda item: item["score"], reverse=True)
    common_traits = [
        {"trait": trait, "count": count}
        for trait, count in trait_counter.most_common(10)
    ]
    return recommendations[:10], common_traits


def process_image(image_path: Path) -> dict | None:
    image = read_image_unicode(image_path)
    if image is None:
        return None

    image = enhance_image(image)
    face = detect_face(image)
    hair_region, eye_regions = estimate_regions(image, face)

    hair_rgb = dominant_color_bgr(hair_region, k=4)[::-1]
    eye_colors = []

    image_h, image_w = image.shape[:2]
    for ex, ey, ew, eh in eye_regions:
        pad = 6
        crop = image[
            max(0, ey - pad) : min(image_h, ey + eh + pad),
            max(0, ex - pad) : min(image_w, ex + ew + pad),
        ]
        eye_colors.append(dominant_color_bgr(crop, k=3)[::-1])

    eye_rgb = np.mean(eye_colors, axis=0).astype(int) if eye_colors else np.array([0, 0, 0])
    debug_name = f"debug_{image_path.name}"
    save_image_unicode(DEBUG_DIR / debug_name, draw_debug(image, face, eye_regions))

    return {
        "filename": image_path.name,
        "filepath": f"/uploads/{image_path.name}",
        "debug": f"/debug/{debug_name}",
        "hair": color_name(hair_rgb),
        "eye": color_name(eye_rgb),
        "hair_rgb": tuple(map(int, hair_rgb)),
        "eye_rgb": tuple(map(int, eye_rgb)),
    }


@app.route("/uploads/<path:filename>")
def uploaded_file(filename: str):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/debug/<path:filename>")
def debug_file(filename: str):
    return send_from_directory(DEBUG_DIR, filename)


@app.route("/", methods=["GET", "POST"])
def index():
    results = []
    db = load_character_db()

    if request.method == "POST":
        for file in request.files.getlist("images"):
            if not file or not file.filename or not allowed_file(file.filename):
                continue

            filename = secure_filename(file.filename)
            if not filename:
                filename = f"upload_{len(results) + 1}.jpg"
            save_path = UPLOAD_DIR / filename
            file.save(save_path)

            result = process_image(save_path)
            if result:
                results.append(result)

    recommendations, common_traits = build_recommendations(results, db)
    return render_template(
        "index.html",
        results=results,
        recommend_names=recommendations,
        common_traits=common_traits,
        has_database=bool(db),
        sample_rows=sample_table_rows(),
    )


if __name__ == "__main__":
    app.run(debug=True)
