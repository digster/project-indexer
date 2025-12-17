#!/usr/bin/env python3
"""
Project README Indexer
======================

A dependency-free Python script that scans subfolders for README files,
extracts project names and summaries, and generates an incremental index.html.

Usage:
    python3 project_indexer.py [OPTIONS]

Options:
    --root PATH         Root directory to scan (default: current directory)
    --output PATH       Output HTML file path (default: index.html in root)
    --cache PATH        Cache file path (default: .project_index_cache.json in root)
    --title STRING      Title for the index page (default: "Project Index")
    --exclude DIRNAME   Directory names to exclude (repeatable; has sensible defaults)

Examples:
    # Index current directory
    python3 project_indexer.py

    # Index a specific directory with custom title
    python3 project_indexer.py --root ~/projects --title "My Projects"

    # Exclude additional directories
    python3 project_indexer.py --exclude dist --exclude build

Incremental Behavior:
    - On first run, scans all projects and creates cache + index.html
    - On subsequent runs:
      - Adds new projects found
      - Updates entries whose README file changed (mtime/size)
      - Removes entries for projects that no longer exist
"""

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Default directories to exclude from scanning
DEFAULT_EXCLUDES = {
    '.git', '.svn', '.hg',
    'node_modules', 'bower_components',
    '.venv', 'venv', 'env', '.env',
    '__pycache__', '.pytest_cache', '.mypy_cache',
    '.tox', '.nox',
    'dist', 'build', 'target', 'out',
    '.idea', '.vscode',
    'vendor',
}

# README filename patterns (case-insensitive matching)
README_PATTERNS = [
    'readme.md',
    'readme.markdown',
    'readme.rst',
    'readme.txt',
    'readme',
]


def find_readme(directory: Path) -> Optional[Path]:
    """
    Find the best README file in a directory.
    
    Priority:
    1. README.md (case-insensitive)
    2. Other README variants by preference order
    3. Shortest filename as tie-breaker
    """
    candidates = []
    
    try:
        for entry in directory.iterdir():
            if entry.is_file():
                name_lower = entry.name.lower()
                if name_lower.startswith('readme'):
                    candidates.append(entry)
    except PermissionError:
        return None
    
    if not candidates:
        return None
    
    # Sort by preference
    def sort_key(p: Path) -> tuple:
        name_lower = p.name.lower()
        # Priority index based on patterns
        for i, pattern in enumerate(README_PATTERNS):
            if name_lower == pattern:
                return (i, len(p.name), p.name.lower())
        return (len(README_PATTERNS), len(p.name), p.name.lower())
    
    candidates.sort(key=sort_key)
    return candidates[0]


def extract_name_and_summary(readme_path: Path, folder_name: str) -> tuple[str, str]:
    """
    Extract project name and summary from a README file.
    
    Name extraction:
    - Prefer Markdown H1 (# Title) or underline-style title
    - Fallback to folder name
    
    Summary extraction:
    - Prefer first paragraph under Summary/Description/Overview/About heading
    - Fallback to first non-empty paragraph after title
    """
    try:
        content = readme_path.read_text(encoding='utf-8', errors='replace')
    except (OSError, IOError):
        return folder_name, ""
    
    lines = content.split('\n')
    
    # Remove code blocks for parsing
    in_code_block = False
    filtered_lines = []
    for line in lines:
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            filtered_lines.append(line)
    
    # Extract name
    name = folder_name
    title_line_idx = -1
    
    for i, line in enumerate(filtered_lines):
        stripped = line.strip()
        # Markdown H1: # Title
        if stripped.startswith('# '):
            name = stripped[2:].strip()
            # Remove any trailing badges or links
            name = re.sub(r'\s*\[!\[.*?\]\(.*?\)\]\(.*?\)', '', name)
            name = re.sub(r'\s*!\[.*?\]\(.*?\)', '', name)
            name = name.strip()
            title_line_idx = i
            break
        # Underline-style title (next line is === or ---)
        if i + 1 < len(filtered_lines):
            next_line = filtered_lines[i + 1].strip()
            if next_line and (all(c == '=' for c in next_line) or all(c == '-' for c in next_line)):
                if stripped and not stripped.startswith('#'):
                    name = stripped
                    title_line_idx = i + 1
                    break
    
    # Extract summary
    summary = ""
    
    # Look for explicit summary/description/overview/about section
    summary_headings = ['summary', 'description', 'overview', 'about']
    section_content = []
    in_target_section = False
    
    for i, line in enumerate(filtered_lines):
        stripped = line.strip().lower()
        
        # Check for heading
        is_heading = False
        heading_text = ""
        
        if stripped.startswith('#'):
            is_heading = True
            heading_text = re.sub(r'^#+\s*', '', stripped)
        elif i + 1 < len(filtered_lines):
            next_line = filtered_lines[i + 1].strip()
            if next_line and (all(c == '=' for c in next_line) or all(c == '-' for c in next_line)):
                is_heading = True
                heading_text = stripped
        
        if is_heading:
            if in_target_section and section_content:
                # End of target section, we have content
                break
            # Check if this is a target heading
            if any(h in heading_text for h in summary_headings):
                in_target_section = True
                section_content = []
            else:
                in_target_section = False
        elif in_target_section:
            section_content.append(line)
    
    if section_content:
        # Get first paragraph from section
        summary = extract_first_paragraph(section_content)
    
    # Fallback: first paragraph after title
    if not summary:
        start_idx = title_line_idx + 1 if title_line_idx >= 0 else 0
        remaining_lines = filtered_lines[start_idx:]
        summary = extract_first_paragraph(remaining_lines)
    
    # Clean up summary
    summary = clean_text(summary)
    
    # Truncate if too long
    if len(summary) > 500:
        summary = summary[:497] + "..."
    
    return name, summary


