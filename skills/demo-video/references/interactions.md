# System-specific interactions (FR-060 ~ FR-065)

Drag-and-drop, scrolling, hover tooltips, keyboard shortcuts, streaming output: the things a viewer can only experience in *this* system. Phase 3 finds them for every page in the approved outline, decides per item whether the video shows it, and writes the result into the scene's `interactions[]`. `validate` enforces the bookkeeping; the sheet shows the decisions as badges so the user can flip them at G3.

## Finding them: two signals, never one

Source alone may be dead code; screen alone hides how it works and the replay fails. Record both in `evidence`.

| Interaction | Source signal | Screen signal | Action |
|---|---|---|---|
| Drag-and-drop, sorting | dnd-kit, react-dnd, SortableJS, react-beautiful-dnd imports; `draggable`, `onDrop`, `onDragStart`; pointer handlers | drag handle icon, `aria-grabbed`, `cursor: grab` | `drag` |
| File drop upload | react-dropzone, `input[type=file]`, `onDrop` + `dataTransfer.files` | dashed drop area, "끌어다 놓으세요" | `dropFile` |
| Content revealed by scrolling | IntersectionObserver, infinite scroll hooks, virtual lists (react-window, tanstack-virtual), `position: sticky`, scroll-snap | `scrollHeight > clientHeight`, inner scroll container, header that stays | `scroll` |
| Hover | Tooltip / Popover components, `onMouseEnter`, `:hover`-only action buttons | `title`, `aria-describedby`, snapshot differs before/after hover | `hover` |
| Resize, split panels | react-resizable-panels, `resize` handlers, `cursor: col-resize` | handle between panels, `role=separator` | `resize` |
| Slider, range | `input[type=range]`, Slider component, date range picker | `role=slider`, `aria-valuenow` | `slide` |
| Canvas manipulation | React Flow, konva, d3-zoom, `onWheel` | large `canvas`/`svg`, minimap, zoom controls | `pan`, `wheelZoom` |
| Keyboard | hotkeys hooks, `onKeyDown`, command palette | shortcut labels (⌘K), `kbd` elements | `key` |
| Inline edit, multi-select | `onDoubleClick`, `contentEditable`, shift/ctrl selection | input appears on double click, checkbox column + bulk bar | `dblclick` |
| Context menu | `onContextMenu`, ContextMenu component | `role=menu` on right click | `rightClick` |
| Live updates | SSE, WebSocket, streaming response handling, polling | progress bar, text growing token by token, status badge changes | `waitStream` |

For agent products the last row matters most: a streamed answer or a stage-by-stage status change is usually the core experience.

## Deciding: `show` when any of these holds

- The scenario's task cannot be completed without the interaction.
- The information the subtitle talks about only appears through it (a summary below the fold, a number in a tooltip).
- It is the differentiator, the "oh, it does that" moment.

Otherwise `skip`. Every tooltip and every scroll makes the video long and unfocused; aim for at most two `show` per scene (`validate` warns above that). `blocked` when the source has it but the screen cannot reproduce it (no data, no permission) - `validate` lists blocked items so you can tell the user at G3 (FR-063).

An interaction that *is* the feature (moving a card on a kanban board, connecting nodes on a canvas) belongs in the phase-1 core feature list; phase 3 only decides how to show it (FR-065).

## Recording it

```json
{ "kind": "drag", "target": "[data-testid=case-card]", "mode": "pointer",
  "evidence": { "source": "src/board/Board.tsx: dnd-kit useSortable", "screen": "카드 좌측 드래그 핸들, cursor: grab" },
  "decision": "show", "reason": "우선순위 변경이 시나리오의 핵심 작업" }
```

`validate` requires both evidence fields and a reason, and for every `show` an action of the same kind on the same target somewhere in the scene's steps (FR-062). `key` matches by kind alone.

## How each one plays (prelude helpers)

| Action | Replay | Pair with |
|---|---|---|
| `drag` | cursor to the source → press (cursor shrinks, ring) → 10 eased steps over 600-900ms → 200ms pause over the target → release ripple | `highlight` the drop target; `zoom` first if the list is small, no zoom for long distances |
| `dropFile` | file icon ghost flies in from off-screen to the drop zone → files injected | `highlight` the drop zone |
| `scroll` | eased, capped at 60% of the viewport per second, 800ms still on arrival. Subtitles stay put (L3) | say what stays fixed in the subtitle if that is the point |
| `hover` | cursor in, wait for the tooltip, hold ≥ 1200ms | `zoom` if the tooltip is small |
| `resize` | like `drag` on the handle | - |
| `slide` | drag the knob; the dependent area should be in frame | `highlight` the result |
| `pan`, `wheelZoom` | drag or stepped wheel events on the canvas | never with page `zoom` |
| `key` | key cap overlay bottom-left for 1s while the key is pressed (L3) | - |
| `dblclick`, `rightClick` | two ripples / orange ripple | - |
| `waitStream` | waits until the stream is done (`until: attr|text|stable`); over 15s the span is marked for speed-up in compose | `highlight` the result when done |

### Drag modes

`mode` comes from the source signal, not from trial and error:

- `pointer` - the library listens to pointer/mouse events (dnd-kit, SortableJS, custom `pointerdown` handlers). Real mouse down, staged moves, mouse up.
- `html5` - native `draggable="true"` with `dragstart` / `dragover` / `drop` handlers. Synthetic DragEvents with a shared DataTransfer; the cursor still animates.

If neither works, mark the interaction `blocked`, tell the user at G3, and write the body by hand.
