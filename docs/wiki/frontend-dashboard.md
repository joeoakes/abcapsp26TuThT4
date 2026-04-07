# Mission Dashboard (Modular Architecture)

The dashboard has been refactored into a decoupled, high-performance front-end stack with strict separation between:

- **Data Logic** (network and payload normalization)
- **UI Rendering** (DOM updates and visual widgets)
- **Style States** (theme variables and theme persistence)

## Directory Structure

```text
frontend/
  index.html
  css/
    main.css
  js/
    api.js
    ui-controller.js
    theme-engine.js
```

## File Responsibilities

### `index.html` (Skeleton)

- Contains only semantic layout containers and ID hooks.
- No inline styles.
- No inline scripts.
- Loads:
  - `/dashboard/css/main.css`
  - `/dashboard/js/ui-controller.js` (ES module entrypoint)

### `css/main.css` (Design System)

- Centralized CSS variable tokens for all visual surfaces.
- Theme states implemented via:
  - `html[data-theme="obsidian"]`
  - `html[data-theme="polar"]`
  - `html[data-theme="monolith"]`
- All colors, borders, and panel treatments come from variables.

### `js/api.js` (Data Engine)

- Pure fetch layer for server data.
- Exposes `fetchSessions()` and `fetchMission(sessionId)`.
- Returns normalized, clean JSON for UI use.
- No DOM operations.

### `js/ui-controller.js` (Renderer)

- Owns user interactions and DOM updates.
- Renders mission cards, movement matrix, chrono-gauges, and telemetry panels.
- Controls non-functional texture data (latency ticker, fluctuating resource HUD, coordinate stream, session fingerprint).
- Uses a **requestAnimationFrame render loop** for coordinate stream painting to keep UI smooth during frequent updates.

### `js/theme-engine.js` (State Manager)

- Dedicated theme manager with localStorage persistence.
- Applies theme through `data-theme` on `<html>`.
- Exposes `initThemeEngine(selectElement)`.

## Runtime Integration

The FastAPI server now serves the `frontend/` directory at the `/dashboard/*` route:

- `/dashboard/` (loads `index.html`)
- `/dashboard/css/main.css`
- `/dashboard/js/*.js`

## Data Source

Primary mission source remains:

- Redis hash: `mission:{session_id}:summary`

Session list source:

- `GET /sessions` filtered to IDs with `team4` prefix.
