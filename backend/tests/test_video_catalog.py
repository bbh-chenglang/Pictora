"""Catalog synchronization uses public mocked GETs, never generation requests."""
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest

from app.video.capabilities import VideoCatalog, bundled_models
from app.video.repository import VideoError


def pricing_row(name='new-video-model'):
    return {
        'model_name': name,
        'supported_endpoint_types': ['openai-video'],
        'video_pricing': {
            'default_duration': 10, 'default_resolution': '4k',
            'default_ratio': '1:1', 'ratios': ['1:1', '16:9'],
            'tiers': [{'duration': 10, 'resolution': '4k'},
                      {'duration': 15, 'resolution': '4k'}],
        },
    }


def test_snapshot_matches_october_8_public_catalog():
    models = {model['id']: model for model in bundled_models()}
    assert set(models) == {
        'sd-2.0-J2', 'sd-2.0-fast-803-J3', 'sd-2.5-J2', 'grok-1.5',
        'minimax-h3', 'sd-2.0-933-720-fast-原生真人', 'sd-2.0-J1',
    }
    fast = models['sd-2.0-fast-803-J3']
    assert fast['default_duration'] == 12 and fast['default_resolution'] == '720p'
    assert fast['durations_by_resolution'] == {
        resolution: list(range(4, 13)) for resolution in ('720p', '1080p', '2k')
    }
    assert fast['reference_limits'] == {'image': 8, 'video': None, 'audio': 3}


@pytest.mark.asyncio
async def test_new_models_and_resolutions_sync_without_a_name_allowlist():
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={'success': True, 'data': [
            None, {'model_name': 'image-only'}, pricing_row(), pricing_row(),
            {**pricing_row('different-protocol'), 'supported_endpoint_types': ['other-video']},
        ]})
    catalog = VideoCatalog('https://sub.beibeihai.xyz', httpx.MockTransport(respond))
    models = await catalog.get()
    assert [model['id'] for model in models] == ['new-video-model']
    assert models[0]['reference_limits'] == {'image': None, 'video': None, 'audio': None}
    assert models[0]['durations_by_resolution'] == {'4k': [10, 15]}
    assert len(requests) == 1 and requests[0].method == 'GET'
    assert str(requests[0].url) == 'https://sub.beibeihai.xyz/api/pricing'
    assert 'authorization' not in requests[0].headers
    request = SimpleNamespace(model='new-video-model', prompt='scene', duration=None, resolution=None, ratio=None)
    assert await catalog.normalize(request, []) == {
        'model': 'new-video-model', 'prompt': 'scene', 'duration': 10, 'resolution': '4k', 'ratio': '1:1',
    }
    with pytest.raises(VideoError) as error:
        await catalog.normalize(request, [{'type': 'image', 'name': 'reference', 'url': 'https://cdn.example/image.png'}])
    assert error.value.code == 'video_material_unsupported'


@pytest.mark.asyncio
async def test_manual_sync_bypasses_cache_and_preserves_last_success_on_failure():
    calls = []
    def respond(request):
        calls.append(request)
        if len(calls) == 2:
            return httpx.Response(503)
        return httpx.Response(200, json={'success': True, 'data': [pricing_row('latest-video-model')]})
    catalog = VideoCatalog('https://sub.beibeihai.xyz', httpx.MockTransport(respond))
    first = deepcopy(await catalog.get())
    assert await catalog.get() == first and len(calls) == 1
    assert await catalog.get(force=True) == first and len(calls) == 2
    assert catalog.source == 'cached_live_catalog'
    assert await catalog.get() == first and len(calls) == 2
    await catalog.get(force=True)
    assert len(calls) == 3 and catalog.source == 'live_catalog'
    assert not any(model['id'] == 'sd-2.0-J2' for model in catalog.models)


@pytest.mark.parametrize('field,value', [
    ('default_duration', True), ('default_duration', '10'), ('default_duration', 11),
    ('default_resolution', None), ('default_resolution', ['4k']),
    ('default_ratio', '9:16'), ('ratios', '1:1'), ('ratios', []), ('ratios', [None]),
    ('tiers', None), ('tiers', [None, {'duration': True, 'resolution': '4k'}]),
])
@pytest.mark.asyncio
async def test_invalid_pricing_preserves_offline_snapshot(field, value):
    row = pricing_row()
    row['video_pricing'][field] = value
    catalog = VideoCatalog('https://sub.beibeihai.xyz', httpx.MockTransport(
        lambda request: httpx.Response(200, json={'data': [row]})))
    assert await catalog.get() == bundled_models()
    assert catalog.source == 'bundled_snapshot_2026-10-08'
