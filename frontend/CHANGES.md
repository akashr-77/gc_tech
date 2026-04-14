# Frontend Enhancement — Changes & How It Works

## Overview

Two features were added to the **Manhattan Project** AI Event Planner frontend:

1. **Agent Thinking / Status Indicator** — A dynamic, animated processing state during agent work
2. **Chat Sidebar** — A ChatGPT-style left-hand collapsible panel for conversation history

---

## Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `src/components/ThinkingIndicator.jsx` | **NEW** | Animated thinking/processing component |
| `src/components/ChatSidebar.jsx` | **NEW** | Left-hand collapsible conversation history panel |
| `src/components/ProgressView.jsx` | **MODIFIED** | Replaced inline spinner + stage list with `ThinkingIndicator` |
| `src/App.jsx` | **MODIFIED** | Layout restructured for left sidebar, added toggle state |
| `src/index.css` | **MODIFIED** | Added sidebar, thinking indicator, and responsive CSS |
| `src/components/SessionHistory.jsx` | **SUPERSEDED** | Functionality absorbed into `ChatSidebar.jsx` |

---

## Feature 1: Thinking Indicator

### How It Works

**`ThinkingIndicator.jsx`** is a self-contained React component that displays processing state during agent work.

```
┌─────────────────────────────────────┐
│  ✦  Sourcing venues…         ▾     │  ← Sparkle icon + current stage + expand toggle
│  ████████████████████████████       │  ← Shimmer bar (wide)
│  ██████████████████                 │  ← Shimmer bar (medium)
│  ████████████                       │  ← Shimmer bar (narrow)
│        Analyzing inputs… •••        │  ← Rotating status message + typing dots
└─────────────────────────────────────┘
```

**Key behaviors:**
- **Shimmer bars** — Three skeleton loading bars animate with a gradient sweep (`@keyframes shimmer`)
- **Typing dots** — Three dots bounce sequentially (`@keyframes dot-bounce`)
- **Sparkle icon** — SVG star pulses with scale + opacity (`@keyframes sparkle-pulse`)
- **Status messages** cycle every 3.2s: "Searching data…" → "Analyzing inputs…" → etc.
- **Collapsible details** — Click the stage label to expand/collapse a full stage tracker showing all 8 agent stages with done/active/pending states
- **Smooth transitions** — Status text fades in with `@keyframes fade-slide-in`, details panel uses `max-height` transition

**Props:**
- `stages` — Array of `{ key, label, icon }` from `ProgressView`
- `currentStageIndex` — Which stage is currently active
- `isActive` — Whether the indicator should be animating

### Integration with ProgressView

`ProgressView.jsx` passes its existing `AGENT_STAGES` array and `stageIdx` state to `ThinkingIndicator`. The polling logic, elapsed timer, and stage advancement (every ~7s) are **unchanged**.

---

## Feature 2: Chat Sidebar

### How It Works

**`ChatSidebar.jsx`** renders a fixed left-hand panel modeled after ChatGPT's sidebar.

```
┌──────────────┐┌──────────────────────────┐
│ + New Chat  ☐││  ⚡ Manhattan Project     │
│──────────────││──────────────────────────│
│ Recent       ││                          │
│ 🏛️ AI Conf  ●││   [Main Content Area]    │
│ 🎵 Music F  ●││                          │
│ 🏆 Sports   ●││                          │
│              ││                          │
│              ││                          │
│──────────────││                          │
│ 🗑 Clear all ││                          │
└──────────────┘└──────────────────────────┘
```

**Key behaviors:**
- **Slide in/out** — Uses `transform: translateX(-100%)` ↔ `translateX(0)` with `cubic-bezier(.4,0,.2,1)` easing
- **Main content shifts** — `.app-main` gets `margin-left: 280px` when sidebar is open (CSS transition)
- **"+ New Chat" button** — Resets the app to the home/form view
- **Session list** — Reads from `localStorage` key `mp_sessions` (same as the old `SessionHistory`)
- **Active highlighting** — Current session gets a blue-tinted background
- **Status dots** — Color-coded dots (green=completed, amber=working, blue=starting, red=failed)
- **Time ago** — Shows relative time like "5m ago", "2h ago", "3d ago"
- **Clear all** — Deletes all saved sessions from localStorage

### Toggle Mechanism

- A **sidebar toggle button** (panel icon SVG) is in the header
- The sidebar itself has a **close button** (same icon) in its top-right corner
- On mobile (`< 768px`): the sidebar overlays content with a backdrop; tapping outside closes it

### Data Persistence

Sessions are stored in `localStorage` under the key `mp_sessions`. The sidebar polls this every 5 seconds to pick up new sessions added by the main form submission flow. No backend is required for persistence.

---

## Layout Changes in App.jsx

**Before:** `grid-template-columns: 1fr 320px` (content | right sidebar)

**After:** Fixed left sidebar + shifting main area:
```
.app { display: flex }             ← Horizontal flex
.chat-sidebar { position: fixed }  ← Fixed left panel
.app-main { margin-left: 280px }   ← Shifts when sidebar is open
```

The old `<aside className="sidebar">` with `SessionHistory` is removed. Its functionality is now in `ChatSidebar`.

---

## CSS Architecture

All new styles are in `index.css` organized into sections:

| Section | What It Does |
|---------|-------------|
| `App Layout` | Flex container, `margin-left` transition for sidebar |
| `Chat Sidebar` | Fixed position, slide transform, session items, mobile overlay |
| `Thinking Indicator` | Shimmer bars, typing dots, sparkle pulse, expandable details |
| `Mobile responsive` | Sidebar as overlay below `768px`, backdrop blur |

### Key Animations

| Animation | Used For | Duration |
|-----------|----------|----------|
| `shimmer` | Skeleton loading bars | 1.8s infinite |
| `dot-bounce` | Typing indicator dots | 1.4s infinite |
| `sparkle-pulse` | Sparkle icon | 2s infinite |
| `stage-pulse` | Active stage dot glow | 1.5s infinite |
| `fade-slide-in` | Status message transition | 0.4s |

---

## Running the App

```bash
cd newproj/frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser. The backend API is not required for the sidebar and thinking indicator to function visually — they work independently with localStorage and simulated stage progression.
