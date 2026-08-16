from fastapi import HTTPException, UploadFile


MAX_REFERENCE_FILE_BYTES = 10 * 1024 * 1024
MAX_REFERENCE_TOTAL_BYTES = 25 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 64 * 1024


def _upload_too_large(message: str) -> HTTPException:
    return HTTPException(
        413,
        {"error": {"code": "image_too_large", "message": message}},
    )


async def read_reference_upload(upload: UploadFile, *, total_bytes: int) -> bytes:
    if upload.size is not None:
        if upload.size > MAX_REFERENCE_FILE_BYTES:
            raise _upload_too_large("Each image must be 10 MB or smaller")
        if total_bytes + upload.size > MAX_REFERENCE_TOTAL_BYTES:
            raise _upload_too_large("Reference images must total 25 MB or less")

    data = bytearray()
    while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
        data.extend(chunk)
        if len(data) > MAX_REFERENCE_FILE_BYTES:
            raise _upload_too_large("Each image must be 10 MB or smaller")
        if total_bytes + len(data) > MAX_REFERENCE_TOTAL_BYTES:
            raise _upload_too_large("Reference images must total 25 MB or less")
    return bytes(data)
