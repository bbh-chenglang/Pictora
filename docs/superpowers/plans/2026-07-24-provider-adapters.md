# Provider Adapter And Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tested provider adapters, normalized image/text results, and a secret-safe provider registry for the existing backend schemas.

**Architecture:** `ImageProvider` defines the async boundary. OpenAI-compatible adapters own SDK calls and exception translation, while `CustomProvider` fails explicitly until a real custom protocol exists. `ProviderRegistry` is constructed from `Settings`, exposes only configured providers and public model metadata, and FastAPI dependencies provide a shared settings/registry boundary.

**Tech Stack:** Python 3, Pydantic v2, OpenAI SDK 2.x, pytest, pytest-asyncio.

---

### Task 1: Define failing provider contract and registry tests

**Files:**
- Create: `backend/tests/test_provider_registry.py`
- Create: `backend/tests/test_image_service.py`

- [x] Write tests for `ImageResult` normalization, registry filtering, public model metadata, SecretStr construction, custom-provider explicit failure, and SDK exception translation using mocked clients.
- [x] Run `cd backend; python -m pytest tests/test_provider_registry.py tests/test_image_service.py -q` and confirm the new imports/behaviors fail because the provider modules do not exist.

### Task 2: Implement provider contracts and normalized adapters

**Files:**
- Create: `backend/app/providers/__init__.py`
- Create: `backend/app/providers/base.py`
- Create: `backend/app/providers/openai_provider.py`
- Create: `backend/app/providers/compatible_provider.py`
- Create: `backend/app/providers/custom_provider.py`

- [x] Define the protocol, response normalization helpers, and stable provider error classes without including secrets or raw SDK payloads in messages.
- [x] Implement OpenAI and compatible SDK-backed generation and analysis with injectable clients, data URLs for image bytes, and auth/timeout/request error mapping.
- [x] Implement `CustomProvider` with `provider_not_implemented` errors for both operations.
- [x] Run the focused tests and keep the implementation minimal until green.

### Task 3: Implement registry and dependency accessors

**Files:**
- Create: `backend/app/providers/registry.py`
- Create: `backend/app/dependencies.py`

- [x] Implement `from_settings`, `resolve`, and `list_models`; only non-empty configured keys create usable configured adapters and returned metadata contains no secrets.
- [x] Add cached settings and registry dependency functions without adding routes or queue behavior.
- [x] Run the focused tests again.

### Task 4: Verify and commit

**Files:**
- No changes to `docs/images-vision.md`.

- [ ] Run `cd backend; python -m pytest tests/test_provider_registry.py tests/test_image_service.py -q`.
- [ ] Run `git diff --check` and inspect `git diff --stat` plus status to verify scope.
- [ ] Commit the implementation with a clear Chinese message retaining technical names in English.

**Self-review:** The plan covers the requested protocol, four error types, SecretStr boundary, two SDK adapters, data URL analysis, explicit custom failure, registry filtering/metadata, dependencies, focused tests, no routes, and the protected vision document.
