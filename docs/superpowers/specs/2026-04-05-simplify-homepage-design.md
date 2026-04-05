# Simplify Homepage

## Summary

Redesign the ACE landing page to be cleaner and more minimal. Replace the recent files list with a single conditional "Resume" link. Add the full app name as a subtitle under the logo. Simplify the visual hierarchy to a vertical stack with generous spacing.

## Layout

```
     [ A ][ C ][ E ]
     ━━━━━━━━━━━━━━━
  Annotation Coding Environment

      my-project.ace           ← conditional underlined link, only if last project exists

       New project
        Open file


         TOOLS
    Inter-Coder Agreement
```

### Sections (top to bottom)

1. **Logo** — `logo-light.svg` (dark tiles on white), centred
2. **Subtitle** — "Annotation Coding Environment" in small-caps or uppercase muted text, centred below logo
3. **Resume link** (conditional) — only rendered when localStorage has a previous project. Shows just the filename (e.g. "my-project.ace") as a subtle underlined link. No "Resume:" label — the position implies it. If localStorage has no recent files, the link is not rendered.
4. **New project** — bold/dark text link, starts the new project flow (name → folder → coder name)
5. **Open file** — muted/grey text link, opens native file picker
6. **Tools** — muted section label + "Inter-Coder Agreement" link, positioned at the bottom with generous top margin

### Spacing
- Logo to subtitle: 8px
- Subtitle to resume (or to New project if no resume): 32px
- Resume to New project: 24px
- New project to Open file: 8px
- Open file to Tools: generous bottom margin (push Tools toward bottom)

## Behaviour Changes

### Resume link
- Reads the first entry from the existing `ace-recent-files` localStorage key (same data source as current recents list)
- Displays only the filename (not the full path), e.g. "my-project.ace" — no label, just the filename as a subtle underlined link
- Clicking it opens the project (same `openProject()` flow as current recent file click)
- If localStorage has no recent files, the resume link is not rendered at all
- If the user creates or opens a project, the recent files list is still updated in localStorage (for resume to work next time)

### Removed
- The entire "Recent" section (section label + list of up to 5 recent files + "No recent projects" empty state)
- The "Start" section label (no longer needed — the actions speak for themselves)
- The pipe separator between "New project" and "Open file" (they're now stacked vertically, not inline)

### Kept unchanged
- New project expand flow (name → folder pick → coder name)
- Open file native picker flow
- Tools section with Inter-Coder Agreement link
- Cloud sync warning for Dropbox/OneDrive/iCloud paths
- All localStorage logic (reading/writing recent files)

## Files to Modify

- `src/ace/templates/landing.html` — restructure markup, remove recents list, add resume link, add subtitle
- `src/ace/static/css/ace.css` — update `.ace-home-*` styles for new vertical layout, remove recents-specific styles

## Visual Style

- "New project" — `font-size: var(--ace-font-size-lg)`, `font-weight: var(--ace-weight-medium)`, `color: var(--ace-text)`, no underline
- "Open file" — same font size, `color: var(--ace-text-muted)`, no underline
- Resume link — `font-size: var(--ace-font-size-md)`, `color: var(--ace-text-muted)`, `text-decoration: underline`, `text-underline-offset: 3px`, `text-decoration-color: var(--ace-border-light)`. No label — just the filename.
- Subtitle — `font-size: var(--ace-font-size-xs)`, `letter-spacing: 2-3px`, `text-transform: uppercase`, `color: var(--ace-text-muted)`
- Section label "TOOLS" — same style as current `.ace-home-section-label`
