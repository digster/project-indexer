"""Validate the generated HTML's shared data and accessible control contract.

Parse the actual output with the standard library so escaping bugs cannot pass
by merely matching a fragment of the template source. Browser interaction
checks complement these tests; see tests/BROWSER_CHECKS.md.
"""

from html.parser import HTMLParser
from pathlib import Path

import pytest

from project_indexer import generate_html


class IndexParser(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.elements = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def find(self, tag, **attrs):
        return [
            element for kind, element in self.elements
            if kind == tag and all(element.get(key) == value for key, value in attrs.items())
        ]


@pytest.mark.parametrize('state', [
    'up_to_date', 'ahead', 'behind', 'diverged', 'no_remote',
    'detached', 'not_repo', 'error',
])
def test_filter_covers_every_status_in_both_views(state):
    page = IndexParser(generate_html({
        'nested/project': {'name': 'Project', 'git': {'state': state, 'ahead': 12}},
    }, 'Index', Path('.')))
    cards = page.find('article', **{'class': 'project-card'})
    rows = page.find('tr', **{'class': 'project-row'})
    assert len(cards) == len(rows) == 1
    assert cards[0]['data-status'] == rows[0]['data-status'] == state
    assert page.find('option', value=state)
    assert page.find('label', **{'for': 'status-filter'})


def test_sorting_controls_exclude_description_and_announce_default_order():
    page = IndexParser(generate_html({}, 'Index', Path('.')))
    buttons = [attrs for tag, attrs in page.elements if tag == 'button' and 'data-sort' in attrs]
    assert {button['data-sort'] for button in buttons} == {'name', 'path', 'status'}
    assert len(page.find('th', **{'scope': 'col'})) == 4
    assert len(page.find('th', **{'aria-sort': 'ascending'})) == 1


def test_search_sort_and_filter_metadata_survives_html_escaping():
    path = 'team/"A&B"/<project>'
    name = 'Project "A&B" <demo>'
    summary = '<script>alert("test")</script> & details'
    page = IndexParser(generate_html({path: {'name': name, 'summary': summary}}, 'Index', Path('.')))
    card = page.find('article', **{'class': 'project-card'})[0]
    row = page.find('tr', **{'class': 'project-row'})[0]
    for field in ('data-name', 'data-summary', 'data-path', 'data-status', 'data-status-label'):
        assert card[field] == row[field]
    assert card['data-name'] == name.lower()
    assert card['data-summary'] == summary.lower()
    assert card['data-path'] == path
    assert card['data-status'] == 'not_repo'
    assert len(page.find('script')) == 1  # Only the indexer's own script is executable.


def test_empty_index_has_no_phantom_projects_and_retains_controls():
    page = IndexParser(generate_html({}, 'Empty', Path('.')))
    assert not page.find('article', **{'class': 'project-card'})
    assert not page.find('tr', **{'class': 'project-row'})
    assert page.find('select', id='status-filter')
    assert page.find('nav', **{'aria-label': 'Project pages'})
    assert page.find('div', id='results-count', role='status')
