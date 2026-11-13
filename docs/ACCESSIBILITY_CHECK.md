# Manual accessibility check – MEA Process Hub 1.5.1

**Why:** the build runs axe-core (WCAG 2.1 A/AA) on nine pages and finds nothing. An automated rule set finds only part of the possible problems:
it cannot judge whether the reading order makes sense, whether a flowchart is understandable without seeing it, or whether focus goes where a person expects.
This check closes that gap. Two people, about 2 hours (estimate), on the pilot server or a local installation with the delivered library.

**Who:** one person who works with the keyboard only (no mouse) and one who uses a screen reader. If nobody uses one daily, IT or the works council may know a colleague who does.
**Tools:** Windows Narrator (built in, Win+Ctrl+Enter) or NVDA (free); Edge or Chrome; browser zoom; Windows *High contrast* mode.
**Rule:** record every failure with the page, what was done, what happened and what was expected. Do not fix on the spot; the maintainer needs the list.

## A. Keyboard only (no mouse)
Tab / Shift+Tab move, Enter and Space activate, arrow keys move inside tabs and menus, Esc closes dialogs.
| # | Task | Passes when |
|---|---|---|
| A1 | Sign in, reach the dashboard | Every field and button is reachable in a sensible order; the focus is always visible |
| A2 | Open the library, filter, open a process | Table rows or links are reachable; no mouse-only control |
| A3 | Move between the tabs of a process (content, flow, RACI, history …) | Tabs work with the keyboard; the active tab is announced or visible |
| A4 | Open and close a dialog (for example *Suggest a change*) | Focus moves into the dialog, stays there, returns to the button on close; Esc closes |
| A5 | Landscape map: open a process from the map | Hot spots are reachable and activated with Enter |
| A6 | Write a comment on a flow step | Works without the mouse |
| A7 | Edit a draft and save (editor role) | All fields reachable; the save result is visible |
| A8 | Review, approve, publish with the password prompt (reviewer, approver, controller) | The prompt receives focus; a wrong password is announced |
| A9 | Skip to the main content from the top of any page | A way past the navigation exists |
| A10 | Search, open a result | Works; no focus trap |

## B. Screen reader
| # | Task | Passes when |
|---|---|---|
| B1 | Page title and main heading on each page | Each page announces where you are |
| B2 | Headings list (screen reader function) on a process page | Headings form a sensible outline |
| B3 | Forms: every field announces its name, required state and error text | No unnamed field |
| B4 | Tables: library, register, signed-decisions table | Column headers are announced with the cell |
| B5 | Status chips and colours (draft, in review, published, overdue) | The state is in the text, not only in colour |
| B6 | **Flowchart**: can a person who cannot see it follow the process? | A text alternative exists: the step list with owner and next step. If not, record it as a finding – this is the most likely failure |
| B7 | Messages after an action (saved, error, signed) | Announced without moving the focus |
| B8 | Dialogs and the password prompt | Announced as a dialog with a name |

## C. Zoom, contrast, small screens
| # | Task | Passes when |
|---|---|---|
| C1 | Browser zoom 200 % and 400 % on dashboard, library, process | Nothing is cut off; no horizontal scrolling for the main text |
| C2 | Windows *High contrast* mode | Text, borders and buttons stay visible |
| C3 | Text size only (browser setting) | Layout holds |
| C4 | Phone width | Process page readable; controls can be tapped |

## D. Result
| Finding | Page | Severity (blocks use / hinders / minor) | Owner |
|---|---|---|---|
| | | | |

Decision rule: any "blocks use" finding is fixed before the tool is rolled out to the region; "hinders" findings go into the next release. Send the table to the maintainer.
State plainly that this check covers WCAG 2.1 A/AA as far as these tasks go; it is not a certified audit.
