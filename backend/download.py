import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter()
ROOT = Path(__file__).resolve().parent.parent
JUNK_DIRS = {"node_modules", ".git", ".emergent", "__pycache__", "build", ".pytest_cache", ".cache",
             ".venv", "venv", ".ruff_cache"}
SKIP_DIRS = {"test_reports", "memory", "tests", "plan"}
SKIP_NAMES = {"test_result.md", "design_guidelines.json"}
SKIP_MD = {"test_credentials.md"}
SKIP_SUFFIXES = {".log", ".pyc"}


def env_example(env_path: Path) -> str:
    keys = [ln.split("=", 1)[0] for ln in env_path.read_text().splitlines() if "=" in ln and not ln.startswith("#")]
    return "\n".join(f"{k}=" for k in keys) + "\n"


def build_zip() -> bytes:
    buf = io.BytesIO()
    written = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:

        def put(arc, path=None, text=None):
            if arc in written:
                return
            written.add(arc)
            zf.writestr(arc, text) if text is not None else zf.write(path, arc)

        for path in ROOT.rglob("*"):
            rel = path.relative_to(ROOT)
            if any(part in JUNK_DIRS for part in rel.parts) or not path.is_file():
                continue
            if path.name == ".env":
                put(str(rel.with_name(".env.example")), text=env_example(path))
                continue
            if path.name.startswith(".env") and path.name != ".env.example":
                continue
            if path.suffix == ".md":
                if path.name not in SKIP_MD:
                    put(str(rel), path)
                continue
            if any(part in SKIP_DIRS for part in rel.parts):
                continue
            if path.suffix in SKIP_SUFFIXES or path.name in SKIP_NAMES:
                continue
            put(str(rel), path)
    return buf.getvalue()


@router.get("/download/source")
async def download_source():
    name = f"source-code-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.zip"
    return Response(build_zip(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})
