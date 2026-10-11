"""Explicit, resumable migration: python -m app.migrate_generated_images."""
import argparse
import asyncio
import json
import time

import aiosqlite

from app.config import Settings
from app.database import DATABASE_PATH
from app.repositories.r2_image_repository import R2ImageRepository
from app.services.r2_image_storage import R2ImageStorage


async def summary(path):
    async with aiosqlite.connect(path, timeout=15) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            """SELECT role, COUNT(*) AS images FROM history_images GROUP BY role"""
        )).fetchall()
        result = {row['role']: row['images'] for row in rows}
        row = await (await db.execute(
            """SELECT COUNT(*) AS local_originals, COALESCE(SUM(length(data)), 0) AS local_bytes
               FROM history_images WHERE role = 'generated' AND length(data) > 0"""
        )).fetchone()
        result.update(dict(row))
        rows = await (await db.execute(
            "SELECT status, COUNT(*) AS jobs FROM r2_image_uploads GROUP BY status"
        )).fetchall()
        result['jobs'] = {row['status']: row['jobs'] for row in rows}
        return result


async def migrate(max_wait):
    repository = R2ImageRepository(DATABASE_PATH)
    storage = R2ImageStorage(repository, Settings())
    if storage.destination is None:
        raise ValueError('R2 must be enabled before migrating generated images')
    await storage.initialize()
    print('before', json.dumps(await summary(DATABASE_PATH)), flush=True)
    cursor = 0
    queued = 0
    while True:
        async with aiosqlite.connect(DATABASE_PATH, timeout=15) as db:
            rows = await (await db.execute(
                """SELECT id FROM history_images WHERE role = 'generated'
                   AND id > ? AND length(data) > 0 ORDER BY id LIMIT 64""", (cursor,),
            )).fetchall()
        if not rows:
            break
        for (image_id,) in rows:
            queued += int(await repository.enqueue_existing_image(storage.destination, image_id))
            cursor = image_id
        print('queued', queued, 'through_image_id', cursor, flush=True)
    deadline = time.monotonic() + max_wait
    last_report = 0.0
    while True:
        now = time.monotonic()
        if now - last_report >= 10:
            state = await summary(DATABASE_PATH)
            print('progress', json.dumps(state), flush=True)
            last_report = now
            if state['local_originals'] == 0:
                async with aiosqlite.connect(DATABASE_PATH, timeout=15) as db:
                    invalid = (await (await db.execute(
                        """SELECT COUNT(*) FROM history_images i
                           LEFT JOIN r2_image_uploads r ON r.image_id = i.id
                           WHERE i.role = 'generated' AND
                             (r.id IS NULL OR r.status != 'ready' OR r.endpoint != ? OR r.bucket != ?)""",
                        (storage.destination.endpoint, storage.destination.bucket),
                    )).fetchone())[0]
                if invalid:
                    raise ValueError('Remote-only images have incomplete storage records')
                print('migration_complete', flush=True)
                return 0
        if now >= deadline:
            print('migration_wait_timeout; queued jobs remain durable and resumable', flush=True)
            return 2
        if not await storage.run_once():
            last_report = 0.0
            await asyncio.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-wait', type=int, default=3600)
    args = parser.parse_args()
    if args.max_wait <= 0:
        parser.error('--max-wait must be positive')
    raise SystemExit(asyncio.run(migrate(args.max_wait)))


if __name__ == '__main__':
    main()
