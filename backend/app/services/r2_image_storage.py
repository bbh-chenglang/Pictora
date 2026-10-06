"""Private R2 archival with verification, retries and local read fallback."""
import asyncio
import hashlib
import logging
import re
import time
from urllib.parse import urlsplit

from app.config import Settings
from app.repositories.r2_image_repository import R2ImageDestination, R2ImageRepository

logger = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 100 * 1024 * 1024


def destination_from_settings(settings: Settings) -> R2ImageDestination | None:
    if not settings.r2_enabled:
        return None
    endpoint = settings.r2_endpoint.rstrip('/')
    parsed = urlsplit(endpoint)
    if (parsed.scheme != 'https' or not parsed.hostname
            or not parsed.hostname.endswith('.r2.cloudflarestorage.com')
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ('', '/')):
        raise ValueError('R2_ENDPOINT must be a Cloudflare R2 HTTPS S3 endpoint')
    if not settings.r2_bucket or not settings.r2_access_key_id.get_secret_value() or not settings.r2_secret_access_key.get_secret_value():
        raise ValueError('R2 is enabled but server credentials/bucket are incomplete')
    prefix = settings.r2_prefix.strip('/')
    if not prefix or any(p in ('', '.', '..') for p in prefix.split('/')):
        raise ValueError('R2_PREFIX must be a non-empty object prefix')
    return R2ImageDestination(endpoint, settings.r2_bucket, prefix)


def safe_error_code(exc: Exception) -> str:
    response = getattr(exc, 'response', None)
    code = response.get('Error', {}).get('Code') if isinstance(response, dict) else None
    value = code or type(exc).__name__
    return value if re.fullmatch(r'[A-Za-z0-9_]{1,64}', str(value)) else 'StorageError'


class R2ImageStorage:
    def __init__(self, repository: R2ImageRepository, settings: Settings, *, client=None):
        self.repository = repository
        self.settings = settings
        self.destination = destination_from_settings(settings)
        self._client = client
        self._stop = asyncio.Event()
        self._task = None
        self._read_backoff_until = 0.0

    def client(self):
        if self._client is None:
            from botocore.config import Config
            from botocore.session import get_session
            self._client = get_session().create_client(
                's3', endpoint_url=self.destination.endpoint, region_name='auto',
                aws_access_key_id=self.settings.r2_access_key_id.get_secret_value(),
                aws_secret_access_key=self.settings.r2_secret_access_key.get_secret_value(),
                config=Config(signature_version='s3v4', connect_timeout=5, read_timeout=15,
                              retries={'total_max_attempts': 2, 'mode': 'standard'},
                              request_checksum_calculation='when_required',
                              response_checksum_validation='when_required',
                              s3={'addressing_style': 'path'}),
            )
        return self._client

    async def initialize(self) -> None:
        if self.destination is not None:
            await self.repository.initialize()
            # Build locally only; startup does not generate images or upload data.
            self.client()

    def _read_verified(self, job: dict) -> bytes:
        expected = job['size_bytes']
        if expected <= 0 or expected > MAX_IMAGE_BYTES:
            raise ValueError('image size is outside storage limits')
        response = self.client().get_object(Bucket=job['bucket'], Key=job['object_key'])
        body = response['Body']
        try:
            data = body.read(expected + 1)
        finally:
            body.close()
        if len(data) != expected or hashlib.sha256(data).hexdigest() != job['sha256']:
            raise ValueError('R2 readback integrity check failed')
        return data

    def _upload_verified(self, job: dict) -> None:
        data = job['data']
        if (not isinstance(data, bytes) or not 0 < len(data) <= MAX_IMAGE_BYTES
                or len(data) != job['size_bytes']
                or hashlib.sha256(data).hexdigest() != job['sha256']):
            raise ValueError('local image integrity check failed')
        self.client().put_object(
            Bucket=job['bucket'], Key=job['object_key'], Body=data,
            ContentType=job['mime_type'], Metadata={'sha256': job['sha256']},
        )
        self._read_verified(job)

    async def run_once(self) -> bool:
        if self.destination is None:
            return False
        job = await self.repository.claim(self.destination)
        if job is None:
            return False
        try:
            if job['image_id'] is None:
                await asyncio.to_thread(self.client().delete_object,
                                        Bucket=job['bucket'], Key=job['object_key'])
                await self.repository.complete(job, deleted=True)
                logger.info('r2_image_deleted job_id=%s', job['id'])
            else:
                await asyncio.to_thread(self._upload_verified, job)
                await self.repository.complete(job)
                logger.info('r2_image_uploaded image_id=%s bytes=%s', job['image_id'], job['size_bytes'])
        except Exception as exc:
            code = safe_error_code(exc)
            await self.repository.retry(job, code)
            logger.warning('r2_image_upload_retry image_id=%s error_code=%s', job['image_id'], code)
        return True

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if await self.run_once():
                    continue
            except Exception as exc:
                logger.warning('r2_image_worker_retry error_code=%s', safe_error_code(exc))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    def start(self) -> None:
        if self.destination is not None and (self._task is None or self._task.done()):
            self._stop = asyncio.Event()
            self._task = asyncio.create_task(self._run(), name='r2-new-generated-images')
            logger.info('r2_image_storage_enabled prefix=%s', self.destination.prefix)

    async def shutdown(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=20)
            except asyncio.TimeoutError:
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)

    async def read_or_fallback(self, image_id: int, local_data: bytes) -> bytes:
        if self.destination is None or time.monotonic() < self._read_backoff_until:
            return local_data
        try:
            job = await self.repository.ready_for_image(image_id, self.destination)
            if job is None:
                return local_data
            data = await asyncio.to_thread(self._read_verified, job)
            logger.info('r2_image_read image_id=%s bytes=%s', image_id, len(data))
            return data
        except Exception as exc:
            self._read_backoff_until = time.monotonic() + 30
            logger.warning('r2_image_read_local_fallback image_id=%s error_code=%s', image_id, safe_error_code(exc))
            return local_data
