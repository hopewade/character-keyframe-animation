#!/usr/bin/env python3
"""Offline whole-character optical-flow interpolation; never animates layers.

Dependencies: Pillow, numpy, opencv-python-headless. Install them separately.
Coordinates in landmarks/translation are source-image pixels. Without an explicit
transform the input must already have a locked camera, scale and composition.
Numerical registration checks do not establish visual quality: inspect previews.
"""
import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path

try:
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw
except ImportError as exc:
    raise SystemExit("Missing dependency. Install Pillow, numpy and opencv-python-headless in your chosen environment.") from exc


def shape_for(limit, original, allow_upscale=False):
    if isinstance(limit, list):
        if len(limit) != 2:
            raise ValueError("Size arrays must contain [width, height].")
        size = tuple(map(int, limit))
        if abs(size[0] * original[1] - size[1] * original[0]) > max(original):
            raise ValueError("Explicit [width,height] must preserve the source aspect ratio; nonuniform stretching is not allowed.")
        if not allow_upscale and (size[0] > original[0] or size[1] > original[1]):
            raise ValueError("Explicit size would upscale source art. Set allow_upscale:true deliberately or choose a smaller size.")
    else:
        ratio = float(limit) / max(original)
        if not allow_upscale:
            ratio = min(ratio, 1.)
        size = tuple(max(1, round(n * ratio)) for n in original)
    if min(size) < 24:
        raise ValueError("Output and flow dimensions must be at least 24 pixels.")
    return size


def grid_for(size):
    y, x = np.mgrid[:size[1], :size[0]].astype(np.float32)
    return np.stack([x, y], axis=-1)


def sample(array, points, border=cv2.BORDER_REPLICATE):
    return cv2.remap(array, points[..., 0].astype(np.float32),
                     points[..., 1].astype(np.float32), cv2.INTER_LINEAR,
                     borderMode=border)


def premultiply(rgba):
    result = np.asarray(rgba, dtype=np.float32) / 255
    result[..., :3] *= result[..., 3:4]
    return result


def to_image(premultiplied):
    a = np.clip(premultiplied[..., 3:4], 0, 1)
    rgb = np.divide(premultiplied[..., :3], a,
                    out=np.zeros_like(premultiplied[..., :3]), where=a > 1e-7)
    rgba = np.concatenate([np.clip(rgb, 0, 1), a], axis=-1)
    return Image.fromarray(np.uint8(np.rint(rgba * 255)), "RGBA")


def transform_info(frame):
    transform = frame.get("transform", {})
    scale = float(transform.get("scale", 1))
    translation = np.asarray(transform.get("translation", [0, 0]), np.float32)
    if not np.isfinite(scale) or scale <= 0 or translation.shape != (2,) or not np.isfinite(translation).all():
        raise ValueError("Transforms need a positive scale and finite [x, y] translation.")
    return scale, translation


def aligned_image(photo, frame, size, original):
    scale, translation = transform_info(frame)
    q = (grid_for(size) + .5) * (np.asarray(original) / np.asarray(size)) - .5
    return sample(photo, (q - translation) / scale, cv2.BORDER_CONSTANT)


def grey(photo):
    rgb = photo[..., :3] + .9 * (1 - photo[..., 3:4])
    return cv2.cvtColor(np.uint8(np.clip(np.rint(rgb * 255), 0, 255)), cv2.COLOR_RGB2GRAY)


