# GenImage Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a light, art-directed Vue/FastAPI demo that generates images and analyzes uploaded images through OpenAI or a configurable OpenAI-compatible provider.

**Architecture:** The Vue double-column workspace talks only to three FastAPI endpoints. The backend resolves a provider adapter, normalizes provider-specific requests and responses, and returns a stable application schema. Frontend state remains local to composables and components; no Pinia is used.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic Settings, OpenAI Python SDK, httpx, pytest, Vue 3, Vite, TypeScript, Tailwind CSS, shadcn-vue, lucide-vue-next, Vitest, Playwright.

---

## File Map

Backend files will live under `backend/app/` and keep transport, domain schemas, provider selection, and provider implementations separate. Frontend files will live under `frontend/src/` and keep API calls, composables, view composition, and presentational controls separate.

```text
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   ├── api/providers.py
│   ├── api/generate.py
│   ├── api/analyze.py
│   ├── schemas/common.py
│   ├── schemas/generate.py
│   ├── schemas/analyze.py
│   ├── providers/base.py
│   ├── providers/openai_provider.py
│   ├── providers/compatible_provider.py
│   ├── providers/custom_provider.py
│   ├── providers/registry.py
│   └── services/image_service.py
├── tests/
│   ├── test_provider_registry.py
│   ├── test_image_service.py
│   └── test_api.py
├── requirements.txt
├── requirements-dev.txt
└── .env.example

frontend/
├── src/
│   ├── api/client.ts
│   ├── api/providers.ts
│   ├── api/images.ts
│   ├── types/api.ts
│   ├── composables/useProviders.ts
│   ├── composables/useImageActions.ts
│   ├── components/ProviderSelector.vue
│   ├── components/PromptPanel.vue
│   ├── components/ImageUploader.vue
│   ├── components/ResultCanvas.vue
│   ├── components/StatusNotice.vue
│   ├── views/StudioView.vue
│   ├── App.vue
│   └── main.ts
├── tests/
│   ├── useImageActions.spec.ts
│   └── StudioView.spec.ts
├── package.json
├── vite.config.ts
├── tailwind.config.ts
└── .env.example
```

## Task 1: Create the backend project and stable schemas

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/requirements-dev.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/schemas/common.py`
- Create: `backend/app/schemas/generate.py`
- Create: `backend/app/schemas/analyze.py`
- Create: `backend/tests/test_api.py`
- Create: `backend/.env.example`

- [ ] **Step 1: Add dependencies and configuration.**

`requirements.txt` must contain `fastapi`, `uvicorn[standard]`, `openai`, `httpx`, `pydantic-settings`, and `python-multipart`. `requirements-dev.txt` must contain `pytest`, `pytest-asyncio`, and `httpx`.

`config.py` defines a `Settings` class with `openai_api_key`, `openai_base_url`, `openai_model`, `custom_api_key`, `custom_base_url`, and `custom_model`, all loaded from environment variables with empty-string defaults except base URLs and model names.

- [ ] **Step 2: Define application schemas before route code.**

Define these Pydantic models:

```python
class ProviderModel(BaseModel):
    id: str
    label: str
    models: list[str]

class ImageResult(BaseModel):
    url: str | None = None
    base64_data: str | None = None
    revised_prompt: str | None = None

class GenerateRequest(BaseModel):
    provider: str
    model: str
    prompt: str = Field(min_length=1, max_length=4000)
    detail: Literal["low", "high", "original", "auto"] = "auto"

class GenerateResponse(BaseModel):
    provider: str
    model: str
    images: list[ImageResult]

class AnalyzeResponse(BaseModel):
    provider: str
    model: str
    text: str

class ErrorBody(BaseModel):
    code: str
    message: str
