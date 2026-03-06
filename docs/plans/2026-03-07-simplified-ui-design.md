# ACE v2 — Simplified Single-Coder Interface

## Flow

1. Landing — New Project (pick save location) / Open Project (native file picker)
2. Import — Upload CSV or load folder of text files
3. Coding — Two-pane interface

## Coding Interface

```
┌──────────────────────┬─────────────────────────────────────────┐
│ CODES                │ TEXT                                    │
│                      │                                         │
│ ┌──────────────────┐ │ The participant described their          │
│ │ + Type new code… │ │ experience as "overwhelming" and        │
│ └──────────────────┘ │ noted that the [intervention] had       │
│                      │ a significant impact on their            │
│ ■ Anxiety    [1] ... │ daily routine...                        │
│ ■ Coping     [2] ... │                                         │
│ ■ Support    [3] ... │                                         │
│ ■ Barriers   [4] ... │                                         │
│                      │                                         │
├──────────────────────┴─────────────────────────────────────────┤
│ ◄ Prev │ ■■■■■■■○○○ 7/10 │ Next ►       [Complete] [Flag]    │
└────────────────────────────────────────────────────────────────┘
```

## Interactions

- Create code: always-visible input, Enter to create, colour auto-assigned
- Apply code: select text in right panel, click code on left (or press 1-9)
- Manage code: "..." menu per code row — rename, change colour, delete
- Navigate: bottom bar prev/next, clickable progress bar
- Undo/redo: Ctrl+Z / Ctrl+Shift+Z

## Removed

- Manager stepper (import_data, codebook, assign, results pages)
- Manager/coder role distinction
- Coder assignment & export/import workflow
- ICR analysis
- Onboarding overlay

## Parked for later

- Multi-coder workflow (future "Extras" on landing page)
- ICR analysis (needs expert input)
- Adding sources after project creation

## Database

Schema unchanged for backwards compat. `file_role` ignored (always single-user).
`coder` and `assignment` tables unused; a default coder row created automatically.
`codebook_code` created inline during coding.