def landmark_prior(a, b, size, original):
    """TPS prior only when >= 3 shared, non-collinear landmark pairs exist."""
    common = sorted(set(a.get("landmarks", {})) & set(b.get("landmarks", {})))
    if len(common) < 3:
        return None, common
    sa, ta = transform_info(a)
    sb, tb = transform_info(b)
    p = np.asarray([a["landmarks"][key] for key in common], np.float64)
    q = np.asarray([b["landmarks"][key] for key in common], np.float64)
    if p.shape != (len(common), 2) or q.shape != p.shape or not np.isfinite(p).all() or not np.isfinite(q).all():
        raise ValueError("Every landmark must contain finite [x, y] coordinates.")
    p = (p * sa + ta + .5) * (np.asarray(size) / original) - .5
    q = (q * sb + tb + .5) * (np.asarray(size) / original) - .5
    if np.linalg.matrix_rank(np.c_[np.ones(len(p)), p]) < 3 or np.linalg.matrix_rank(np.c_[np.ones(len(q)), q]) < 3:
        return None, common
    # Normalization keeps the TPS solve independent of image resolution.
    norm = float(max(size))
    pn = p / norm
    delta = (q - p) / norm
    r2 = ((pn[:, None] - pn[None]) ** 2).sum(-1)
    kernel = r2 * np.log(np.maximum(r2, 1e-12))
    affine = np.c_[np.ones(len(p)), pn]
    system = np.block([[kernel + np.eye(len(p)) * 1e-6, affine],
                       [affine.T, np.zeros((3, 3))]])
    weights = np.linalg.solve(system, np.r_[delta, np.zeros((3, 2))])
    grid = grid_for(size).reshape(-1, 2) / norm
    output = np.empty_like(grid)
    for start in range(0, len(grid), 8192):
        points = grid[start:start + 8192]
        distance = ((points[:, None] - pn[None]) ** 2).sum(-1)
        basis = distance * np.log(np.maximum(distance, 1e-12))
        output[start:start + len(points)] = np.c_[basis, np.ones(len(points)), points] @ weights
    return (output.reshape(size[1], size[0], 2) * norm).astype(np.float32), common


def jacobian_stats(flow):
    dx_y, dx_x = np.gradient(flow[..., 0])
    dy_y, dy_x = np.gradient(flow[..., 1])
    # det(I + t grad F) = 1 + b*t + a*t*t. Check endpoints and
    # every valid convex vertex, rather than a finite set of sampled times.
    quadratic = dx_x * dy_y - dx_y * dy_x
    linear = dx_x + dy_y
    endpoint = 1 + linear + quadratic
    minimum = np.minimum(1., endpoint)
    vertex = np.divide(-linear, 2 * quadratic, out=np.zeros_like(linear),
                       where=np.abs(quadratic) > 1e-12)
    valid = (quadratic > 0) & (vertex > 0) & (vertex < 1)
    minimum = np.where(valid, np.minimum(minimum, 1 + linear * vertex + quadratic * vertex * vertex), minimum)
    return {"minimumJacobian": float(minimum.min()),
            "endpointMinimumJacobian": float(endpoint.min()),
            "intermediateCheck": "analytic endpoints and quadratic vertices, t in [0,1]",
            "foldedPixelsAtEndpoint": int(np.count_nonzero(endpoint <= 0))}


def score(a, b, alpha_a, alpha_b, flow, regions):
    grid = grid_for((a.shape[1], a.shape[0]))
    target = sample(b, grid + flow)
    mask = np.maximum(alpha_a, sample(alpha_b, grid + flow)) > .05
    difference = np.abs(a.astype(np.float32) - target.astype(np.float32))
    results = {}
    weighted, weights = 0., 0.
    for region in regions:
        name, bounds = region["name"], region["bounds"]
        x0, y0, x1, y1 = bounds
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError("Region bounds must be normalized [x0,y0,x1,y1] inside [0,1].")
        w, h = a.shape[1], a.shape[0]
        sl = np.s_[int(y0 * h):max(int(y0 * h) + 1, int(y1 * h)),
                   int(x0 * w):max(int(x0 * w) + 1, int(x1 * w))]
        values = difference[sl][mask[sl]]
        if not values.size:
            raise ValueError(f"Quality region '{name}' contains no visible character pixels.")
        mae = float(values.mean())
        weight = float(region.get("weight", 1))
        if not np.isfinite(weight) or weight <= 0:
            raise ValueError("Region weights must be positive and finite.")
        results[name] = {"greyMAE_0_255": mae, "visiblePixels": int(values.size), "weight": weight}
        weighted += mae * weight
        weights += weight
    return weighted / weights, results


