#!/usr/bin/env python3
"""Platform link audit utility.

Checks frontend source for:
- missing internal href routes
- insecure http://.../api URLs
- placeholder href="#" links
"""

from pathlib import Path
import re


ROOT = Path('/app/frontend')
APP_DIR = ROOT / 'app'
SRC_DIR = ROOT / 'src'


def iter_files():
    for base in [APP_DIR, SRC_DIR]:
        for p in base.rglob('*'):
            if p.suffix not in {'.ts', '.tsx', '.js', '.jsx', '.html'}:
                continue
            if any(skip in p.parts for skip in {'dist', 'dist_tmp', 'node_modules', '.expo'}):
                continue
            yield p


def build_routes():
    routes = {'/'}
    for p in APP_DIR.rglob('*.tsx'):
        rel = p.relative_to(APP_DIR).as_posix()
        if rel.startswith(('+', '_')):
            continue
        if rel.endswith('/index.tsx'):
            route = '/' + rel[:-10]
        else:
            route = '/' + rel[:-4]
        route = route.replace('/(tabs)', '').replace('//', '/')
        route = route.replace('/[id]', '/:id').replace('/[token]', '/:token').replace('/[slug]', '/:slug')
        routes.add(route)
    return routes


def main():
    href_pattern = re.compile(r'href=["\'](/[^"\']+)["\']')
    insecure_pattern = re.compile(r'http://[^"\'\s]+/api')

    routes = build_routes()
    hrefs = set()
    missing_routes = []
    insecure = []
    placeholders = []

    for p in iter_files():
        text = p.read_text(encoding='utf-8', errors='ignore')
        if 'href="#"' in text or "href='#'" in text:
            placeholders.append(str(p))
        if p.name != '+html.tsx' and insecure_pattern.search(text):
            insecure.append(str(p))
        for m in href_pattern.finditer(text):
            hrefs.add(m.group(1))

    for href in sorted(hrefs):
        if href.startswith('/api'):
            continue
        if href in routes:
            continue
        static_candidate = ROOT / 'public' / href.lstrip('/')
        if static_candidate.exists():
            continue
        missing_routes.append(href)

    print('=== Platform Link Audit ===')
    print(f'source_files_scanned: {sum(1 for _ in iter_files())}')
    print(f'hrefs_found: {len(hrefs)}')
    print(f'missing_internal_routes: {len(missing_routes)}')
    print(f'insecure_http_api_refs: {len(insecure)}')
    print(f'placeholder_hash_links: {len(placeholders)}')
    if missing_routes:
        print('\nMissing routes:')
        for r in missing_routes[:100]:
            print('-', r)
    if insecure:
        print('\nInsecure API refs:')
        for f in insecure[:100]:
            print('-', f)
    if placeholders:
        print('\nPlaceholder # links:')
        for f in placeholders[:100]:
            print('-', f)


if __name__ == '__main__':
    main()
