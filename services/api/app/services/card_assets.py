from __future__ import annotations

import asyncio
import io
import threading
import uuid
import warnings
from dataclasses import dataclass
from urllib.parse import urlsplit

from minio import Minio
from minio.error import S3Error
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings

MAX_CARD_ASSET_BYTES = 5 * 1024 * 1024
MAX_CARD_VIDEO_ASSET_BYTES = 50 * 1024 * 1024
MAX_CARD_ASSET_PIXELS = 20_000_000
MAX_CARD_ASSET_EDGE = 8_192
OUTPUT_CARD_ASSET_EDGE = 1_600
ALLOWED_CARD_ASSET_MIMES = frozenset({"image/jpeg", "image/png", "image/webp"})
_FORMAT_MIMES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
_NOT_FOUND_CODES = frozenset({"NoSuchBucket", "NoSuchKey", "NoSuchObject"})
ALLOWED_CARD_VIDEO_MIMES = frozenset({"video/mp4", "video/webm"})
_VIDEO_EXTENSIONS = {"video/mp4": "mp4", "video/webm": "webm"}


class CardAssetValidationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CardAssetNotFoundError(LookupError):
    pass


class CardAssetStorageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProcessedCardAsset:
    payload: bytes
    width: int
    height: int
    content_type: str = "image/webp"


@dataclass(frozen=True, slots=True)
class StoredCardAsset:
    asset_id: uuid.UUID
    width: int
    height: int
    size_bytes: int
    content_type: str


@dataclass(frozen=True, slots=True)
class CardAssetContent:
    payload: bytes
    content_type: str


@dataclass(frozen=True, slots=True)
class ProcessedCardVideoAsset:
    payload: bytes
    content_type: str
    extension: str


@dataclass(frozen=True, slots=True)
class StoredCardVideoAsset:
    asset_id: uuid.UUID
    size_bytes: int
    content_type: str
    extension: str


def process_card_asset(payload: bytes, declared_content_type: str | None) -> ProcessedCardAsset:
    if not payload:
        raise CardAssetValidationError("CARD_ASSET_EMPTY")
    if len(payload) > MAX_CARD_ASSET_BYTES:
        raise CardAssetValidationError("CARD_ASSET_TOO_LARGE")
    normalized_mime = (declared_content_type or "").split(";", 1)[0].strip().casefold()
    if normalized_mime not in ALLOWED_CARD_ASSET_MIMES:
        raise CardAssetValidationError("CARD_ASSET_UNSUPPORTED_TYPE")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as source:
                detected_mime = _FORMAT_MIMES.get(source.format or "")
                if detected_mime != normalized_mime:
                    raise CardAssetValidationError("CARD_ASSET_MIME_MISMATCH")
                if getattr(source, "n_frames", 1) != 1:
                    raise CardAssetValidationError("CARD_ASSET_ANIMATED")
                width, height = source.size
                if (
                    width < 1
                    or height < 1
                    or width > MAX_CARD_ASSET_EDGE
                    or height > MAX_CARD_ASSET_EDGE
                    or width * height > MAX_CARD_ASSET_PIXELS
                ):
                    raise CardAssetValidationError("CARD_ASSET_DIMENSIONS")
                image = ImageOps.exif_transpose(source).copy()
    except CardAssetValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise CardAssetValidationError("CARD_ASSET_DIMENSIONS") from None
    except (OSError, UnidentifiedImageError, ValueError):
        raise CardAssetValidationError("CARD_ASSET_INVALID_IMAGE") from None

    image.thumbnail((OUTPUT_CARD_ASSET_EDGE, OUTPUT_CARD_ASSET_EDGE), Image.Resampling.LANCZOS)
    has_alpha = image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )
    normalized = image.convert("RGBA" if has_alpha else "RGB")
    output = io.BytesIO()
    normalized.save(
        output,
        format="WEBP",
        lossless=has_alpha,
        quality=88,
        method=4,
    )
    encoded = output.getvalue()
    if not encoded or len(encoded) > MAX_CARD_ASSET_BYTES:
        raise CardAssetValidationError("CARD_ASSET_TOO_LARGE")
    return ProcessedCardAsset(
        payload=encoded,
        width=normalized.width,
        height=normalized.height,
    )


