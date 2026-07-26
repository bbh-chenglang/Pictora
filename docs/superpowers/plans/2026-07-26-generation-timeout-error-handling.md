# Generation Timeout and Error Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend image generation to three minutes per image and display stable errors when a proxy response has no JSON body.

**Architecture:** Keep timeout ownership in `ImageService`, with Nginx providing a margin above the maximum backend duration. Add a small frontend response parser that preserves structured JSON errors but safely handles empty or malformed proxy responses.

**Tech Stack:** Python asyncio, FastAPI, Vue 3, TypeScript, Vitest, Nginx

---

### Task 1: Backend timeout

**Files:**
- Modify: `backend/tests/test_image_service.py`
- Modify: `backend/app/services/image_service.py`

- [ ] Rename the timeout test to describe three minutes per generated image and expect `540` seconds for `count=3`.
- [ ] Run the focused Pytest test and confirm it fails with actual value `180`.
- [ ] Change `asyncio.timeout(count * 60)` to `asyncio.timeout(count * 180)`.
- [ ] Run the focused backend test and then the full backend suite.

### Task 2: Frontend response parsing

**Files:**
- Modify: `frontend/src/App.test.ts`
- Modify: `frontend/src/App.vue`

- [ ] Add a component test whose generation request returns an empty HTTP 504 response and assert `生成失败（HTTP 504）`.
- [ ] Run the focused Vitest test and confirm it fails with `Unexpected end of JSON input`.
- [ ] Add a response parser that reads text, returns parsed JSON when valid, and returns `null` for empty or malformed bodies.
- [ ] Use the parser in generation handling, preserving structured errors and rejecting invalid successful responses.
- [ ] Run the focused frontend test and then the full frontend suite.

### Task 3: Proxy timeout and publication

**Files:**
- Modify: `frontend/nginx.conf`

- [ ] Change API `proxy_read_timeout` and `proxy_send_timeout` from `300s` to `780s`.
- [ ] Run the frontend production build and `docker compose config --quiet`.
- [ ] Review the diff and verify unrelated local documents remain untracked.
- [ ] Commit the fix, merge it into `master`, rerun all verification, and push `master` to GitHub.
