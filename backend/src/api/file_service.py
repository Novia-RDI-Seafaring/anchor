import hashlib
import ipaddress
import json
import os
import socket
from typing import Any, cast
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, UploadFile
from pydantic import BaseModel

INDEX_FILE_NAME = "files_index.json"
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024  # 25MB


class UploadedFileInfo(BaseModel):
    file_id: str
    file_path: str
    original_filename: str
    source: str
    file_size: int
    source_url: str | None = None


class FileWriteResult(BaseModel):
    file_id: str
    file_path: str
    exists: bool


FileIndex = dict[str, UploadedFileInfo]


class FileService:
    def __init__(self, uploads_folder: Path):
        self.uploads_folder = uploads_folder
        self.uploads_folder.mkdir(parents=True, exist_ok=True)
        self.index_path = self.uploads_folder / INDEX_FILE_NAME

    def _load_index(self) -> FileIndex:
        if not self.index_path.exists():
            return {}
        try:
            raw_data: Any = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

        if not isinstance(raw_data, dict):
            return {}

        index: FileIndex = {}
        raw_dict = cast(dict[str, object], raw_data)
        for file_id, payload in raw_dict.items():
            if not isinstance(payload, dict):
                continue
            try:
                index[file_id] = UploadedFileInfo.model_validate(payload)
            except Exception:
                continue
        return index

    def _save_index(self, index: FileIndex) -> None:
        serialized = {file_id: entry.model_dump() for file_id, entry in index.items()}
        self.index_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")

    def _make_file_id(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _existing_record(self, file_id: str, index: FileIndex | None = None) -> UploadedFileInfo | None:
        idx = index or self._load_index()
        entry = idx.get(file_id)
        if not entry:
            return None
        file_path = Path(entry.file_path)
        return entry if file_path.exists() else None

    def _assert_public_http_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise HTTPException(status_code=400, detail="Only http/https URLs are allowed")
        if not parsed.hostname:
            raise HTTPException(status_code=400, detail="URL host is missing")
        if parsed.hostname.lower() == "localhost":
            raise HTTPException(status_code=400, detail="Localhost URLs are not allowed")

        try:
            addrinfos = socket.getaddrinfo(parsed.hostname, None)
        except socket.gaierror:
            raise HTTPException(status_code=400, detail="Could not resolve URL host")

        for info in addrinfos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise HTTPException(
                    status_code=400,
                    detail="URL resolves to a non-public network address",
                )

    def _ensure_pdf(self, content: bytes, content_type: str) -> None:
        is_pdf_mime = "application/pdf" in content_type.lower()
        has_pdf_signature = content.startswith(b"%PDF-")
        if not is_pdf_mime and not has_pdf_signature:
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    def _write_and_track(
        self,
        *,
        content: bytes,
        original_filename: str,
        source: str,
        extension: str,
        source_url: str | None = None,
    ) -> FileWriteResult:
        file_id = self._make_file_id(content)
        index = self._load_index()
        existing = self._existing_record(file_id, index)
        if existing:
            return FileWriteResult(file_id=file_id, file_path=existing.file_path, exists=True)

        normalized_extension = extension if extension.startswith(".") else f".{extension}"
        file_path = self.uploads_folder / f"{original_filename}"
        file_path.write_bytes(content)

        index[file_id] = UploadedFileInfo(
            file_id=file_id,
            file_path=str(file_path),
            original_filename=Path(original_filename).name,
            source=source,
            file_size=len(content),
            source_url=source_url,
        )
        self._save_index(index)
        return FileWriteResult(file_id=file_id, file_path=str(file_path), exists=False)

    async def upload_file(self, file: UploadFile) -> FileWriteResult:
        content = await file.read()
        filename = file.filename
        if not filename:
            raise HTTPException(status_code=400, detail="Uploaded file must have a filename")

        extension = Path(filename).suffix or ".bin"
        return self._write_and_track(
            content=content,
            original_filename=filename,
            source="upload",
            extension=extension,
        )

    def download_file(self, url: str) -> FileWriteResult:
        for entry in self._load_index().values():
            if entry.source_url == url and Path(entry.file_path).exists():
                return FileWriteResult(file_id=entry.file_id, file_path=entry.file_path, exists=True)

        self._assert_public_http_url(url)

        with httpx.Client(follow_redirects=True, timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()

        content = response.content
        if len(content) > MAX_DOWNLOAD_BYTES:
            raise HTTPException(status_code=400, detail="PDF too large")

        self._ensure_pdf(content, response.headers.get("content-type", ""))
        source_name = Path(urlparse(url).path).name or "downloaded.pdf"
        return self._write_and_track(
            content=content,
            original_filename=source_name,
            source="download",
            extension=".pdf",
            source_url=url,
        )

    def list_tracked_files(self) -> list[UploadedFileInfo]:
        return list(self._load_index().values())

    def exists(self, file_id: str) -> bool:
        return self._existing_record(file_id) is not None

    def get_file_by_id(self, file_id: str) -> UploadedFileInfo:
        entry = self._load_index().get(file_id)
        if not entry:
            raise HTTPException(status_code=404, detail="File ID not found")
        return entry

    def delete_file(self, file_id: str) -> dict[str, str | bool]:
        index = self._load_index()
        entry = index.get(file_id)
        if not entry:
            raise HTTPException(status_code=404, detail="File ID not found")

        file_path = Path(entry.file_path)
        deleted = False
        if file_path.exists():
            file_path.unlink()
            deleted = True

        del index[file_id]
        self._save_index(index)
        return {"file_id": file_id, "deleted": deleted}


_file_service: FileService | None = None


def get_file_service() -> FileService:
    global _file_service
    if _file_service is None:
        uploads_dir = Path(os.getenv("UPLOADS_DIR", "data/uploads"))
        _file_service = FileService(uploads_folder=uploads_dir)
    return _file_service