def process_card_video_asset(
    payload: bytes,
    declared_content_type: str | None,
    file_name: str | None,
) -> ProcessedCardVideoAsset:
    if not payload:
        raise CardAssetValidationError("CARD_VIDEO_ASSET_EMPTY")
    if len(payload) > MAX_CARD_VIDEO_ASSET_BYTES:
        raise CardAssetValidationError("CARD_VIDEO_ASSET_TOO_LARGE")
    mime = (declared_content_type or "").split(";", 1)[0].strip().casefold()
    if mime not in ALLOWED_CARD_VIDEO_MIMES:
        raise CardAssetValidationError("CARD_VIDEO_ASSET_UNSUPPORTED_TYPE")
    extension = _VIDEO_EXTENSIONS[mime]
    supplied_extension = (file_name or "").rsplit(".", 1)[-1].casefold()
    if supplied_extension != extension:
        raise CardAssetValidationError("CARD_VIDEO_ASSET_MIME_MISMATCH")
    is_mp4 = len(payload) >= 12 and payload[4:8] == b"ftyp"
    is_webm = payload.startswith(b"\x1aE\xdf\xa3")
    if (mime == "video/mp4" and not is_mp4) or (mime == "video/webm" and not is_webm):
        raise CardAssetValidationError("CARD_VIDEO_ASSET_MIME_MISMATCH")
    return ProcessedCardVideoAsset(
        payload=payload,
        content_type=mime,
        extension=extension,
    )


