#!/usr/bin/env python3
"""
Codemod to fix @typescript-eslint/no-unused-vars warnings.
Strategy:
- Unused imports: remove the specific import identifier
- Unused destructured vars: prefix with _
- Unused function params (catch etc.): prefix with _
"""
import json
import re
import sys
from collections import defaultdict

REPORT_FILE = '/tmp/eslint_report2.json'

def extract_var_name(message):
    """Extract the variable name from an ESLint no-unused-vars message."""
    m = re.match(r"'(\w+)'", message)
    return m.group(1) if m else None

def remove_import_identifier(line, var_name):
    """Remove a specific identifier from an import line."""
    # Handle: import { A, B, C } from '...'
    # Remove just the specific identifier
    
    # Named imports: { ..., VarName, ... } or { VarName } 
    # Try to remove from named imports
    pattern1 = rf',\s*{re.escape(var_name)}\s*(?=,|}})'  # middle
    pattern2 = rf'{re.escape(var_name)}\s*,\s*'  # first with comma after
    pattern3 = rf'{{\s*{re.escape(var_name)}\s*}}'  # only import in braces
    
    # Check if entire import becomes empty
    new_line = re.sub(pattern1, '', line)
    if new_line != line:
        return new_line
    
    new_line = re.sub(pattern2, '', line)
    if new_line != line:
        return new_line
    
    # Check if it's the only named import
    new_line = re.sub(pattern3, '{}', line)
    if '{}' in new_line:
        # Whole import is empty, remove the line
        return None
    
    # Default import: import VarName from '...'
    # Only remove if it's the default import
    default_import_pattern = rf'^(\s*)import\s+{re.escape(var_name)}\s+from\s'
    if re.match(default_import_pattern, line):
        return None  # Remove entire line
    
    # Namespace import: import * as VarName from '...'
    ns_pattern = rf'^(\s*)import\s+\*\s+as\s+{re.escape(var_name)}\s+from\s'
    if re.match(ns_pattern, line):
        return None  # Remove entire line
    
    return line  # Can't fix, return unchanged

def is_import_line(line):
    return re.match(r'\s*import\s+', line) is not None

def prefix_with_underscore(line, var_name, col):
    """Prefix a variable name with _ in the line."""
    # Try simple rename at/near the column
    # Find the variable name in the line
    pos = line.find(var_name, max(0, col - 2))
    if pos == -1:
        pos = line.find(var_name)
    if pos == -1:
        return line
    
    # Make sure we're not already prefixed
    if pos > 0 and line[pos-1] == '_':
        return line
    
    # Make sure it's a word boundary
    after = pos + len(var_name)
    if after < len(line) and (line[after].isalnum() or line[after] == '_'):
        return line
    if pos > 0 and (line[pos-1].isalnum() or line[pos-1] == '_'):
        return line
    
    return line[:pos] + '_' + line[pos:]

def process_file(filepath, warnings):
    """Process a file, fixing all unused var warnings."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  ERROR reading {filepath}: {e}")
        return 0

    # Sort warnings by line descending (process bottom-up to preserve line numbers)
    sorted_warnings = sorted(warnings, key=lambda w: w['line'], reverse=True)
    
    fixes = 0
    for warn in sorted_warnings:
        line_idx = warn['line'] - 1  # 0-based
        col = warn['column'] - 1  # 0-based
        var_name = extract_var_name(warn['msg'])
        
        if not var_name or line_idx >= len(lines):
            continue
        
        original_line = lines[line_idx]
        
        if is_import_line(original_line):
            new_line = remove_import_identifier(original_line, var_name)
            if new_line is None:
                lines[line_idx] = '// [removed unused import]\n'
                fixes += 1
            elif new_line != original_line:
                lines[line_idx] = new_line
                fixes += 1
        else:
            # For catch params, destructured vars, etc: prefix with _
            new_line = prefix_with_underscore(original_line, var_name, col)
            if new_line != original_line:
                lines[line_idx] = new_line
                fixes += 1
    
    # Clean up removed import lines
    lines = [l for l in lines if l.strip() != '// [removed unused import]']
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    return fixes

def main():
    with open(REPORT_FILE) as f:
        data = json.load(f)
    
    unused_by_file = defaultdict(list)
    for f in data:
        for m in f['messages']:
            if m['ruleId'] in ('@typescript-eslint/no-unused-vars', 'no-unused-vars'):
                unused_by_file[f['filePath']].append({
                    'line': m['line'], 
                    'column': m['column'], 
                    'msg': m['message']
                })
    
    total_fixes = 0
    files_fixed = 0
    for filepath, warnings in sorted(unused_by_file.items(), key=lambda x: -len(x[1])):
        fixes = process_file(filepath, warnings)
        if fixes > 0:
            fname = filepath.split('frontend/')[-1]
            print(f"  {fixes:3d} fixes  {fname}")
            total_fixes += fixes
            files_fixed += 1
    
    print(f"\nTotal: {total_fixes} fixes across {files_fixed} files")

if __name__ == '__main__':
    main()