```

`AnalyzeRequest` is represented by multipart form fields in the route because it includes an uploaded file.

- [ ] **Step 3: Write schema validation tests.**

Test that an empty prompt returns a Pydantic validation error, `detail="auto"` is the default, and an unsupported detail value is rejected.

- [ ] **Step 4: Run the focused test.**

Run: `cd backend; python -m pytest tests/test_api.py -q`

Expected: PASS for schema tests; route tests remain skipped until Task 3.

- [ ] **Step 5: Commit the backend foundation.**

```bash
git add backend
git commit -m "feat: add backend schemas and configuration"
```

## Task 2: Implement provider adapters and registry

**Files:**
- Create: `backend/app/providers/base.py`
- Create: `backend/app/providers/openai_provider.py`
- Create: `backend/app/providers/compatible_provider.py`
- Create: `backend/app/providers/custom_provider.py`
- Create: `backend/app/providers/registry.py`
- Create: `backend/app/dependencies.py`
- Create: `backend/tests/test_provider_registry.py`
- Create: `backend/tests/test_image_service.py`

- [ ] **Step 1: Write adapter contract tests.**

Define fake provider doubles in the tests and assert that the registry resolves `openai`, `compatible`, and `custom`, while an unknown provider raises a typed `ProviderNotFoundError`.

Assert that every adapter exposes:

```python
async def generate_image(self, request: GenerateRequest) -> GenerateResponse: ...
async def analyze_image(
    self,
    model: str,
    prompt: str,
    image_bytes: bytes,
    content_type: str,
) -> str: ...
```

- [ ] **Step 2: Implement the base errors and protocol.**

Create `ProviderError` with `code` and `message`, plus `ProviderNotFoundError`, `ProviderAuthError`, `ProviderTimeoutError`, and `ProviderRequestError`. Define the `ImageProvider` protocol in `base.py`.

- [ ] **Step 3: Implement OpenAI and compatible adapters.**

`OpenAIProvider` constructs `OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)` and calls the SDK. `CompatibleProvider` uses the same SDK shape but reads the custom key and base URL. Both adapters must normalize image output into `ImageResult` and catch SDK authentication, timeout, and request exceptions without leaking credentials.

For image analysis, use a URL or `data:<mime>;base64,<payload>` input and return the SDK's text output. Do not write uploaded image bytes outside the request lifecycle.

- [ ] **Step 4: Implement the custom adapter boundary.**

`CustomProvider` must raise a clear `provider_not_implemented` error rather than silently routing a non-compatible provider through the OpenAI adapter. This keeps the extension point explicit while the Demo only enables OpenAI-compatible providers.

- [ ] **Step 5: Implement the registry.**

`ProviderRegistry.from_settings(settings)` registers only providers with a configured API key. `list_models()` returns safe public metadata for the frontend and never returns keys or full settings objects.

- [ ] **Step 6: Run provider tests.**

Run: `cd backend; python -m pytest tests/test_provider_registry.py tests/test_image_service.py -q`

Expected: PASS without network access. All SDK calls must be mocked.

- [ ] **Step 7: Commit the adapter layer.**

```bash
git add backend/app/providers backend/app/dependencies.py backend/tests/test_provider_registry.py backend/tests/test_image_service.py
git commit -m "feat: add image provider adapters"
```

## Task 3: Add FastAPI routes and application errors

**Files:**
- Create: `backend/app/services/image_service.py`
- Create: `backend/app/api/providers.py`
- Create: `backend/app/api/generate.py`
- Create: `backend/app/api/analyze.py`
- Create: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Write route tests with mocked providers.**

Use FastAPI `TestClient` and dependency overrides. Cover:

```text
GET /api/providers -> 200 and provider metadata without secrets
POST /api/generate with a valid prompt -> 200 and normalized images
POST /api/generate with an empty prompt -> 422
POST /api/analyze with a JPEG upload -> 200 and normalized text
unknown provider -> 400 with provider_not_found
provider timeout -> 504 with provider_timeout
```

- [ ] **Step 2: Implement the service layer.**

`ImageService` receives a registry, resolves the requested provider, calls the adapter, and returns the stable response schema. It must preserve the requested provider and model in successful responses.

- [ ] **Step 3: Implement routes.**

Mount `/api/providers`, `/api/generate`, and `/api/analyze` under the FastAPI app. `/api/analyze` accepts `provider`, `model`, `prompt`, `detail`, and `image: UploadFile`; reject unsupported MIME types before calling a provider.

- [ ] **Step 4: Add one global exception handler.**

Map provider exceptions to the agreed response:

```json
{
  "error": {
    "code": "provider_timeout",
    "message": "The selected provider timed out"
  }
}
```

Never include stack traces, authorization headers, or raw SDK payloads in the response.

- [ ] **Step 5: Run the API suite.**

Run: `cd backend; python -m pytest -q`

Expected: PASS with no external API calls.

- [ ] **Step 6: Commit the API layer.**

```bash
git add backend/app backend/tests/test_api.py
git commit -m "feat: expose image generation and analysis APIs"
```

## Task 4: Scaffold the Vue application and design tokens

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/types/api.ts`
- Create: `frontend/.env.example`

