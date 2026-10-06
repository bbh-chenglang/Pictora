import asyncio
import base64
import io
import time
from pathlib import Path

import aiosqlite
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.auth import hash_password
from app.config import Settings
from app.database import initialize_database
from app.dependencies import get_current_user, get_history_repository, get_r2_image_storage
from app.main import app
from app.repositories.history_repository import HistoryRepository
from app.repositories.r2_image_repository import R2ImageRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import StoredSessionUser
from app.services.r2_image_storage import R2ImageStorage, destination_from_settings, safe_error_code

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j3ioAAAAASUVORK5CYII=')


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.puts = []
        self.gets = []
        self.deletes = []
        self.fail_put = False
        self.fail_get = False
        self.corrupt_read = False

    def put_object(self, **args):
        self.puts.append(args)
        if self.fail_put:
            raise ConnectionError('private credentials must never appear in log output')
        self.objects[(args['Bucket'], args['Key'])] = args['Body']
        return {'ETag': 'test'}

    def get_object(self, **args):
        self.gets.append(args)
        if self.fail_get:
            raise TimeoutError('https://example.invalid/signed?secret=private')
        data = self.objects[(args['Bucket'], args['Key'])]
        return {'Body': io.BytesIO(b'bad' if self.corrupt_read else data)}

    def delete_object(self, **args):
        self.deletes.append(args)
        self.objects.pop((args['Bucket'], args['Key']), None)
        return {}


def r2_settings(**extra):
    values = dict(r2_enabled=True, r2_endpoint='https://test.r2.cloudflarestorage.com',
                  r2_bucket='test-private', r2_access_key_id=SecretStr('fixture-key'),
                  r2_secret_access_key=SecretStr('fixture-secret'))
    values.update(extra)
    return Settings(_env_file=None, **values)


async def setup(db: Path):
    await initialize_database(db)
    user_repo = UserRepository(db)
    await user_repo.create('alice', hash_password('secret6'))
    await user_repo.create('bob', hash_password('secret6'))
    repository = R2ImageRepository(db)
    await repository.initialize()
    client = FakeS3()
    storage = R2ImageStorage(repository, r2_settings(), client=client)
    history = HistoryRepository(db, r2_destination=storage.destination)
    history_id = await history.create(user_id=1, kind='generate', prompt='fixture',
                                     provider='compatible', model='fixture', detail='auto', image_count=1)
    return history, history_id, repository, storage, client


async def add(history, history_id, role='generated', data=PNG):
    return await history.add_image(user_id=1, history_id=history_id, role=role,
                                   mime_type='image/png', filename='fixture.png', position=0, data=data)


async def jobs(db):
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        return [dict(row) for row in await (await con.execute('SELECT * FROM r2_image_uploads ORDER BY created_at,id')).fetchall()]


@pytest.mark.asyncio
async def test_only_future_generated_images_are_queued(tmp_path):
    db = tmp_path/'test.db'
    history, hid, repo, storage, s3 = await setup(db)
    old = await add(HistoryRepository(db), hid)
    reference = await add(history, hid, 'reference')
    new = await add(history, hid)
    rows = await jobs(db)
    assert [r['image_id'] for r in rows] == [new]
    assert rows[0]['object_key'].startswith('pictora/generated/')
    assert rows[0]['size_bytes'] == len(PNG)
    assert await storage.run_once()
    assert not await storage.run_once()
    assert len(s3.puts) == 1
    assert (await jobs(db))[0]['status'] == 'ready'
    assert await history.get_image(1, hid, old)
    assert await history.get_image(1, hid, reference)
    assert (await history.get_image(1, hid, new)).data == PNG


@pytest.mark.asyncio
async def test_outbox_insert_is_atomic_with_local_image(tmp_path, monkeypatch):
    import app.repositories.history_repository as module
    db = tmp_path/'test.db'
    history, hid, *_ = await setup(db)
    async def fail(*a, **kw):
        raise RuntimeError('outbox unavailable')
    monkeypatch.setattr(module, 'enqueue_new_image', fail)
    with pytest.raises(RuntimeError):
        await add(history, hid)
    async with aiosqlite.connect(db) as con:
        assert (await (await con.execute('SELECT COUNT(*) FROM history_images')).fetchone())[0] == 0
    assert not await jobs(db)