def extract_first_paragraph(lines: list[str]) -> str:
    """Extract the first non-empty paragraph from lines."""
    paragraph_lines = []
    started = False
    
    for line in lines:
        stripped = line.strip()
        
        # Skip badges, images, and links-only lines
        if re.match(r'^\[?!\[', stripped):
            continue
        if re.match(r'^\[.*\]\(.*\)$', stripped):
            continue
        # Skip horizontal rules
        if re.match(r'^[-*_]{3,}$', stripped):
            continue
        # Skip table lines
        if stripped.startswith('|') or re.match(r'^[-:|]+$', stripped):
            continue
        # Skip HTML comments
        if stripped.startswith('<!--'):
            continue
        
        if stripped:
            started = True
            paragraph_lines.append(stripped)
        elif started and paragraph_lines:
            # End of paragraph
            break
    
    return ' '.join(paragraph_lines)


def clean_text(text: str) -> str:
    """Clean markdown formatting from text."""
    # Remove inline code
    text = re.sub(r'`[^`]+`', '', text)
    # Remove bold/italic
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    # Remove links but keep text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove images
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def discover_projects(root: Path, excludes: set[str]) -> dict[str, Path]:
    """
    Discover all projects (directories with README files) under root.
    
    Returns dict mapping relative project path to README file path.
    """
    projects = {}
    
    for dirpath, dirnames, filenames in os.walk(root):
        # Filter out excluded directories
        dirnames[:] = [d for d in dirnames if d not in excludes and not d.startswith('.')]
        
        current_dir = Path(dirpath)
        readme = find_readme(current_dir)
        
        if readme:
            # Get relative path from root
            try:
                rel_path = current_dir.relative_to(root)
                if str(rel_path) == '.':
                    continue  # Skip root directory itself
                projects[str(rel_path)] = readme
            except ValueError:
                continue
    
    return projects


def load_cache(cache_path: Path) -> dict:
    """Load the cache file, returning empty dict if not found or invalid."""
    if not cache_path.exists():
        return {}
    
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError):
        pass
    
    return {}


def save_cache(cache_path: Path, cache: dict) -> None:
    """Save the cache to file."""
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def needs_update(readme_path: Path, cached_entry: dict) -> bool:
    """Check if a README file has changed since caching."""
    try:
        stat = readme_path.stat()
        cached_mtime = cached_entry.get('readme_mtime', 0)
        cached_size = cached_entry.get('readme_size', -1)
        
        return stat.st_mtime != cached_mtime or stat.st_size != cached_size
    except OSError:
        return True


def process_project(project_path: str, readme_path: Path, root: Path) -> dict:
    """Process a single project and return cache entry."""
    folder_name = Path(project_path).name
    name, summary = extract_name_and_summary(readme_path, folder_name)
    
    stat = readme_path.stat()
    
    return {
        'readme_path': str(readme_path.relative_to(root)),
        'readme_mtime': stat.st_mtime,
        'readme_size': stat.st_size,
        'name': name,
        'summary': summary,
    }


