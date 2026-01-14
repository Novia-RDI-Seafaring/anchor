"""Content parsing utilities for identifying UI structures."""
from __future__ import annotations

import re


def has_bullet_points(content: str) -> bool:
    """Check if content contains bullet point patterns."""
    bullet_pattern = r'^[\-\•\*]\s*(.+?):\s*(.+)$'
    lines = content.split('\n')
    bullet_count = sum(1 for line in lines if re.match(bullet_pattern, line.strip()))
    return bullet_count >= 2


def has_table_structure(content: str) -> bool:
    """Check if content contains table patterns."""
    lines = content.split('\n')
    pipe_lines = [line for line in lines if '|' in line and line.strip()]
    if len(pipe_lines) >= 2:
        return True
    kv_pattern = r'^[\-\•\*]?\s*(.+?):\s*(.+)$'
    kv_count = sum(1 for line in lines if re.match(kv_pattern, line.strip()))
    return kv_count >= 4


def parse_bullet_points(content: str) -> list:
    """Parse bullet points from content."""
    bullet_pattern = r'^[\-\•\*]\s*(.+?):\s*(.+)$'
    lines = content.split('\n')
    bullet_items = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(bullet_pattern, line)
        if match:
            label = match.group(1).strip()
            value = match.group(2).strip()
            if label and value:
                bullet_items.append({"label": label, "value": value})
    
    return bullet_items


def parse_key_value_pairs(content: str) -> list:
    """Parse key-value pairs from content."""
    kv_pattern = r'^[\-\•\*]?\s*(.+?):\s*(.+)$'
    lines = content.split('\n')
    kv_items = []
    
    for line in lines:
        line = line.strip()
        if not line or len(line) > 200:
            continue
        match = re.match(kv_pattern, line)
        if match:
            label = match.group(1).strip()
            value = match.group(2).strip()
            if label and value and len(label) < 100 and len(value) < 200:
                if ':' in label or '.' in label or len(label.split()) > 8:
                    continue
                kv_items.append({"label": label, "value": value})
    
    return kv_items


def parse_table_from_content(content: str) -> dict | None:
    """Parse table structure from content."""
    lines = content.split('\n')
    
    # Check for markdown-style pipe tables
    pipe_lines = [line for line in lines if '|' in line and line.strip()]
    if len(pipe_lines) >= 2:
        rows = []
        for line in pipe_lines:
            if re.match(r'^\s*\|[\s\-\:]+\|\s*$', line):
                continue
            cells = [cell.strip() for cell in line.split('|') if cell.strip()]
            if cells:
                rows.append(cells)
        
        if len(rows) >= 2:
            return {"headers": rows[0], "rows": rows[1:]}
    
    # Check for key-value pairs
    kv_pattern = r'^[\-\•\*]?\s*(.+?):\s*(.+)$'
    kv_pairs = []
    for line in lines:
        line = line.strip()
        match = re.match(kv_pattern, line)
        if match:
            kv_pairs.append([match.group(1).strip(), match.group(2).strip()])
    
    if len(kv_pairs) >= 3:
        return {"headers": ["Property", "Value"], "rows": kv_pairs}
    
    return None
