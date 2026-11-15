from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from certificate_doctor.engine import diagnose
from certificate_doctor.report import to_json, to_markdown

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT.parent / "samples"
ARTIFACTS = Path(tempfile.gettempdir()) / "certificate-doctor-artifacts"
ARTIFACTS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Certificate Doctor", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"title": "Certificate Doctor"},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "product": "certificate-doctor"}


def _artifact_url(path: str | None, token: str, kind: str) -> str | None:
    if not path:
        return None
    return f"/api/artifact/{token}/{kind}"


@app.get("/api/artifact/{token}/{kind}")
async def get_artifact(token: str, kind: str) -> FileResponse:
    if kind not in {"overlay", "heatmap"}:
        return JSONResponse({"error": "Unknown artifact"}, status_code=404)  # type: ignore[return-value]
    base = ARTIFACTS / token
    # Find matching file
    matches = list(base.glob(f"*.{kind}.png"))
    if not matches:
        return JSONResponse({"error": "Not found"}, status_code=404)  # type: ignore[return-value]
    return FileResponse(matches[0], media_type="image/png")


@app.post("/api/scan")
async def api_scan(
    file: UploadFile | None = File(None),
    sample: str | None = Form(None),
) -> JSONResponse:
    tmp_path: Path | None = None
    try:
        if sample in {"genuine", "tampered"}:
            path = SAMPLES / f"{sample}_marksheet.jpg"
            if not path.exists():
                # Backward-compatible PNG samples
                path = SAMPLES / f"{sample}_marksheet.png"
            if not path.exists():
                return JSONResponse({"error": f"Sample missing: {sample}_marksheet.jpg"}, status_code=404)
            file_name = path.name
        elif file is not None and file.filename:
            suffix = Path(file.filename).suffix.lower() or ".png"
            allowed = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".pdf"}
            if suffix not in allowed:
                return JSONResponse(
                    {"error": "Upload an image (PNG/JPEG/WebP/TIFF/BMP) or PDF."},
                    status_code=400,
                )
            raw = await file.read()
            if len(raw) > 25 * 1024 * 1024:
                return JSONResponse({"error": "File too large (25 MB max)."}, status_code=400)
            fd, name = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            tmp_path = Path(name)
            tmp_path.write_bytes(raw)
            path = tmp_path
            file_name = file.filename
        else:
            return JSONResponse({"error": "Upload a file or choose a sample."}, status_code=400)

        token = uuid.uuid4().hex
        out_dir = ARTIFACTS / token
        result = diagnose(path, out_dir=out_dir, file_name=file_name)
        payload = result.to_dict()
        payload["markdown"] = to_markdown(result)
        payload["json_export"] = to_json(result)
        payload["overlay_url"] = _artifact_url(result.overlay_path, token, "overlay")
        payload["heatmap_url"] = _artifact_url(result.heatmap_path, token, "heatmap")
        return JSONResponse(payload)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def create_app() -> FastAPI:
    return app
