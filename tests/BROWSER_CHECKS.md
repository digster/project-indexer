# Browser regression checks

From the repository root:

```bash
uv run python -m tests.browser_fixture /tmp/project-indexer-ui
uv run python -m http.server 8765 --bind 127.0.0.1 --directory /tmp/project-indexer-ui
```

Open `http://127.0.0.1:8765/checks.html` in an active browser tab. It runs 11
assertion groups and prepends a PASS/FAIL report. Reload to rerun. The fixtures
contain 61 projects with all eight statuses, unpadded numbers, reversed paths,
and variable description lengths. They never inspect or modify real projects.

Coverage includes all three sortable columns in both directions, sorting
before pagination, numeric commit counts, all status filters in both views,
combined search/status filtering, no matches, page reset, dropdown keyboard
events, full/short-page scroll preservation, focus restoration, and All.

Additional manual checks on `index.html` and `empty.html`:

- Select All, reload, and verify that All and all 61 projects remain visible.
- Use Tab and Enter/Space to operate sort buttons. Confirm the direction changes
  and a screen reader can read the selected header's `aria-sort` state.
- Use arrow keys inside the status and page-size dropdowns; the controls should
  behave normally without triggering global page navigation.
- Check the first/last and current-page buttons. Disabled controls must do
  nothing; clicking the current page must not move the viewport or lose focus.
- Check 320px and 390px widths and a desktop width. The toolbar should wrap;
  any table overflow must stay inside its wrapper rather than widening the page.
- In an empty index, sort and change status without errors or phantom entries.
  For a filter producing one result, pagination may move up because the whole
  document fits in the viewport; that is the browser's normal scroll boundary.
- Try duplicate names, accented/mixed-case names, paths with HTML characters,
  long paths, and large commit counts. Names/paths break status ties consistently.

The tests modify only view/page-size preferences on the temporary local origin.
Stop the server after testing. Do not commit generated HTML or screenshots.
