/* Run against the synthetic document built by tests.browser_fixture.
   Assertions use rendered rows and controls rather than application internals. */
(async function () {
  const results = [];
  const $ = selector => document.querySelector(selector);
  const visibleRows = () => [...document.querySelectorAll('.project-row:not(.hidden)')];
  const names = () => visibleRows().map(row => row.querySelector('.col-name').textContent);
  const paths = () => visibleRows().map(row => row.querySelector('.col-path').textContent);
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const change = (selector, value, event = 'change') => {
    $(selector).value = value;
    $(selector).dispatchEvent(new Event(event, { bubbles: true }));
  };
  // Two animation frames allow scroll anchoring/layout to settle without
  // timing-dependent sleeps. The test page should remain in an active tab.
  const settle = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const check = async (name, run) => { await run(); results.push(`PASS: ${name}`); };

  try {
    // Reload can otherwise restore a previous scroll offset during assertions.
    // Disable history restoration only in this disposable test document and
    // wait for load/layout before exercising the application's scrolling.
    history.scrollRestoration = 'manual';
    if (document.readyState !== 'complete') {
      await new Promise(resolve => window.addEventListener('load', resolve, { once: true }));
    }
    await settle();
    $('#btn-table').click();
    change('#per-page', '10');

    await check('Initial natural name ordering and page boundaries', () => {
      assert(names().join(',') === Array.from({ length: 10 }, (_, i) => `Project ${i}`).join(','), 'Incorrect initial names');
      assert($('#page-info').textContent === 'Showing 1-10 of 61 projects', 'Incorrect page count');
      assert($('#pagination button[aria-label="Previous page"]').disabled, 'Previous must be disabled');
      assert(![...document.querySelectorAll('th button')].some(button => button.textContent.includes('Description')), 'Description is sortable');
    });

    await check('Name descending sorts the full dataset, then toggles back', () => {
      $('[data-sort="name"]').click();
      assert(names()[0] === 'Project 60' && names()[9] === 'Project 51', 'Only the current page was sorted');
      assert($('[data-sort="name"]').closest('th').getAttribute('aria-sort') === 'descending', 'Missing accessible direction');
      $('[data-sort="name"]').click();
      assert(names()[0] === 'Project 0', 'Name ascending did not return');
    });

    await check('Path sorting works in both directions and resets pagination', () => {
      $('#pagination button[aria-label="Next page"]').click();
      $('[data-sort="path"]').click();
      assert(paths()[0] === 'group/0/project' && names()[0] === 'Project 60', 'Path ascending is incorrect');
      assert($('#page-info').textContent === 'Showing 1-10 of 61 projects', 'Sorting did not reset page');
      $('[data-sort="path"]').click();
      assert(paths()[0] === 'group/60/project' && names()[0] === 'Project 0', 'Path descending is incorrect');
    });

    await check('All remote status filters agree between cards and table', () => {
      const states = ['ahead', 'behind', 'up_to_date', 'diverged', 'no_remote', 'not_repo', 'detached', 'error'];
      for (const state of states) {
        change('#status-filter', state);
        const expected = state === 'not_repo' || state === 'detached' || state === 'error' ? 7 : 8;
        assert(visibleRows().length === expected, `Wrong count for ${state}`);
        assert(visibleRows().every(row => row.dataset.status === state), `Filter leaked another status: ${state}`);
        $('#btn-cards').click();
        const cards = [...document.querySelectorAll('.project-card:not(.hidden)')];
        assert(cards.map(card => card.querySelector('h2').textContent).join(',') === names().join(','), 'Views disagree');
        assert(!$('#projects-cards').classList.contains('hidden'), 'Cards are not shown');
        $('#btn-table').click();
      }
    });

    await check('Remote status sorting compares commit counts numerically', () => {
      change('#status-filter', 'ahead');
      $('[data-sort="status"]').click();
      assert(names().join(',') === 'Project 0,Project 8,Project 16,Project 24,Project 32,Project 40,Project 48,Project 56', 'Ahead counts are not naturally sorted');
      $('[data-sort="status"]').click();
      assert(names()[0] === 'Project 56', 'Status descending failed');
      change('#status-filter', '');
      change('#per-page', 'all');
      const descending = paths();
      $('[data-sort="status"]').click();
      assert(paths().join(',') === descending.reverse().join(','), 'Status toggle does not reverse complete order');
    });

    await check('Search combines with status, handles no matches, and recovers', () => {
      change('#status-filter', 'ahead');
      change('#search', '  PROJECT 16  ', 'input');
      assert(names().join(',') === 'Project 16', 'Search/status conjunction failed');
      assert($('#results-count').textContent === 'Found 1 of 61 projects', 'Filtered result count failed');
      change('#search', 'nothing-matches', 'input');
      assert(names().length === 0 && !$('#no-results').hidden, 'No-results state is missing');
      assert(!$('#pagination').children.length, 'Empty results still have page buttons');
      change('#search', 'group/44/project', 'input');
      assert(names().join(',') === 'Project 16', 'Path search failed');
      change('#search', '', 'input');
      change('#status-filter', '');
      assert(names().length === 61 && $('#no-results').hidden, 'Clearing filters failed');
    });

    await check('Filtering from a later page resets to the first page', () => {
      change('#per-page', '10');
      $('#pagination button[aria-label="Next page"]').click();
      change('#status-filter', 'behind');
      assert($('#page-info').textContent === 'Showing 1-8 of 8 projects', 'Status filtering retained a later page');
      change('#status-filter', '');
    });

    await check('Select keyboard events do not trigger global pagination', () => {
      for (const selector of ['#status-filter', '#per-page']) {
        $(selector).focus();
        $(selector).dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
        assert($('#page-info').textContent === 'Showing 1-10 of 61 projects', 'Select arrow key changed pages');
      }
    });

    for (const view of ['cards', 'table']) {
      await check(`${view}: pagination keeps controls in view across unequal and short pages`, async () => {
        $(`#btn-${view}`).click();
        change('#per-page', '25');
        const controls = $('#pagination-container');
        controls.scrollIntoView({ block: 'center' });
        await settle();
        const initialTop = controls.getBoundingClientRect().top;
        assert(window.scrollY > 0, 'Fixture is not tall enough to test scrolling');
        $('#pagination button[aria-label="Next page"]').click();
        await settle();
        assert(Math.abs(controls.getBoundingClientRect().top - initialTop) < 3, 'Controls moved after changing page');
        assert(window.scrollY > 0, 'Pagination jumped to top');
        assert(document.activeElement.getAttribute('aria-current') === 'page', 'Pagination lost keyboard focus');
        $('#pagination button[aria-label="Next page"]').click();
        await settle();
        assert(visibleRows().length === 11, 'Last page should have 11 entries');
        assert(Math.abs(controls.getBoundingClientRect().top - initialTop) < 3, 'Short last page moved controls');
        assert($('#pagination button[aria-label="Next page"]').disabled, 'Next must be disabled on last page');
        $('#pagination button[aria-label="Previous page"]').click();
        await settle();
        assert(Math.abs(controls.getBoundingClientRect().top - initialTop) < 3, 'Returning from short page moved controls');
      });
    }

    await check('All shows every result and removes pagination', () => {
      change('#per-page', 'all');
      assert(visibleRows().length === 61, 'All did not show every project');
      assert($('#page-info').textContent === 'Showing all 61 projects', 'All count is incorrect');
      assert(!$('#pagination').children.length, 'All retained pagination');
    });
  } catch (error) {
    results.push(`FAIL: ${error.message}`);
    console.error(error);
  }

  const report = document.createElement('pre');
  report.id = 'browser-test-results';
  report.setAttribute('role', 'status');
  report.style.cssText = 'padding: 24px; white-space: pre-wrap;';
  report.textContent = results.join('\n');
  document.body.prepend(report);
  window.scrollTo(0, 0);
})();