@pytest.mark.asyncio
async def test_upload_failure_retains_local_and_retries_same_key_after_restart(tmp_path):
    db = tmp_path/'test.db'
    history, hid, repo, storage, s3 = await setup(db)
    image_id = await add(history, hid)
    s3.fail_put = True
    assert await storage.run_once()
    original = (await jobs(db))[0]
    assert original['status'] == 'retry' and original['last_error_code'] == 'ConnectionError'
    assert await storage.read_or_fallback(image_id, PNG) == PNG
    async with aiosqlite.connect(db) as con:
        await con.execute('UPDATE r2_image_uploads SET next_attempt_at=0')
        await con.commit()
    s3.fail_put = False
    restarted = R2ImageStorage(R2ImageRepository(db), r2_settings(), client=s3)
    await restarted.run_once()
    assert (await jobs(db))[0]['status'] == 'ready'
    assert {p['Key'] for p in s3.puts} == {original['object_key']}
    assert (await history.get_image(1, hid, image_id)).data == PNG


@pytest.mark.asyncio
async def test_readback_corruption_does_not_mark_ready(tmp_path):
    db = tmp_path/'test.db'
    history, hid, _, storage, s3 = await setup(db)
    await add(history, hid)
    s3.corrupt_read = True
    await storage.run_once()
    assert (await jobs(db))[0]['status'] == 'retry'


@pytest.mark.asyncio
async def test_ready_object_read_and_local_fallback(tmp_path):
    db = tmp_path/'test.db'
    history, hid, _, storage, s3 = await setup(db)
    image_id = await add(history, hid)
    await storage.run_once()
    assert await storage.read_or_fallback(image_id, b'fallback') == PNG
    s3.fail_get = True
    assert await storage.read_or_fallback(image_id, b'fallback') == b'fallback'
    count = len(s3.gets)
    assert await storage.read_or_fallback(image_id, b'fallback') == b'fallback'
    assert len(s3.gets) == count


@pytest.mark.asyncio
async def test_historical_reads_do_not_access_r2(tmp_path):
    db = tmp_path/'test.db'
    history, hid, _, storage, s3 = await setup(db)
    old = await add(HistoryRepository(db), hid)
    assert await storage.read_or_fallback(old, PNG) == PNG
    assert not s3.gets and not s3.puts


@pytest.mark.asyncio
async def test_two_workers_cannot_claim_the_same_job(tmp_path):
    db = tmp_path/'test.db'
    history, hid, repo, storage, _ = await setup(db)
    await add(history, hid)
    a, b = await asyncio.gather(repo.claim(storage.destination), repo.claim(storage.destination))
    assert sum(x is not None for x in [a,b]) == 1


@pytest.mark.asyncio
async def test_stale_lease_is_recovered_and_old_owner_cannot_complete(tmp_path):
    db = tmp_path/'test.db'
    history, hid, repo, storage, _ = await setup(db)
    await add(history, hid)
    old = await repo.claim(storage.destination, now=time.time())
    assert await repo.claim(storage.destination) is None
    newer = await repo.claim(storage.destination, now=time.time()+301)
    assert newer and newer['lease_id'] != old['lease_id']
    await repo.complete(old)
    assert (await jobs(db))[0]['lease_id'] == newer['lease_id']


@pytest.mark.asyncio
@pytest.mark.parametrize('upload_first', [False, True])
async def test_deleting_new_image_cleans_only_its_r2_object(tmp_path, upload_first):
    db = tmp_path/'test.db'
    history, hid, _, storage, s3 = await setup(db)
    image_id = await add(history, hid)
    if upload_first:
        await storage.run_once()
    assert await history.delete_generated_image(1, hid, image_id)
    assert (await jobs(db))[0]['image_id'] is None
    await storage.run_once()
    assert (await jobs(db))[0]['status'] == 'deleted'
    assert len(s3.deletes) == 1 and not s3.objects
    assert len(s3.puts) == (1 if upload_first else 0)