class CardAssetStore:
    def __init__(self, settings: Settings) -> None:
        parsed = urlsplit(settings.object_storage_endpoint.strip())
        if parsed.scheme:
            if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
                raise ValueError("OBJECT_STORAGE_ENDPOINT must be an HTTP(S) origin")
            if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                raise ValueError("OBJECT_STORAGE_ENDPOINT must not contain a path or query")
            endpoint = parsed.netloc
            secure = parsed.scheme.casefold() == "https"
        else:
            endpoint = settings.object_storage_endpoint.strip().rstrip("/")
            secure = settings.object_storage_secure
        self._bucket = settings.object_storage_bucket
        self._client = Minio(
            endpoint,
            access_key=settings.object_storage_access_key,
            secret_key=settings.object_storage_secret_key.get_secret_value(),
            secure=secure,
            region=settings.object_storage_region,
        )
        self._bucket_ready = False
        self._bucket_lock = threading.Lock()

    async def put(
        self,
        *,
        company_id: uuid.UUID,
        asset: ProcessedCardAsset,
    ) -> StoredCardAsset:
        asset_id = uuid.uuid4()
        await asyncio.to_thread(self._put, company_id, asset_id, asset)
        return StoredCardAsset(
            asset_id=asset_id,
            width=asset.width,
            height=asset.height,
            size_bytes=len(asset.payload),
            content_type=asset.content_type,
        )

    async def get(self, *, company_id: uuid.UUID, asset_id: uuid.UUID) -> CardAssetContent:
        return await asyncio.to_thread(self._get, company_id, asset_id)

    async def put_video(
        self,
        *,
        company_id: uuid.UUID,
        asset: ProcessedCardVideoAsset,
    ) -> StoredCardVideoAsset:
        asset_id = uuid.uuid4()
        await asyncio.to_thread(self._put_video, company_id, asset_id, asset)
        return StoredCardVideoAsset(
            asset_id=asset_id,
            size_bytes=len(asset.payload),
            content_type=asset.content_type,
            extension=asset.extension,
        )

    async def get_video(
        self,
        *,
        company_id: uuid.UUID,
        asset_id: uuid.UUID,
        extension: str,
    ) -> CardAssetContent:
        return await asyncio.to_thread(self._get_video, company_id, asset_id, extension)

    def _object_name(self, company_id: uuid.UUID, asset_id: uuid.UUID) -> str:
        return f"card-assets/{company_id}/{asset_id}.webp"

    @staticmethod
    def _video_object_name(
        company_id: uuid.UUID, asset_id: uuid.UUID, extension: str
    ) -> str:
        return f"card-video-assets/{company_id}/{asset_id}.{extension}"

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        with self._bucket_lock:
            if self._bucket_ready:
                return
            try:
                if not self._client.bucket_exists(self._bucket):
                    self._client.make_bucket(self._bucket)
            except S3Error as exc:
                if exc.code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                    raise CardAssetStorageError("object storage is unavailable") from exc
            except Exception as exc:
                raise CardAssetStorageError("object storage is unavailable") from exc
            self._bucket_ready = True

    def _put(
        self,
        company_id: uuid.UUID,
        asset_id: uuid.UUID,
        asset: ProcessedCardAsset,
    ) -> None:
        self._ensure_bucket()
        try:
            self._client.put_object(
                self._bucket,
                self._object_name(company_id, asset_id),
                io.BytesIO(asset.payload),
                len(asset.payload),
                content_type=asset.content_type,
                metadata={"company-id": str(company_id)},
            )
        except Exception as exc:
            raise CardAssetStorageError("object storage is unavailable") from exc

    def _put_video(
        self,
        company_id: uuid.UUID,
        asset_id: uuid.UUID,
        asset: ProcessedCardVideoAsset,
    ) -> None:
        self._ensure_bucket()
        try:
            self._client.put_object(
                self._bucket,
                self._video_object_name(company_id, asset_id, asset.extension),
                io.BytesIO(asset.payload),
                len(asset.payload),
                content_type=asset.content_type,
                metadata={"company-id": str(company_id)},
            )
        except Exception as exc:
            raise CardAssetStorageError("object storage is unavailable") from exc

    def _get(self, company_id: uuid.UUID, asset_id: uuid.UUID) -> CardAssetContent:
        response = None
        try:
            response = self._client.get_object(
                self._bucket,
                self._object_name(company_id, asset_id),
            )
            payload = response.read(MAX_CARD_ASSET_BYTES + 1)
            if not payload or len(payload) > MAX_CARD_ASSET_BYTES:
                raise CardAssetStorageError("stored card asset is invalid")
            return CardAssetContent(payload=payload, content_type="image/webp")
        except S3Error as exc:
            if exc.code in _NOT_FOUND_CODES:
                raise CardAssetNotFoundError from exc
            raise CardAssetStorageError("object storage is unavailable") from exc
        except CardAssetStorageError:
            raise
        except Exception as exc:
            raise CardAssetStorageError("object storage is unavailable") from exc
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def _get_video(
        self,
        company_id: uuid.UUID,
        asset_id: uuid.UUID,
        extension: str,
    ) -> CardAssetContent:
        if extension not in {"mp4", "webm"}:
            raise CardAssetNotFoundError
        response = None
        try:
            response = self._client.get_object(
                self._bucket,
                self._video_object_name(company_id, asset_id, extension),
            )
            payload = response.read(MAX_CARD_VIDEO_ASSET_BYTES + 1)
            if not payload or len(payload) > MAX_CARD_VIDEO_ASSET_BYTES:
                raise CardAssetStorageError("stored card video asset is invalid")
            return CardAssetContent(
                payload=payload,
                content_type="video/mp4" if extension == "mp4" else "video/webm",
            )
        except S3Error as exc:
            if exc.code in _NOT_FOUND_CODES:
                raise CardAssetNotFoundError from exc
            raise CardAssetStorageError("object storage is unavailable") from exc
        except CardAssetStorageError:
            raise
        except Exception as exc:
            raise CardAssetStorageError("object storage is unavailable") from exc
        finally:
            if response is not None:
                response.close()
                response.release_conn()


__all__ = [
    "ALLOWED_CARD_ASSET_MIMES",
    "ALLOWED_CARD_VIDEO_MIMES",
    "CardAssetContent",
    "CardAssetNotFoundError",
    "CardAssetStorageError",
    "CardAssetStore",
    "CardAssetValidationError",
    "MAX_CARD_ASSET_BYTES",
    "MAX_CARD_VIDEO_ASSET_BYTES",
    "ProcessedCardAsset",
    "ProcessedCardVideoAsset",
    "StoredCardAsset",
    "StoredCardVideoAsset",
    "process_card_asset",
    "process_card_video_asset",
]
