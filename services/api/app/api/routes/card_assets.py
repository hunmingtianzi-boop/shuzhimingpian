from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status

from app.api.card_asset_schemas import (
    CardAssetEnvelope,
    CardAssetRecord,
    CardVideoAssetEnvelope,
    CardVideoAssetRecord,
)
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.core.tokens import StaffPrincipal
from app.services.card_assets import (
    MAX_CARD_ASSET_BYTES,
    MAX_CARD_VIDEO_ASSET_BYTES,
    CardAssetNotFoundError,
    CardAssetStorageError,
    CardAssetStore,
    CardAssetValidationError,
    process_card_asset,
    process_card_video_asset,
)

router = APIRouter(tags=["Card Assets"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]
_ADMIN_ROLES = {"company_admin", "platform_admin"}


def _store(request: Request) -> CardAssetStore:
    store = getattr(request.app.state, "card_asset_store", None)
    if store is None:
        store = CardAssetStore(request.app.state.settings)
        request.app.state.card_asset_store = store
    return store


def _require_card_write(principal: StaffPrincipal) -> None:
    role = str(getattr(principal.role, "value", principal.role))
    if role in _ADMIN_ROLES:
        return
    granted = {str(value) for value in principal.permissions}
    if granted.intersection({"card.write", "*", "admin:*"}):
        return
    raise ApiError(403, "FORBIDDEN", "当前账号没有上传名片素材的权限")


@router.post(
    "/admin/card-assets",
    response_model=CardAssetEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="uploadAdminCardAsset",
)
async def upload_card_asset(
    request: Request,
    principal: StaffDependency,
    file: Annotated[UploadFile, File(...)],
) -> CardAssetEnvelope:
    _require_card_write(principal)
    payload = await file.read(MAX_CARD_ASSET_BYTES + 1)
    try:
        processed = process_card_asset(payload, file.content_type)
        stored = await _store(request).put(
            company_id=principal.company_id,
            asset=processed,
        )
    except CardAssetValidationError as exc:
        messages = {
            "CARD_ASSET_EMPTY": "图片内容为空",
            "CARD_ASSET_TOO_LARGE": "图片不能超过 5 MiB",
            "CARD_ASSET_UNSUPPORTED_TYPE": "仅支持 PNG、JPEG 或 WebP 图片",
            "CARD_ASSET_MIME_MISMATCH": "图片格式与文件类型不一致",
            "CARD_ASSET_ANIMATED": "暂不支持动态图片",
            "CARD_ASSET_DIMENSIONS": "图片尺寸超出安全限制",
            "CARD_ASSET_INVALID_IMAGE": "无法识别图片内容",
        }
        raise ApiError(400, exc.code, messages.get(exc.code, "图片不符合上传要求")) from exc
    except CardAssetStorageError as exc:
        raise ApiError(503, "OBJECT_STORAGE_UNAVAILABLE", "图片存储服务暂不可用") from exc

    url = (
        f"{request.app.state.settings.api_prefix}/public/card-assets/"
        f"{principal.company_id}/{stored.asset_id}.webp"
    )
    return CardAssetEnvelope(
        data=CardAssetRecord(
            url=url,
            content_type=stored.content_type,
            width=stored.width,
            height=stored.height,
            size_bytes=stored.size_bytes,
        )
    )


@router.get(
    "/public/card-assets/{company_id}/{asset_id}.webp",
    operation_id="getPublicCardAsset",
    responses={200: {"content": {"image/webp": {}}}},
)
async def get_card_asset(
    company_id: uuid.UUID,
    asset_id: uuid.UUID,
    request: Request,
) -> Response:
    try:
        asset = await _store(request).get(company_id=company_id, asset_id=asset_id)
    except CardAssetNotFoundError as exc:
        raise ApiError(404, "CARD_ASSET_NOT_FOUND", "名片图片不存在") from exc
    except CardAssetStorageError as exc:
        raise ApiError(503, "OBJECT_STORAGE_UNAVAILABLE", "图片存储服务暂不可用") from exc
    return Response(
        content=asset.payload,
        media_type=asset.content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/admin/card-video-assets",
    response_model=CardVideoAssetEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="uploadAdminCardVideoAsset",
)
async def upload_card_video_asset(
    request: Request,
    principal: StaffDependency,
    file: Annotated[UploadFile, File(...)],
) -> CardVideoAssetEnvelope:
    _require_card_write(principal)
    payload = await file.read(MAX_CARD_VIDEO_ASSET_BYTES + 1)
    try:
        processed = process_card_video_asset(payload, file.content_type, file.filename)
        stored = await _store(request).put_video(
            company_id=principal.company_id,
            asset=processed,
        )
    except CardAssetValidationError as exc:
        messages = {
            "CARD_VIDEO_ASSET_EMPTY": "视频内容为空",
            "CARD_VIDEO_ASSET_TOO_LARGE": "视频不能超过 50 MiB",
            "CARD_VIDEO_ASSET_UNSUPPORTED_TYPE": "仅支持 MP4 或 WebM 视频",
            "CARD_VIDEO_ASSET_MIME_MISMATCH": "视频扩展名、文件类型或文件签名不一致",
        }
        raise ApiError(400, exc.code, messages.get(exc.code, "视频不符合上传要求")) from exc
    except CardAssetStorageError as exc:
        raise ApiError(503, "OBJECT_STORAGE_UNAVAILABLE", "视频存储服务暂不可用") from exc
    url = (
        f"{request.app.state.settings.api_prefix}/public/card-video-assets/"
        f"{principal.company_id}/{stored.asset_id}.{stored.extension}"
    )
    return CardVideoAssetEnvelope(
        data=CardVideoAssetRecord(
            url=url,
            content_type=stored.content_type,
            size_bytes=stored.size_bytes,
        )
    )


def _range_slice(range_header: str | None, length: int) -> tuple[int, int] | None:
    if not range_header:
        return None
    if not range_header.startswith("bytes=") or "," in range_header:
        raise ApiError(416, "CARD_VIDEO_RANGE_INVALID", "视频分段范围无效")
    raw_start, separator, raw_end = range_header[6:].partition("-")
    if not separator:
        raise ApiError(416, "CARD_VIDEO_RANGE_INVALID", "视频分段范围无效")
    try:
        if raw_start:
            start = int(raw_start)
            end = int(raw_end) if raw_end else length - 1
        else:
            suffix = int(raw_end)
            if suffix <= 0:
                raise ValueError
            start = max(0, length - suffix)
            end = length - 1
    except ValueError as exc:
        raise ApiError(416, "CARD_VIDEO_RANGE_INVALID", "视频分段范围无效") from exc
    if start < 0 or start >= length or end < start:
        raise ApiError(416, "CARD_VIDEO_RANGE_INVALID", "视频分段范围无效")
    return start, min(end, length - 1)


@router.get(
    "/public/card-video-assets/{company_id}/{asset_id}.{extension}",
    operation_id="getPublicCardVideoAsset",
)
async def get_card_video_asset(
    company_id: uuid.UUID,
    asset_id: uuid.UUID,
    extension: str,
    request: Request,
) -> Response:
    try:
        asset = await _store(request).get_video(
            company_id=company_id,
            asset_id=asset_id,
            extension=extension.casefold(),
        )
    except CardAssetNotFoundError as exc:
        raise ApiError(404, "CARD_VIDEO_ASSET_NOT_FOUND", "名片视频不存在") from exc
    except CardAssetStorageError as exc:
        raise ApiError(503, "OBJECT_STORAGE_UNAVAILABLE", "视频存储服务暂不可用") from exc
    selected = _range_slice(request.headers.get("Range"), len(asset.payload))
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
    }
    if selected is None:
        return Response(content=asset.payload, media_type=asset.content_type, headers=headers)
    start, end = selected
    headers["Content-Range"] = f"bytes {start}-{end}/{len(asset.payload)}"
    return Response(
        content=asset.payload[start : end + 1],
        media_type=asset.content_type,
        headers=headers,
        status_code=status.HTTP_206_PARTIAL_CONTENT,
    )


__all__ = ["router"]