@pytest.mark.asyncio
async def test_delete_during_upload_queues_cleanup_instead_of_publishing(tmp_path):
    db = tmp_path/'test.db'
    history, hid, repo, storage, s3 = await setup(db)
    image_id = await add(history, hid)
    claimed = await repo.claim(storage.destination)
    await history.delete_generated_image(1, hid, image_id)
    await asyncio.to_thread(storage._upload_verified, claimed)
    await repo.complete(claimed)
    row = (await jobs(db))[0]
    assert row['image_id'] is None and row['status'] == 'retry'
    await storage.run_once()
    assert not s3.objects and (await jobs(db))[0]['status'] == 'deleted'


@pytest.mark.asyncio
async def test_authenticated_route_reads_r2_but_other_user_and_304_do_not(tmp_path):
    db = tmp_path/'test.db'
    history, hid, _, storage, s3 = await setup(db)
    image_id = await add(history, hid)
    await storage.run_once()
    app.dependency_overrides[get_history_repository] = lambda: history
    app.dependency_overrides[get_r2_image_storage] = lambda: storage
    app.dependency_overrides[get_current_user] = lambda: StoredSessionUser(id=2, username='bob', api_key='', model='fixture')
    try:
        client = TestClient(app)
        path = f'/api/history/{hid}/images/{image_id}'
        count = len(s3.gets)
        assert client.get(path).status_code == 404
        assert len(s3.gets) == count
        app.dependency_overrides[get_current_user] = lambda: StoredSessionUser(id=1, username='alice', api_key='', model='fixture')
        response = client.get(path)
        assert response.status_code == 200 and response.content == PNG
        assert len(s3.gets) == count + 1
        assert 'private' in response.headers['cache-control']
        response2 = client.get(path, headers={'If-None-Match': response.headers['etag']})
        assert response2.status_code == 304 and len(s3.gets) == count + 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_worker_start_shutdown_and_disabled_mode(tmp_path):
    db = tmp_path/'test.db'
    history, hid, _, storage, s3 = await setup(db)
    await add(history, hid)
    storage.start()
    for _ in range(100):
        if (await jobs(db))[0]['status'] == 'ready':
            break
        await asyncio.sleep(.01)
    await storage.shutdown()
    assert (await jobs(db))[0]['status'] == 'ready'
    disabled = R2ImageStorage(R2ImageRepository(db), r2_settings(r2_enabled=False), client=s3)
    assert not await disabled.run_once()
    assert await disabled.read_or_fallback(1, b'local') == b'local'


@pytest.mark.parametrize('changes', [
    {'r2_endpoint':'http://test.r2.cloudflarestorage.com'},
    {'r2_endpoint':'https://private.example.com'},
    {'r2_endpoint':'https://test.r2.cloudflarestorage.com/path'},
    {'r2_endpoint':'https://test.r2.cloudflarestorage.com?secret=x'},
    {'r2_prefix':'../private'}, {'r2_prefix':'/'},
    {'r2_access_key_id':SecretStr('')}, {'r2_bucket':''},
])
def test_invalid_storage_configuration_is_rejected(changes):
    with pytest.raises(ValueError):
        destination_from_settings(r2_settings(**changes))


def test_error_codes_and_settings_do_not_disclose_secrets():
    assert 'fixture-secret' not in repr(r2_settings())
    assert 'fixture-key' not in repr(r2_settings())
    assert safe_error_code(ValueError('private signed URL and token')) == 'ValueError'
    error = RuntimeError('secret')
    error.response = {'Error':{'Code':'AccessDenied'}}
    assert safe_error_code(error) == 'AccessDenied'
    error.response = {'Error':{'Code':'https://private/?secret'}}
    assert safe_error_code(error) == 'StorageError'
