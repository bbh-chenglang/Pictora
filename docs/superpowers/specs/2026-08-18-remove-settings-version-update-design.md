# Remove Settings Version Update Module

## Scope

Remove only the "版本更新" module from the frontend settings page. Keep other version displays, build-version configuration, and the backend `/api/version` endpoint unchanged.

## Design

- Remove the settings-page markup that displays the version update action and status.
- Remove frontend-only state, computed labels, and functions used exclusively by that module, including the `/api/version` request and refresh/apply handlers.
- Leave `CLIENT_VERSION` only if it has another consumer; otherwise remove it as part of the dead-code cleanup.
- Do not change backend routes, version response behavior, or build/deployment configuration.

## Verification

- Add a focused Vitest test covering the settings-page behavior: the settings view must not render "版本更新" and entering settings must not request `/api/version`.
- Run the focused test and the complete frontend test suite.
- Run `npm run typecheck` and `npm run build`.
- Confirm the backend `/api/version` implementation remains unchanged.

## Acceptance Criteria

1. The settings page contains no version-update module or action.
2. The frontend contains no unreachable version-update state or handlers.
3. The backend `/api/version` endpoint and build-version configuration remain available.
4. The focused test, frontend tests, typecheck, and build pass.
