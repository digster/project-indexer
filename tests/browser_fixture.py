"""Build disposable pages for real-browser checks without runtime dependencies.

Run from the repository root with:
    uv run python -m tests.browser_fixture /tmp/project-indexer-ui
Then serve that directory and open checks.html or index.html.
"""

import argparse
from pathlib import Path

from project_indexer import generate_html


def build_fixtures(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    states = [
        'ahead', 'behind', 'up_to_date', 'diverged', 'no_remote',
        'not_repo', 'detached', 'error',
    ]
    # Reversed paths distinguish path sorting from name sorting; unpadded
    # numbers and repeated status labels exercise natural numeric ordering.
    cache = {
        f'group/{60 - i}/project': {
            'name': f'Project {i}',
            'summary': ('Searchable fixture. ' * (1 + i % 8)),
            'git': {'state': states[i % len(states)], 'ahead': i + 1, 'behind': i + 1},
        }
        for i in range(61)
    }
    content = generate_html(cache, 'Project Index UI Test', output)
    (output / 'index.html').write_text(content, encoding='utf-8')
    (output / 'empty.html').write_text(generate_html({}, 'Empty Index', output), encoding='utf-8')
    # The test runner exercises the generated document itself, including real
    # layout/scrolling. It is added only to this disposable test artifact.
    script = Path(__file__).with_name('browser_checks.js').read_text(encoding='utf-8')
    checks = content.replace('</body>', f'<script>{script}</script></body>')
    (output / 'checks.html').write_text(checks, encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    build_fixtures(parser.parse_args().output)
