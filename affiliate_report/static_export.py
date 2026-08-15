from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


APP_VERSION_TOKEN = "__APP_VERSION__"
RSC_FLAT_NAME = re.compile(
    r"^(?P<prefix>__next\.[A-Za-z0-9_-]+)\.(?P<segments>[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)\.txt$"
)


def _nested_rsc_path(path: str) -> str | None:
    """Map Next static-export's flattened RSC URL to the emitted file path."""

    # Starlette normalizes mounted paths with the platform separator before
    # get_response(), so convert Windows backslashes back to URL separators.
    requested = PurePosixPath(path.replace("\\", "/").lstrip("/"))
    match = RSC_FLAT_NAME.fullmatch(requested.name)
    if match is None:
        return None

    segments = match.group("segments").split(".")
    nested = requested.parent / match.group("prefix")
    for segment in segments[:-1]:
        nested /= segment
    return str(nested / f"{segments[-1]}.txt")


class StaticExportFiles(StaticFiles):
    """Serve a Next.js static export, including flattened client-navigation payload URLs."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        # Không có Cache-Control thì trình duyệt/WebView tự áp heuristic freshness cho HTML/RSC
        # payload và có thể phục vụ bản cũ sau khi cập nhật xong mà không hỏi lại server — kể cả
        # khi service worker (network-first, đúng) chạy, vì fetch() bên trong nó vẫn có thể bị
        # cache HTTP chặn trước khi ra tới mạng thật. no-cache (khác no-store) vẫn cho trình
        # duyệt giữ bản đã tải để so sánh ETag/Last-Modified, chỉ bắt buộc hỏi lại server trước
        # khi dùng — không tốn băng thông tải lại toàn bộ mỗi lần như no-store.
        response = await self._resolve_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response

    async def _resolve_response(self, path: str, scope: Scope) -> Response:
        missing_error: HTTPException | None = None
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            missing_error = exc
            response = None

        if response is not None and response.status_code != 404:
            return response

        candidate = _nested_rsc_path(path)
        if candidate is None:
            if response is not None:
                return response
            raise missing_error or HTTPException(status_code=404)

        try:
            return await super().get_response(candidate, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            if response is not None:
                return response
            raise missing_error or exc


def service_worker_response(static_dir: str | Path, app_version: str) -> Response:
    source = (Path(static_dir) / "sw.js").read_text(encoding="utf-8")
    if APP_VERSION_TOKEN not in source:
        raise RuntimeError("Service worker is missing the app-version token.")
    rendered = source.replace(APP_VERSION_TOKEN, app_version)
    return Response(
        rendered,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
