from io import BytesIO

from fastapi import HTTPException, UploadFile
from PyPDF2 import PdfReader


async def parse_upload(file: UploadFile) -> str:
    data = await file.read()
    filename = file.filename or "document"
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if suffix == "pdf":
        try:
            reader = PdfReader(BytesIO(data))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not parse PDF: {exc}") from exc

    if suffix in {"txt", "md", "markdown"}:
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("latin-1")

    raise HTTPException(status_code=400, detail="Supported document types: .pdf, .txt, .md")