def dis_flow(a, b, initial=None):
    algorithm = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    algorithm.setFinestScale(0)
    algorithm.setGradientDescentIterations(60)
    algorithm.setVariationalRefinementIterations(15)
    return algorithm.calc(a, b, None if initial is None else initial.copy())


def exponentiate(velocity, grid):
    displacement = velocity / 64
    for _ in range(6):
        displacement = displacement + sample(displacement, grid + displacement)
    return displacement


def register_pair(a, b, prior, config):
    ga, gb = grey(a), grey(b)
    grid = grid_for((ga.shape[1], ga.shape[0]))
    raw = [("DIS", dis_flow(ga, gb, prior))]
    flags = cv2.OPTFLOW_USE_INITIAL_FLOW if prior is not None else 0
    raw.append(("Farneback", cv2.calcOpticalFlowFarneback(
        ga, gb, None if prior is None else prior.copy(), .5, 5, 31, 12, 7, 1.5, flags)))
    if prior is not None:
        raw.append(("TPS+localDIS", dis_flow(ga, sample(gb, grid + prior))))
    regions = config.get("regions") or [{"name": "visible_character", "bounds": [0, 0, 1, 1], "weight": 1}]
    threshold = float(config.get("minimum_jacobian", .2))
    if not .03 <= threshold < 1:
        raise ValueError("minimum_jacobian must be >= 0.03 and < 1. Values below 0.1 require close visual review.")
    candidates = []

    def consider(field, method, sigma, weight):
        if not np.isfinite(field).all():
            return
        stats = jacobian_stats(field)
        if stats["minimumJacobian"] < threshold:
            return
        cost, detail = score(ga, gb, a[..., 3], b[..., 3], field, regions)
        candidates.append((cost, field, {"method": method, "sigma": sigma, "weight": weight,
                                       "weightedGreyMAE_0_255": cost, "regions": detail, **stats}))

    if prior is not None:
        consider(prior, "TPS-prior", 0, 1)
    for method, field in raw:
        for sigma in [1., 2., 3.5, 5.]:
            smooth = cv2.GaussianBlur(field, (0, 0), sigma)
            if method != "TPS+localDIS":
                consider(smooth, method, sigma, 1)
            if prior is not None and config.get("scaling_squaring", True):
                residual = smooth if method == "TPS+localDIS" else smooth - prior
                for weight in [1., .7, .4]:
                    offset = exponentiate(residual * weight, grid)
                    consider(offset + sample(prior, grid + offset), method + "+residual-exp", sigma, weight)
    if not candidates:
        raise RuntimeError("No safe optical-flow candidate. Improve/insert source keyframes or correct landmarks; no sequence was accepted.")
    candidates.sort(key=lambda item: item[0])
    _, selected, report = candidates[0]
    report["safeCandidateCount"] = len(candidates)
    report["bestCandidates"] = [dict(item[2]) for item in candidates[:5]]
    report["visualQualityApproved"] = False
    report["configuredMinimumJacobian"] = threshold
    report["needsCloseVisualReview"] = threshold < .1
    return selected.astype(np.float32), report


def inverse_map(flow, q, t):
    """Solve q = p + t F(p) without browser-time deformation."""
    p = q - t * sample(flow, q)
    fy, fx = np.gradient(flow, axis=(0, 1))
    for _ in range(16):
        error = p + t * sample(flow, p) - q
        dx, dy = sample(fx, p), sample(fy, p)
        aa, bb = 1 + t * dx[..., 0], t * dy[..., 0]
        cc, dd = t * dx[..., 1], 1 + t * dy[..., 1]
        det = aa * dd - bb * cc
        if np.any(~np.isfinite(det)) or np.any(det <= 1e-5):
            raise RuntimeError("Unsafe intermediate inverse mapping; improve keyframe correspondence.")
        update = np.stack([(dd * error[..., 0] - bb * error[..., 1]) / det,
                           (-cc * error[..., 0] + aa * error[..., 1]) / det], axis=-1)
        p -= np.clip(update, -max(flow.shape[:2]) / 8, max(flow.shape[:2]) / 8)
    residual = np.linalg.norm(p + t * sample(flow, p) - q, axis=-1)
    return p, float(np.percentile(residual, 99))


