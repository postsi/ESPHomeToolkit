# Canvas vs device parity — rollback and work list

## Rollback version

Before changing preview rendering or LVGL compile behavior, the repo was tagged:

- **Tag:** `pre-canvas-device-parity-2026-03-23` (annotated). It points at the commit **before** this document was added, so a checkout of the tag restores code only; read this file on `main` for the checklist.

**Return to this snapshot locally:**

```bash
git checkout pre-canvas-device-parity-2026-03-23
```

**Create a branch from it (to fix forward without losing main):**

```bash
git checkout -b fix/rollback-canvas-parity pre-canvas-device-parity-2026-03-23
```

**Publish the tag** (optional, for remotes):

```bash
git push origin pre-canvas-device-parity-2026-03-23
```

Add-on / Docker rollback is separate: use whatever image or add-on version you deployed from this commit, or rebuild from this tag.

---

## TODO — make canvas as close as possible to the device

Ordered roughly by impact vs effort. Check items off as you complete them.

### Foundation

1. ~~**Guarantee 1:1 logical pixels in the designer** — At default zoom, Konva stage width/height must equal project screen size with no accidental CSS scaling; document zoom behavior so “pixel” always means project pixels.~~ Done: `flexShrink: 0`, fixed wrapper size, copy under canvas + About.
2. ~~**Single alignment spec** — For each widget type, list LVGL properties emitted in YAML (padding, align, text_align, long_mode, etc.) and the Canvas equivalent; fix any missing or default mismatches when props are omitted.~~ Done: `frontend/src/lvglCanvasParity.ts` (doc + `effectiveLongMode` / shared defaults); button/textarea/label use same long-mode path.
3. ~~**Rounding policy** — Agree on integer rules for x/y/w/h and border/radius (floor vs round) and apply consistently in preview helpers (e.g. `canvasUtils`) and compiler output.~~ Done: `layoutInt` in `canvasUtils` (flex positions, corner radius cap); compiler comment in `views.py` `common()`.

### Typography

4. ~~**Load project fonts in the browser** — When `font` uses `asset:Something.ttf:N`, register that TTF via `@font-face` (or equivalent) in the designer and draw preview text with it at size `N` instead of system fonts.~~ Done: `GET /api/esptoolkit/assets/file`, `usePreviewFontResolver`, Montserrat from Google Fonts for `montserrat_*`.
5. ~~**Fallback labeling** — If the asset is missing or not a TTF, show a clear preview-only indicator so users know text metrics are approximate.~~ Done: `fontPreviewBanner` when `resolvePreviewFont` returns `approximate`.
6. ~~**Line break / long mode** — Match ESPHome/LVGL text long mode and line wrapping behavior where Konva supports it; document remaining gaps (e.g. ellipsis, scroll) as known preview limits.~~ Done: `konvaLongModeTextProps` + canvas copy (SCROLL → static ellipsis); `text_letter_space` on Konva Text.

### Layout

7. **Flex / container parity** — Extend `computeLayoutPositions` (and related Canvas code) until row/column flex, gap, and padding match LVGL for the subset you support in YAML; or explicitly restrict unsupported flex flags in the schema so the preview never lies.
8. **Nested containers** — Verify parent `pad_*`, border width, and content area match how widgets are positioned on device for container → child chains.

### Widget-by-widget audit

9. **Schema-driven regression set** — For each widget in the schema, one minimal fixture on canvas + same in compiled YAML; flash and visually compare (screenshot optional).
10. **Arcs, sliders, gauges** — These often diverge on stroke width, knob size, and angle mapping; align math with LVGL widget docs and existing audits (`WIDGET_SCHEMA_AUDIT.md`, `ESPHOME_WIDGET_PROPERTIES.md`).

### Automation and process

11. **Parity fixtures** — JSON under `frontend/public/parity-fixtures/`; compare designer export to Mac LVGL PNG (`docs/PARITY_PIPELINE.md`), not to committed browser goldens.
12. **Screenshot diff** — Playwright + `pixelmatch` vs sim snapshot URL; tolerance env vars when fonts/OS differ slightly.
13. **Round-trip guard** — After import-from-YAML (if applicable), assert geometry and key props match expected for fixtures (extends ideas in `ROUND_TRIP_TESTING.md`).

### Product / docs

14. **User-facing expectation** — Short note in About or docs: preview is geometrically aligned with the project; typography may differ slightly from firmware until fonts and long_mode fully match.

---

*Created when tag `pre-canvas-device-parity-2026-03-23` was added.*