def generate_html(cache: dict, title: str, root: Path) -> str:
    """Generate the index.html content from cache data."""
    # Sort projects alphabetically by name (case-insensitive)
    sorted_projects = sorted(
        cache.items(),
        key=lambda x: (x[1].get('name', x[0]).lower(), x[0])
    )
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    project_count = len(sorted_projects)
    
    # Generate project cards HTML
    cards_html = []
    table_rows_html = []
    
    for project_path, data in sorted_projects:
        name = html.escape(data.get('name', project_path))
        summary = html.escape(data.get('summary', ''))
        path_escaped = html.escape(project_path)
        
        # Card view
        card = f'''    <article class="project-card" data-name="{name.lower()}" data-summary="{summary.lower()}">
      <h2><a href="{path_escaped}">{name}</a></h2>
      <p class="summary">{summary if summary else '<em>No description available</em>'}</p>
      <p class="path">{path_escaped}</p>
    </article>'''
        cards_html.append(card)
        
        # Table row
        row = f'''      <tr class="project-row" data-name="{name.lower()}" data-summary="{summary.lower()}">
        <td class="col-name"><a href="{path_escaped}">{name}</a></td>
        <td class="col-summary">{summary if summary else '<em>No description</em>'}</td>
        <td class="col-path">{path_escaped}</td>
      </tr>'''
        table_rows_html.append(row)
    
    cards_content = '\n'.join(cards_html) if cards_html else '    <p class="no-projects">No projects found.</p>'
    table_rows_content = '\n'.join(table_rows_html) if table_rows_html else '''      <tr><td colspan="3" class="no-projects">No projects found.</td></tr>'''
    
    html_template = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg-primary: #0d1117;
      --bg-secondary: #161b22;
      --bg-tertiary: #21262d;
      --text-primary: #e6edf3;
      --text-secondary: #8b949e;
      --text-muted: #6e7681;
      --accent: #58a6ff;
      --accent-hover: #79b8ff;
      --border: #30363d;
      --card-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    }}
    
    @media (prefers-color-scheme: light) {{
      :root {{
        --bg-primary: #f6f8fa;
        --bg-secondary: #ffffff;
        --bg-tertiary: #f0f3f6;
        --text-primary: #1f2328;
        --text-secondary: #656d76;
        --text-muted: #8c959f;
        --accent: #0969da;
        --accent-hover: #0550ae;
        --border: #d0d7de;
        --card-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
      }}
    }}
    
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif;
      background: var(--bg-primary);
      color: var(--text-primary);
      line-height: 1.6;
      min-height: 100vh;
    }}
    
    .container {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 2rem 1.5rem;
    }}
    
    header {{
      margin-bottom: 2rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--border);
    }}
    
    h1 {{
      font-size: 2rem;
      font-weight: 600;
      margin-bottom: 0.5rem;
      letter-spacing: -0.02em;
    }}
    
    .meta {{
      display: flex;
      gap: 1.5rem;
      font-size: 0.875rem;
      color: var(--text-secondary);
      flex-wrap: wrap;
    }}
    
    .toolbar {{
      display: flex;
      gap: 1rem;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 1.5rem;
    }}
    
    #search {{
      flex: 1;
      min-width: 200px;
      max-width: 400px;
      padding: 0.75rem 1rem;
      font-size: 1rem;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--bg-secondary);
      color: var(--text-primary);
      transition: border-color 0.15s ease;
    }}
    
    #search:focus {{
      outline: none;
      border-color: var(--accent);
    }}
    
    #search::placeholder {{
      color: var(--text-muted);
    }}
    
    .view-toggle {{
      display: flex;
      border: 1px solid var(--border);
      border-radius: 6px;
      overflow: hidden;
    }}
    
    .view-toggle button {{
      padding: 0.5rem 0.75rem;
      border: none;
      background: var(--bg-secondary);
      color: var(--text-secondary);
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.375rem;
      font-size: 0.875rem;
      transition: background 0.15s ease, color 0.15s ease;
    }}
    
    .view-toggle button:not(:last-child) {{
      border-right: 1px solid var(--border);
    }}
    
    .view-toggle button:hover {{
      background: var(--bg-tertiary);
    }}
    
    .view-toggle button.active {{
      background: var(--accent);
      color: #fff;
    }}
    
    .view-toggle svg {{
      width: 16px;
      height: 16px;
    }}
    
    /* Card View */
    .projects-cards {{
      display: grid;
      gap: 1rem;
    }}
    
    .projects-cards.hidden {{
      display: none;
    }}
    
    .project-card {{
      background: var(--bg-secondary);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1.25rem 1.5rem;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }}
    
    .project-card:hover {{
      border-color: var(--accent);
      box-shadow: var(--card-shadow);
    }}
    
    .project-card.hidden {{
      display: none;
    }}
    
    .project-card h2 {{
      font-size: 1.125rem;
      font-weight: 600;
      margin-bottom: 0.5rem;
    }}
    
    .project-card h2 a {{
      color: var(--accent);
      text-decoration: none;
    }}
    
    .project-card h2 a:hover {{
      color: var(--accent-hover);
      text-decoration: underline;
    }}
    
    .project-card .summary {{
      color: var(--text-secondary);
      font-size: 0.9375rem;
      margin-bottom: 0.75rem;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    
    .project-card .summary em {{
      color: var(--text-muted);
    }}
    
    .project-card .path {{
      font-size: 0.8125rem;
      color: var(--text-muted);
      font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
    }}
    
    /* Table View */
    .projects-table-wrapper {{
      overflow-x: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--bg-secondary);
    }}
    
    .projects-table-wrapper.hidden {{
      display: none;
    }}
    
    .projects-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9375rem;
    }}
    
    .projects-table th,
    .projects-table td {{
      padding: 0.75rem 1rem;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }}
    
    .projects-table th {{
      background: var(--bg-tertiary);
      font-weight: 600;
      font-size: 0.8125rem;
      text-transform: uppercase;
      letter-spacing: 0.025em;
      color: var(--text-secondary);
      position: sticky;
      top: 0;
    }}
    
    .projects-table tbody tr:last-child td {{
      border-bottom: none;
    }}
    
    .projects-table tbody tr:hover {{
      background: var(--bg-tertiary);
    }}
    
    .projects-table tbody tr.hidden {{
      display: none;
    }}
    
    .projects-table .col-name {{
      width: 20%;
      min-width: 150px;
      font-weight: 500;
    }}
    
    .projects-table .col-name a {{
      color: var(--accent);
      text-decoration: none;
    }}
    
    .projects-table .col-name a:hover {{
      color: var(--accent-hover);
      text-decoration: underline;
    }}
    
    .projects-table .col-summary {{
      color: var(--text-secondary);
      max-width: 500px;
    }}
    
    .projects-table .col-summary em {{
      color: var(--text-muted);
    }}
    
    .projects-table .col-path {{
      width: 25%;
      min-width: 150px;
      font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
      font-size: 0.8125rem;
      color: var(--text-muted);
    }}
    
    .no-projects {{
      text-align: center;
      color: var(--text-secondary);
      padding: 3rem 1rem;
      font-size: 1.125rem;
    }}
    
    .results-count {{
      font-size: 0.875rem;
      color: var(--text-muted);
      margin-bottom: 1rem;
    }}
    
    /* Pagination */
    .pagination-container {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
      margin-top: 1.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border);
    }}
    
    .per-page {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.875rem;
      color: var(--text-secondary);
    }}
    
    .per-page select {{
      padding: 0.375rem 0.625rem;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--bg-secondary);
      color: var(--text-primary);
      font-size: 0.875rem;
      cursor: pointer;
    }}
    
    .per-page select:focus {{
      outline: none;
      border-color: var(--accent);
    }}
    
    .pagination {{
      display: flex;
      align-items: center;
      gap: 0.25rem;
    }}
    
    .pagination button {{
      min-width: 2rem;
      height: 2rem;
      padding: 0 0.5rem;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--bg-secondary);
      color: var(--text-secondary);
      font-size: 0.875rem;
      cursor: pointer;
      transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
    }}
    
    .pagination button:hover:not(:disabled) {{
      background: var(--bg-tertiary);
      border-color: var(--accent);
    }}
    
    .pagination button.active {{
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }}
    
    .pagination button:disabled {{
      opacity: 0.4;
      cursor: not-allowed;
    }}
    
    .pagination .ellipsis {{
      padding: 0 0.375rem;
      color: var(--text-muted);
    }}
    
    .page-info {{
      font-size: 0.875rem;
      color: var(--text-muted);
    }}
    
    footer {{
      margin-top: 3rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border);
      text-align: center;
      color: var(--text-muted);
      font-size: 0.8125rem;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>{html.escape(title)}</h1>
      <div class="meta">
        <span>{project_count} project{"s" if project_count != 1 else ""}</span>
        <span>Last updated: {timestamp}</span>
      </div>
    </header>
    
    <div class="toolbar">
      <input type="text" id="search" placeholder="Search projects..." autocomplete="off">
      <div class="view-toggle">
        <button id="btn-cards" class="active" title="Card view">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7" rx="1"/>
            <rect x="14" y="3" width="7" height="7" rx="1"/>
            <rect x="3" y="14" width="7" height="7" rx="1"/>
            <rect x="14" y="14" width="7" height="7" rx="1"/>
          </svg>
          Cards
        </button>
        <button id="btn-table" title="Table view">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="3" y1="6" x2="21" y2="6"/>
            <line x1="3" y1="12" x2="21" y2="12"/>
            <line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
          Table
        </button>
      </div>
    </div>
    
    <div id="results-count" class="results-count"></div>
    
    <section class="projects-cards" id="projects-cards">
{cards_content}
    </section>
    
    <div class="projects-table-wrapper hidden" id="projects-table-wrapper">
      <table class="projects-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Description</th>
            <th>Path</th>
          </tr>
        </thead>
        <tbody id="projects-table">
{table_rows_content}
        </tbody>
      </table>
    </div>
    
    <div class="pagination-container" id="pagination-container">
      <div class="per-page">
        <label for="per-page">Show</label>
        <select id="per-page">
          <option value="10">10</option>
          <option value="25" selected>25</option>
          <option value="50">50</option>
          <option value="100">100</option>
          <option value="all">All</option>
        </select>
        <span>per page</span>
      </div>
      <div class="page-info" id="page-info"></div>
      <nav class="pagination" id="pagination"></nav>
    </div>
    
    <footer>
      Generated by Project README Indexer
    </footer>
  </div>
  
  <script>
    (function() {{
      // Elements
      const search = document.getElementById('search');
      const cardsContainer = document.getElementById('projects-cards');
      const tableWrapper = document.getElementById('projects-table-wrapper');
      const tableBody = document.getElementById('projects-table');
      const cards = Array.from(cardsContainer.querySelectorAll('.project-card'));
      const rows = Array.from(tableBody.querySelectorAll('.project-row'));
      const resultsCount = document.getElementById('results-count');
      const btnCards = document.getElementById('btn-cards');
      const btnTable = document.getElementById('btn-table');
      const perPageSelect = document.getElementById('per-page');
      const paginationNav = document.getElementById('pagination');
      const pageInfo = document.getElementById('page-info');
      const paginationContainer = document.getElementById('pagination-container');
      
      const totalCount = cards.length;
      
      // State
      let currentView = localStorage.getItem('projectIndexView') || 'cards';
      let perPage = parseInt(localStorage.getItem('projectIndexPerPage')) || 25;
      let currentPage = 1;
      let filteredCards = [...cards];
      let filteredRows = [...rows];
      
      // Initialize per-page select
      if (perPage === Infinity || perPage > 100) {{
        perPageSelect.value = 'all';
        perPage = Infinity;
      }} else {{
        perPageSelect.value = perPage.toString();
      }}
      
      // View toggle
      function setView(view) {{
        currentView = view;
        localStorage.setItem('projectIndexView', view);
        
        if (view === 'cards') {{
          cardsContainer.classList.remove('hidden');
          tableWrapper.classList.add('hidden');
          btnCards.classList.add('active');
          btnTable.classList.remove('active');
        }} else {{
          cardsContainer.classList.add('hidden');
          tableWrapper.classList.remove('hidden');
          btnCards.classList.remove('active');
          btnTable.classList.add('active');
        }}
      }}
      
      btnCards.addEventListener('click', () => setView('cards'));
      btnTable.addEventListener('click', () => setView('table'));
      setView(currentView);
      
      // Filter items based on search
      function filterItems() {{
        const query = search.value.toLowerCase().trim();
        
        filteredCards = cards.filter(card => {{
          const name = card.dataset.name || '';
          const summary = card.dataset.summary || '';
          const path = card.querySelector('.path')?.textContent?.toLowerCase() || '';
          return !query || name.includes(query) || summary.includes(query) || path.includes(query);
        }});
        
        filteredRows = rows.filter(row => {{
          const name = row.dataset.name || '';
          const summary = row.dataset.summary || '';
          const path = row.querySelector('.col-path')?.textContent?.toLowerCase() || '';
          return !query || name.includes(query) || summary.includes(query) || path.includes(query);
        }});
      }}
      
      // Calculate pagination
      function getTotalPages() {{
        if (perPage === Infinity) return 1;
        return Math.max(1, Math.ceil(filteredCards.length / perPage));
      }}
      
      // Render pagination controls
      function renderPagination() {{
        const total = filteredCards.length;
        const totalPages = getTotalPages();
        
        // Hide pagination if no items or showing all
        if (total === 0 || perPage === Infinity) {{
          paginationNav.innerHTML = '';
          pageInfo.textContent = total > 0 ? `Showing all ${{total}} projects` : '';
          return;
        }}
        
        const start = (currentPage - 1) * perPage + 1;
        const end = Math.min(currentPage * perPage, total);
        pageInfo.textContent = `Showing ${{start}}-${{end}} of ${{total}} projects`;
        
        let html = '';
        
        // Previous button
        html += `<button ${{currentPage === 1 ? 'disabled' : ''}} data-page="${{currentPage - 1}}">&laquo;</button>`;
        
        // Page numbers
        const maxVisible = 5;
        let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
        let endPage = Math.min(totalPages, startPage + maxVisible - 1);
        
        if (endPage - startPage < maxVisible - 1) {{
          startPage = Math.max(1, endPage - maxVisible + 1);
        }}
        
        if (startPage > 1) {{
          html += `<button data-page="1">1</button>`;
          if (startPage > 2) html += `<span class="ellipsis">...</span>`;
        }}
        
        for (let i = startPage; i <= endPage; i++) {{
          html += `<button class="${{i === currentPage ? 'active' : ''}}" data-page="${{i}}">${{i}}</button>`;
        }}
        
        if (endPage < totalPages) {{
          if (endPage < totalPages - 1) html += `<span class="ellipsis">...</span>`;
          html += `<button data-page="${{totalPages}}">${{totalPages}}</button>`;
        }}
        
        // Next button
        html += `<button ${{currentPage === totalPages ? 'disabled' : ''}} data-page="${{currentPage + 1}}">&raquo;</button>`;
        
        paginationNav.innerHTML = html;
      }}
      
      // Show items for current page
      function showPage() {{
        const start = perPage === Infinity ? 0 : (currentPage - 1) * perPage;
        const end = perPage === Infinity ? filteredCards.length : start + perPage;
        
        // Hide all first
        cards.forEach(c => c.classList.add('hidden'));
        rows.forEach(r => r.classList.add('hidden'));
        
        // Show filtered items for current page
        filteredCards.slice(start, end).forEach(c => c.classList.remove('hidden'));
        filteredRows.slice(start, end).forEach(r => r.classList.remove('hidden'));
      }}
      
      // Update display
      function updateDisplay() {{
        filterItems();
        
        // Clamp current page
        const totalPages = getTotalPages();
        if (currentPage > totalPages) currentPage = totalPages;
        if (currentPage < 1) currentPage = 1;
        
        showPage();
        renderPagination();
        
        // Update results count for search
        const query = search.value.trim();
        if (query) {{
          resultsCount.textContent = `Found ${{filteredCards.length}} of ${{totalCount}} projects`;
        }} else {{
          resultsCount.textContent = '';
        }}
      }}
      
      // Event listeners
      search.addEventListener('input', () => {{
        currentPage = 1;
        updateDisplay();
      }});
      
      perPageSelect.addEventListener('change', (e) => {{
        const val = e.target.value;
        if (val === 'all') {{
          perPage = Infinity;
          localStorage.setItem('projectIndexPerPage', 'all');
        }} else {{
          perPage = parseInt(val);
          localStorage.setItem('projectIndexPerPage', perPage);
        }}
        currentPage = 1;
        updateDisplay();
      }});
      
      paginationNav.addEventListener('click', (e) => {{
        const btn = e.target.closest('button');
        if (btn && !btn.disabled) {{
          currentPage = parseInt(btn.dataset.page);
          updateDisplay();
          window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}
      }});
      
      // Keyboard shortcuts
      document.addEventListener('keydown', e => {{
        if (e.key === '/' && document.activeElement !== search) {{
          e.preventDefault();
          search.focus();
        }}
        // Arrow keys for pagination (when not in search)
        if (document.activeElement !== search) {{
          if (e.key === 'ArrowLeft' && currentPage > 1) {{
            currentPage--;
            updateDisplay();
          }} else if (e.key === 'ArrowRight' && currentPage < getTotalPages()) {{
            currentPage++;
            updateDisplay();
          }}
        }}
      }});
      
      // Initial render
      updateDisplay();
    }})();
  </script>
</body>
</html>
'''
    
    return html_template


def main():
    parser = argparse.ArgumentParser(
        description='Index projects with README files into an HTML page.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s                          # Index current directory
  %(prog)s --root ~/projects        # Index specific directory
  %(prog)s --title "My Projects"    # Custom page title
  %(prog)s --exclude dist build     # Exclude additional directories
        '''
    )
    
    parser.add_argument(
        '--root', '-r',
        type=Path,
        default=Path('.'),
        help='Root directory to scan (default: current directory)'
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=None,
        help='Output HTML file path (default: index.html in root)'
    )
    parser.add_argument(
        '--cache', '-c',
        type=Path,
        default=None,
        help='Cache file path (default: .project_index_cache.json in root)'
    )
    parser.add_argument(
        '--title', '-t',
        type=str,
        default='Project Index',
        help='Title for the index page (default: "Project Index")'
    )
    parser.add_argument(
        '--exclude', '-e',
        action='append',
        default=[],
        metavar='DIRNAME',
        help='Additional directory names to exclude (can be used multiple times)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print verbose output'
    )
    
    args = parser.parse_args()
    
    # Resolve paths
    root = args.root.resolve()
    output_path = args.output if args.output else root / 'index.html'
    cache_path = args.cache if args.cache else root / '.project_index_cache.json'
    
    # Build exclude set
    excludes = DEFAULT_EXCLUDES.copy()
    excludes.update(args.exclude)
    
    if not root.is_dir():
        print(f"Error: Root directory does not exist: {root}", file=sys.stderr)
        sys.exit(1)
    
    if args.verbose:
        print(f"Scanning: {root}")
        print(f"Output: {output_path}")
        print(f"Cache: {cache_path}")
    
    # Load existing cache
    cache = load_cache(cache_path)
    
    # Discover projects
    discovered = discover_projects(root, excludes)
    
    if args.verbose:
        print(f"Found {len(discovered)} projects with README files")
    
    # Track changes
    added = 0
    updated = 0
    removed = 0
    
    # Process new and updated projects
    new_cache = {}
    for project_path, readme_path in discovered.items():
        if project_path in cache:
            cached_entry = cache[project_path]
            if needs_update(readme_path, cached_entry):
                new_cache[project_path] = process_project(project_path, readme_path, root)
                updated += 1
                if args.verbose:
                    print(f"  Updated: {project_path}")
            else:
                new_cache[project_path] = cached_entry
        else:
            new_cache[project_path] = process_project(project_path, readme_path, root)
            added += 1
            if args.verbose:
                print(f"  Added: {project_path}")
    
    # Count removed (projects in old cache but not discovered)
    removed = len(set(cache.keys()) - set(discovered.keys()))
    if args.verbose and removed > 0:
        for old_path in set(cache.keys()) - set(discovered.keys()):
            print(f"  Removed: {old_path}")
    
    # Save updated cache
    save_cache(cache_path, new_cache)
    
    # Generate HTML
    html_content = generate_html(new_cache, args.title, root)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    # Print summary
    total = len(new_cache)
    changes = added + updated + removed
    
    if changes > 0:
        parts = []
        if added:
            parts.append(f"{added} added")
        if updated:
            parts.append(f"{updated} updated")
        if removed:
            parts.append(f"{removed} removed")
        print(f"Index updated: {', '.join(parts)} ({total} total projects)")
    else:
        print(f"Index up to date ({total} projects)")
    
    print(f"Output: {output_path}")


if __name__ == '__main__':
    main()