- [ ] **Step 1: Scaffold Vue with TypeScript.**

Create the Vite Vue TypeScript app, install Tailwind CSS, shadcn-vue dependencies, `lucide-vue-next`, `axios`, Vitest, and Vue Test Utils. Configure the dev server to proxy `/api` to `http://localhost:8000`.

- [ ] **Step 2: Define frontend API types.**

Mirror the backend schemas for `ProviderModel`, `ImageResult`, `GenerateResponse`, `AnalyzeResponse`, and `ApiError`. Keep API types in `src/types/api.ts` rather than duplicating them inside components.

- [ ] **Step 3: Add visual tokens.**

Define light-theme tokens for the Art Lab direction: warm-white canvas, black ink borders, bright yellow controls, coral primary actions, and teal result accents. Use Tailwind utilities and CSS variables; avoid gradients and fabricated metrics.

- [ ] **Step 4: Verify the empty app.**

Run: `cd frontend; npm run build`

Expected: PASS and produce a Vite production bundle.

- [ ] **Step 5: Commit the frontend foundation.**

```bash
git add frontend
git commit -m "feat: scaffold Vue studio frontend"
```

## Task 5: Build API client and composables without Pinia

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/providers.ts`
- Create: `frontend/src/api/images.ts`
- Create: `frontend/src/composables/useProviders.ts`
- Create: `frontend/src/composables/useImageActions.ts`
- Create: `frontend/tests/useImageActions.spec.ts`

- [ ] **Step 1: Write composable tests.**

Mock the API client and test that `generate()` transitions `idle -> loading -> success`, stores images, and returns a normalized error on failure. Test that `analyze()` sends `FormData` and stores returned text. Test that a second request clears only the previous error and preserves the prompt.

- [ ] **Step 2: Implement the API client.**

Use Axios with `/api` as the base URL. Add one error normalizer that reads `{ error: { code, message } }` and falls back to a generic message without displaying raw response objects.

- [ ] **Step 3: Implement provider API functions.**

Add `fetchProviders()`, `generateImage(payload)`, and `analyzeImage(payload)`. `analyzeImage()` must append provider, model, prompt, detail, and image to `FormData`.

- [ ] **Step 4: Implement local composables.**

`useProviders()` owns provider options, selected provider, selected model, and initial loading/error state. `useImageActions()` owns prompt, selected detail, uploaded image, generated images, analysis text, loading state, and error state. Do not create a singleton store.

- [ ] **Step 5: Run composable tests.**

Run: `cd frontend; npm run test -- --run`

Expected: PASS with all network calls mocked.

- [ ] **Step 6: Commit the frontend data layer.**

```bash
git add frontend/src/api frontend/src/composables frontend/src/types frontend/tests/useImageActions.spec.ts
git commit -m "feat: add frontend image action composables"
```

## Task 6: Build the Art Lab double-column workspace

**Files:**
- Create: `frontend/src/components/ProviderSelector.vue`
- Create: `frontend/src/components/PromptPanel.vue`
- Create: `frontend/src/components/ImageUploader.vue`
- Create: `frontend/src/components/ResultCanvas.vue`
- Create: `frontend/src/components/StatusNotice.vue`
- Create: `frontend/src/views/StudioView.vue`
- Modify: `frontend/src/App.vue`
- Create: `frontend/tests/StudioView.spec.ts`

- [ ] **Step 1: Write view tests.**

Test that the view renders provider/model controls, prompt input, upload control, Generate and Analyze buttons, and an empty result state. Test that Generate is disabled without a prompt, Analyze is disabled without an image, and loading disables the active action.

- [ ] **Step 2: Implement the control components.**

Use shadcn-vue controls with labels and Lucide icons. Keep standard action labels such as “Generate image”, “Analyze image”, “Download”, and “Remove image”. Do not use Unicode symbols as icons.

- [ ] **Step 3: Implement the result canvas.**

Render a stable two-column image grid on desktop and one column on narrow screens. Render image previews, download actions, analysis text, empty state, loading state, and error state without shifting the main layout.

- [ ] **Step 4: Compose `StudioView.vue`.**

Connect the composables to the controls. Keep the left panel fixed within the page grid and let the right canvas scroll independently when results grow. Preserve entered prompt and selected provider after errors.

- [ ] **Step 5: Apply Art Lab styling.**

Use the approved light palette: warm white page, black borders, bright yellow secondary controls, coral primary action, teal result accents. Use a strong grid, hard-edged borders, restrained radius, and image-first spacing. Avoid dark panels, gradients, fake stats, and nested cards.

- [ ] **Step 6: Run view tests and build.**

Run: `cd frontend; npm run test -- --run; npm run build`

Expected: PASS and a successful production build.

- [ ] **Step 7: Commit the workspace UI.**

```bash
git add frontend/src frontend/tests/StudioView.spec.ts
git commit -m "feat: add Art Lab image studio workspace"
```

## Task 7: Integrate, verify, and document local run commands

**Files:**
- Create: `README.md`
- Modify: `backend/.env.example`
- Modify: `frontend/.env.example`
- Create: `backend/tests/test_smoke.py`

- [ ] **Step 1: Add a backend smoke test.**

Start the FastAPI app with empty provider keys and assert `GET /api/providers` returns 200 with an empty or configured-safe provider list. This verifies the app can start without a configured provider.

- [ ] **Step 2: Add local setup documentation.**

Document exact commands:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
uvicorn app.main:app --app-dir backend --reload --port 8000

cd frontend
npm install
npm run dev
```

