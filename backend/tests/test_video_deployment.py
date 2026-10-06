"""Static deployment guards; Docker/Caddy availability is not assumed by unit tests."""
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[2]


class ComposeLoader(yaml.SafeLoader):
    pass


ComposeLoader.add_constructor('!override', lambda loader, node: loader.construct_sequence(node))


def test_https_overlay_keeps_single_backend_and_persistent_certificates():
    base = yaml.load((ROOT / 'compose.yaml').read_text(encoding='utf-8'), Loader=ComposeLoader)
    https = yaml.load((ROOT / 'compose.https.yaml').read_text(encoding='utf-8'), Loader=ComposeLoader)
    assert base['services']['web']['ports'] == ['8083:80']
    assert https['services']['web']['ports'] == ['127.0.0.1:8083:80']
    assert https['services']['backend']['environment']['COOKIE_SECURE'] == 'true'
    assert base['services']['backend']['environment']['VIDEO_MAX_CONCURRENCY'] == '$' + '{VIDEO_MAX_CONCURRENCY:-2}'
    assert base['services']['backend']['environment']['VIDEO_MAX_TASKS_PER_USER'] == '$' + '{VIDEO_MAX_TASKS_PER_USER:-2}'
    assert base['services']['backend']['environment']['VIDEO_MAX_ACTIVE_TASKS'] == '$' + '{VIDEO_MAX_ACTIVE_TASKS:-32}'
    assert all(key not in base['services']['web'].get('environment', {}) for key in ['R2_SECRET_ACCESS_KEY','VIDEO_ASSET_SIGNING_SECRET'])
    assert 'caddy_data' in https['volumes'] and 'caddy_config' in https['volumes']
    assert '443:443' in https['services']['caddy']['ports']
    caddy = (ROOT / 'deploy' / 'Caddyfile').read_text(encoding='utf-8')
    assert 'reverse_proxy web:80' in caddy and '{$PICTORA_DOMAIN}' in caddy


def test_only_video_multipart_route_has_expanded_nginx_body_ceiling():
    nginx = (ROOT / 'frontend' / 'nginx.conf').read_text(encoding='utf-8')
    assert nginx.count('client_max_body_size 25m;') == 1
    assert nginx.count('client_max_body_size 128m;') == 1
    assert re.search(r'location = /api/videos/assets/upload\s*\{[^}]*client_max_body_size 128m;', nginx)
    assert re.search(r'location /api/videos/assets/public/\s*\{[^}]*access_log off;', nginx)
    assert nginx.count('{') == nginx.count('}')


def test_backend_image_installs_ffprobe_without_changing_worker_count():
    dockerfile = (ROOT / 'backend' / 'Dockerfile').read_text(encoding='utf-8')
    assert 'apt-get install -y --no-install-recommends ffmpeg' in dockerfile
    assert '"uvicorn", "app.main:app"' in dockerfile
    assert '--workers' not in dockerfile
    assert 'USER app' in dockerfile


def test_shared_r2_credentials_are_not_shadowed_by_empty_compose_defaults():
    base = yaml.load((ROOT / 'compose.yaml').read_text(encoding='utf-8'), Loader=ComposeLoader)
    backend = base['services']['backend']
    assert backend['env_file'] == [
        {'path': '.env', 'required': False},
        {'path': '.env.r2', 'required': False},
    ]
    assert 'R2_ACCESS_KEY_ID' not in backend['environment']
    assert 'R2_SECRET_ACCESS_KEY' not in backend['environment']
    assert 'R2_ACCOUNT_ID' in backend['environment']
    assert 'R2_BUCKET_NAME' in backend['environment']