def interpolate(a, b, flow, t, output_size):
    flow_size = (flow.shape[1], flow.shape[0])
    q = (grid_for(output_size) + .5) * (np.asarray(flow_size) / output_size) - .5
    if t <= 0:
        return sample(a, q, cv2.BORDER_CONSTANT), 0.
    if t >= 1:
        return sample(b, q, cv2.BORDER_CONSTANT), 0.
    p, error = inverse_map(flow, q, t)
    # Both full portraits are brought into correspondence before alpha blending.
    first = sample(a, p, cv2.BORDER_CONSTANT)
    second = sample(b, p + sample(flow, p), cv2.BORDER_CONSTANT)
    return first * (1 - t) + second * t, error


def previews(images, labels, output):
    thumb_size = (240, 280)
    cols = min(len(images), 5)
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_size[0], rows * thumb_size[1]), "#eee8dc")
    draw = ImageDraw.Draw(sheet)
    for i, (image, label) in enumerate(zip(images, labels)):
        picture = image.copy()
        picture.thumbnail((224, 240))
        x, y = i % cols * 240, i // cols * 280
        sheet.paste(picture, (x + (240 - picture.width) // 2, y + 8), picture)
        draw.text((x + 10, y + 252), label, fill="#3c332a")
    sheet.save(output / "contact-sheet.jpg", quality=92)
    small = []
    for image in images:
        picture = image.copy()
        picture.thumbnail((300, 300))
        canvas = Image.new("RGBA", (300, 300), "#eee8dc")
        canvas.alpha_composite(picture, ((300 - picture.width) // 2, (300 - picture.height) // 2))
        small.append(canvas.convert("RGB"))
    loop = small + small[-2:0:-1]
    loop[0].save(output / "loop.gif", save_all=True, append_images=loop[1:],
                 duration=80, loop=0, disposal=2)


def build(config_path, output, preview_only):
    config = json.loads(config_path.read_text(encoding="utf-8"))
    frames = config["keyframes"]
    positions = [float(frame["position"]) for frame in frames]
    front = int(config["front_index"])
    if len(frames) < 2 or not np.isfinite(positions).all() or any(b <= a for a, b in zip(positions, positions[1:])):
        raise ValueError("At least two keyframes with finite, strictly increasing positions are required.")
    if not 0 <= front < len(frames) or abs(positions[front]) > 1e-8:
        raise ValueError("front_index must identify a keyframe whose position is 0.")
    photos, original = [], None
    for frame in frames:
        path = (config_path.parent / frame["file"]).resolve()
        with Image.open(path) as image:
            if image.mode != "RGBA":
                raise ValueError(f"Expected a transparent RGBA source, got {image.mode}: {path}")
            if original is not None and image.size != original:
                raise ValueError("All source keyframes must have exactly equal dimensions.")
            original = image.size
            if image.getextrema()[3][0] == 255:
                raise ValueError(f"Source has no transparent pixels: {path}")
            photos.append(premultiply(image))
    output_size = shape_for(config.get("output_size", 768), original, config.get("allow_upscale", False))
    flow_size = shape_for(config.get("flow_size", 384), original, config.get("allow_upscale", False))
    steps = int(config.get("steps_per_pair", 32))
    quality = int(config.get("quality", 90))
    if steps < 2 or not 1 <= quality <= 100:
        raise ValueError("steps_per_pair must be >= 2 and quality must be 1..100.")
    output.mkdir(parents=True, exist_ok=True)
    frame_dir = output / "frames"
    frame_dir.mkdir(exist_ok=True)
    aligned = [aligned_image(p, f, flow_size, original) for p, f in zip(photos, frames)]
    # Render photos at final resolution via original source pixels, retaining detail.
    render_photos = [aligned_image(p, f, output_size, original) for p, f in zip(photos, frames)]
    to_image(render_photos[front]).save(output / "poster.png")
    flows, reports = [], []
    for pair in range(len(frames) - 1):
        prior, names = landmark_prior(frames[pair], frames[pair + 1], flow_size, np.asarray(original))
        field, report = register_pair(aligned[pair], aligned[pair + 1], prior, config)
        report.update({"pair": pair, "sharedLandmarks": names, "tpsPriorUsed": prior is not None,
                       "units": "flow-grid pixels", "flowSize": list(flow_size)})
        np.savez_compressed(output / f"flow-{pair:03d}.npz", forward=field)
        flows.append(field)
        reports.append(report)
        print(json.dumps({"pair": pair, "method": report["method"], "minimumJacobian": report["minimumJacobian"],
                          "greyMAE": report["weightedGreyMAE_0_255"]}), flush=True)
    records, preview_images, preview_labels, errors = [], [], [], []
    for pair, field in enumerate(flows):
        times = [0., .5, 1.] if preview_only else list(np.linspace(0, 1, steps + 1))
        resized = cv2.resize(field, output_size, interpolation=cv2.INTER_LINEAR)
        resized *= (np.asarray(output_size) / flow_size).astype(np.float32)
        for t in times:
            if pair > 0 and t == 0:
                continue
            # Convert coordinates, not artwork: the field remains float32, unquantized.
            pixels, error = interpolate(render_photos[pair], render_photos[pair + 1], resized, t, output_size)
            if error > 1:
                raise RuntimeError(f"Inverse correspondence residual {error:.3f}px exceeds 1px at pair {pair}, t={t:.3f}.")
            errors.append(error)
            image = to_image(pixels)
            index = len(records)
            filename = f"frame-{index:05d}.webp"
            image.save(frame_dir / filename, "WEBP", quality=quality, method=5, exact=True)
            position = positions[pair] * (1 - t) + positions[pair + 1] * t
            records.append({"index": index, "position": float(position), "src": f"frames/{filename}",
                            "sourcePair": [pair, pair + 1], "blend": float(t),
                            "isSourceKeyframe": t in (0., 1.)})
            if preview_only or (index % max(1, steps // 4) == 0) or (pair == len(flows) - 1 and t == 1):
                preview_images.append(image)
                preview_labels.append(f"pose {position:+.3f}")
    front_frame = min(range(len(records)), key=lambda i: abs(records[i]["position"]))
    sequence = {"version": 1, "kind": "whole-character-keyframe-flow-interpolation",
                "previewOnly": preview_only, "frameSize": list(output_size), "frontFrame": front_frame,
                "poster": "poster.png",
                "frameCount": len(records), "positions": [f["position"] for f in records],
                "sourcePositions": positions, "stepsPerPair": steps, "frames": records,
                "method": "Full RGBA portraits; optional TPS landmark prior; safe dense optical-flow registration; offline inverse mapping and premultiplied-alpha interpolation. No segmented neck/body layers.",
                "visualReviewRequired": True}
    (output / "sequence.json").write_text(json.dumps(sequence, ensure_ascii=False, indent=2), encoding="utf-8")
    quality_report = {"numericalChecksOnly": True, "visualQualityApproved": False,
                      "needsCloseVisualReview": any(r["needsCloseVisualReview"] for r in reports),
                      "note": "Inspect eyes, glasses, hair, neck, silhouette and reverse playback. Ghosting requires source/landmark correction and rerun; more frames do not repair inconsistent artwork.",
                      "maxInverseResidualP99Pixels": max(errors), "pairs": reports}
    (output / "quality-report.json").write_text(json.dumps(quality_report, indent=2), encoding="utf-8")
    previews(preview_images, preview_labels, output)
    return len(records)


def run(config_path, output, preview_only):
    """Build in isolation; publish only complete results, preserving old output on failure.

    The output directory is a dedicated generated-artifact directory. A successful
    build replaces that directory; keep source art and unrelated files elsewhere.
    """
    validate_output(config_path, output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-build-", dir=output.parent))
    backup = None
    try:
        count = build(config_path, stage, preview_only)
        # Recheck immediately before publication in case another process added
        # a user file while registration/rendering was running.
        validate_output(config_path, output)
        if output.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{output.name}-previous-", dir=output.parent))
            backup.rmdir()
            output.rename(backup)
        try:
            stage.rename(output)
        except OSError:
            if backup is not None:
                backup.rename(output)
                backup = None
            raise
        if backup is not None:
            shutil.rmtree(backup)
            backup = None
        print(json.dumps({"sequence": str(output / "sequence.json"), "frames": count,
                          "previewOnly": preview_only, "visualReviewRequired": True}), flush=True)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def validate_output(config_path, output):
    """Refuse to replace sources, unrelated files, symlinks or unknown folders."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    inputs = [config_path] + [(config_path.parent / f["file"]).resolve()
                              for f in config["keyframes"]]
    if any(path.is_relative_to(output) for path in inputs):
        raise ValueError("Keep the configuration and source images outside the generated output directory.")
    if output.is_symlink():
        raise ValueError("Refusing to replace a symlink output directory.")
    if not output.exists():
        return
    if not output.is_dir():
        raise ValueError("Output must be a dedicated generated-artifact directory.")
    entries = list(output.iterdir())
    if not entries:
        return
    manifest = output / "sequence.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Nonempty output has no owned sequence manifest; existing files are preserved.")
    previous = json.loads(manifest.read_text(encoding="utf-8"))
    if previous.get("kind") != "whole-character-keyframe-flow-interpolation":
        raise ValueError("Output sequence kind is unrelated to this builder; existing files are preserved.")
    allowed = {"sequence.json", "quality-report.json", "poster.png", "contact-sheet.jpg", "loop.gif",
               "character-player.js", "character-player.css", "index.html", "preview.html"}
    for entry in entries:
        if entry.is_symlink():
            raise ValueError(f"Refusing symlink in generated output: {entry.name}")
        if entry.is_dir():
            if entry.name != "frames":
                raise ValueError(f"Unknown output folder '{entry.name}'; existing files are preserved.")
            for frame in entry.iterdir():
                if frame.is_symlink() or not frame.is_file() or not re.fullmatch(r"frame-\d+\.webp", frame.name):
                    raise ValueError(f"Unknown output frame entry '{frame.name}'; existing files are preserved.")
        elif not entry.is_file():
            raise ValueError(f"Non-file output entry '{entry.name}'; existing files are preserved.")
        elif entry.name not in allowed and not re.fullmatch(r"flow-\d+\.npz", entry.name):
            raise ValueError(f"Unknown output file '{entry.name}'; existing files are preserved.")
        elif entry.name in {"index.html", "preview.html"}:
            if "<!-- character-keyframe-player -->" not in entry.read_text(encoding="utf-8"):
                raise ValueError(f"Unrelated page '{entry.name}'; existing files are preserved.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preview-only", action="store_true", help="Render only 0, .5 and 1 per pair for visual review before a full run.")
    args = parser.parse_args()
    cv2.setNumThreads(1)
    try:
        if args.output.is_symlink():
            raise ValueError("Refusing to replace a symlink output directory.")
        run(args.config.resolve(), args.output.resolve(), args.preview_only)
    except (ValueError, RuntimeError, KeyError, OSError, np.linalg.LinAlgError) as exc:
        raise SystemExit(f"Sequence build failed; existing output was not replaced by an incomplete build: {exc}") from exc


if __name__ == "__main__":
    main()