Document both OpenAI and compatible-provider environment variables, and state that keys remain server-side.

- [ ] **Step 3: Run the complete automated verification.**

```bash
cd backend; python -m pytest -q
cd ..\frontend; npm run test -- --run; npm run build
```

Expected: all backend and frontend tests pass and the frontend build succeeds.

- [ ] **Step 4: Run browser smoke checks.**

Start backend and frontend, open the Vite URL, and verify at desktop and mobile widths:

```text
Provider list loads without exposing keys.
Generate button validates an empty prompt.
Analyze button validates a missing image.
Uploading an image shows its preview and remove action.
Provider timeout/error appears in the result area.
Successful mocked generation displays image tiles.
Successful mocked analysis displays text.
The two-column workspace collapses cleanly on mobile.
```

- [ ] **Step 5: Commit integration documentation and smoke coverage.**

```bash
git add README.md backend/.env.example frontend/.env.example backend/tests/test_smoke.py
git commit -m "docs: add GenImage demo setup and verification"
```

## Self-Review Checklist

- The plan covers both generation and analysis.
- Provider selection, OpenAI compatibility, and custom adapter boundaries are explicit.
- No task introduces Pinia or another global state library.
- The approved A layout and C Art Lab visual direction are represented in the frontend task.
- API keys remain backend-only.
- Tests cover schemas, provider selection, API errors, composable states, UI validation, and the production build.
- `.superpowers/` remains ignored and is not part of implementation commits.
