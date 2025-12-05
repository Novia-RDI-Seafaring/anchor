"""UI Logic for determining and formatting UI components based on search results."""
from src.types import UIComponentType



def determine_component_type(query: str, results: list) -> UIComponentType:
    """
    Intelligently determine which UI component to use based on query and results.
    
    Priority:
    1. Check for images in metadata
    2. Check actual content structure (bullets, tables) across all results
    3. Check query keywords
    4. Fall back to result count
    
    Args:
        query: The user's search query
        results: List of search results from the knowledge base
        
    Returns:
        UIComponentType enum indicating which component to render
    """
    query_lower = query.lower()
    
    # First, check if any results contain images in metadata
    if results:
        for r in results:
            metadata = r.get("metadata", {})
            if "image_url" in metadata or "image_base64" in metadata:
                return UIComponentType.IMAGE
    
    # Image keywords in query (if no images found in metadata)
    if any(kw in query_lower for kw in ['image', 'picture', 'photo', 'diagram', 'figure']):
        return UIComponentType.IMAGE
    
    # Analyze content structure across all results
    if results and len(results) > 0:
        # Check all results for structure patterns
        bullet_count = 0
        table_count = 0
        
        for r in results:
            content = r.get("content", "")
            if has_bullet_points(content):
                bullet_count += 1
            if has_table_structure(content):
                table_count += 1
        
        # If majority have table structure, use table
        if table_count > len(results) / 2:
            return UIComponentType.TABLE
        
        # If majority have bullet points, use list
        if bullet_count > len(results) / 2:
            return UIComponentType.LIST
        
        # Check first result as fallback
        first_content = results[0].get("content", "")
        if has_table_structure(first_content):
            return UIComponentType.TABLE
        if has_bullet_points(first_content):
            return UIComponentType.LIST
    
    # Table keywords in query (explicit request for tabular data)
    if any(kw in query_lower for kw in ['table', 'compare', 'comparison', 'columns', 'rows', 'versus', 'vs']):
        return UIComponentType.TABLE
    
    # Page preview keywords (explicit request for full page)
    if any(kw in query_lower for kw in ['preview', 'show page', 'full document', 'source page']):
        return UIComponentType.PAGE_PREVIEW
    
    # List keywords or multiple results (default for many results)
    if 'list' in query_lower or len(results) > 3:
        return UIComponentType.LIST
    
    # For single result with substantial content, use page preview
    if len(results) == 1 and results[0].get("content", ""):
        content_len = len(results[0].get("content", ""))
        if content_len > 500:  # Substantial content
            return UIComponentType.PAGE_PREVIEW
    
    # Default to list for general queries
    return UIComponentType.LIST


def has_bullet_points(content: str) -> bool:
    """Check if content contains bullet point patterns."""
    import re
    bullet_pattern = r'^[\-\•\*]\s*(.+?):\s*(.+)$'
    lines = content.split('\n')
    bullet_count = sum(1 for line in lines if re.match(bullet_pattern, line.strip()))
    return bullet_count >= 2


def has_table_structure(content: str) -> bool:
    """Check if content contains table patterns."""
    lines = content.split('\n')
    # Check for pipe tables
    pipe_lines = [line for line in lines if '|' in line and line.strip()]
    if len(pipe_lines) >= 2:
        return True
    # Check for multiple key-value pairs (could form a table)
    import re
    kv_pattern = r'^[\-\•\*]?\s*(.+?):\s*(.+)$'
    kv_count = sum(1 for line in lines if re.match(kv_pattern, line.strip()))
    return kv_count >= 4


def format_for_component(component_type: UIComponentType, results: list) -> dict:
    """
    Format search results for specific component type.
    
    Args:
        component_type: The UI component type to format for
        results: Raw search results
        
    Returns:
        Formatted data dictionary suitable for the component
    """
    if component_type == UIComponentType.LIST:
        return format_as_list(results)
    elif component_type == UIComponentType.TABLE:
        return format_as_table(results)
    elif component_type == UIComponentType.IMAGE:
        return format_as_image(results)
    elif component_type == UIComponentType.PAGE_PREVIEW:
        return format_as_page_preview(results)
    elif component_type == UIComponentType.MARKDOWN_TABLE:
        return format_as_table(results)  # Same as table for now
    else:
        return format_as_list(results)  # Default fallback



def format_as_list(results: list) -> dict:
    """Format results as a single aggregated list of bullet points.
    
    Extracts all bullet points from all chunks and combines them into one list.
    Removes duplicates based on label.
    """
    all_bullet_items = []
    seen_labels = set()
    
    # Collect all bullet points from all chunks
    for r in results:
        content = r.get("content", "")
        parsed_items = parse_bullet_points(content)
        
        for item in parsed_items:
            label = item["label"].strip().lower()
            # Only add if we haven't seen this label before (avoid duplicates)
            if label not in seen_labels:
                all_bullet_items.append(item)
                seen_labels.add(label)
    
    # If we found bullet points, return them as a single aggregated list
    if all_bullet_items:
        return {
            "items": [{
                "items": all_bullet_items,
                "type": "bullets"
            }]
        }
    
    # Fallback: if no bullet points found, try to extract key-value pairs
    # This handles cases where content has "Label: Value" format without bullets
    all_kv_items = []
    seen_kv_labels = set()
    
    for r in results:
        content = r.get("content", "")
        kv_items = parse_key_value_pairs(content)
        
        for item in kv_items:
            label = item["label"].strip().lower()
            if label not in seen_kv_labels:
                all_kv_items.append(item)
                seen_kv_labels.add(label)
    
    if all_kv_items:
        return {
            "items": [{
                "items": all_kv_items,
                "type": "bullets"
            }]
        }
    
    # Last resort: return empty or minimal structure
    return {"items": []}


def parse_bullet_points(content: str) -> list:
    """Parse bullet points from content.
    
    Detects patterns like:
    - Item: value
    • Item: value
    * Item: value
    - Item: value (with various spacing)
    
    Returns list of {label, value} dicts, or empty list if no bullets found.
    """
    import re
    
    # Pattern for bullet points with labels and values
    # Matches: "- Label: Value" or "• Label: Value" or "* Label: Value"
    # Also handles variations with different spacing
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
            if label and value:  # Ensure both are non-empty
                bullet_items.append({
                    "label": label,
                    "value": value
                })
    
    return bullet_items


def parse_key_value_pairs(content: str) -> list:
    """Parse key-value pairs from content that may not have bullet points.
    
    Detects patterns like:
    Label: Value
    Label : Value
    Label:Value
    
    Returns list of {label, value} dicts, or empty list if no pairs found.
    """
    import re
    
    # Pattern for key-value pairs (with or without bullets)
    # Matches: "Label: Value" or "Label : Value" or "Label:Value"
    kv_pattern = r'^[\-\•\*]?\s*(.+?):\s*(.+)$'
    
    lines = content.split('\n')
    kv_items = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip lines that are clearly not key-value pairs
        if len(line) > 200:  # Skip very long lines (likely paragraphs)
            continue
        match = re.match(kv_pattern, line)
        if match:
            label = match.group(1).strip()
            value = match.group(2).strip()
            # Only add if it looks like a key-value pair (not a sentence)
            if label and value and len(label) < 100 and len(value) < 200:
                # Avoid false positives: skip if it looks like a sentence
                if ':' in label or '.' in label or len(label.split()) > 8:
                    continue
                kv_items.append({
                    "label": label,
                    "value": value
                })
    
    return kv_items


def format_as_table(results: list) -> dict:
    """Format results as a table with headers and rows.
    
    Tries to parse table structure from content, or aggregates key-value pairs from all chunks.
    """
    # First, try to parse a markdown/pipe table from any result
    for r in results:
        content = r.get("content", "")
        parsed_table = parse_table_from_content(content)
        if parsed_table and len(parsed_table.get("rows", [])) > 0:
            return parsed_table
    
    # If no markdown table found, aggregate key-value pairs from all chunks
    all_kv_pairs = []
    seen_labels = set()
    
    for r in results:
        content = r.get("content", "")
        # Try bullet points first
        bullet_items = parse_bullet_points(content)
        if bullet_items:
            for item in bullet_items:
                label = item["label"].strip().lower()
                if label not in seen_labels:
                    all_kv_pairs.append([item["label"], item["value"]])
                    seen_labels.add(label)
        else:
            # Try key-value pairs
            kv_items = parse_key_value_pairs(content)
            for item in kv_items:
                label = item["label"].strip().lower()
                if label not in seen_labels:
                    all_kv_pairs.append([item["label"], item["value"]])
                    seen_labels.add(label)
    
    # If we found key-value pairs, format as a table
    if all_kv_pairs:
        return {
            "headers": ["Property", "Value"],
            "rows": all_kv_pairs
        }
    
    # Last resort: Create a minimal summary table (but this shouldn't happen often)
    if results:
        return {
            "headers": ["Property", "Value"],
            "rows": [["No structured data found", "Please check the source documents"]]
        }
    
    return {
        "headers": ["Property", "Value"],
        "rows": []
    }


def parse_table_from_content(content: str) -> dict:
    """Parse table structure from content if it contains a table.
    
    Detects patterns like:
    - Pipe-separated tables: | Header1 | Header2 |
    - Colon-separated key-value pairs that form a table
    
    Returns dict with headers and rows, or None if no table found.
    """
    import re
    
    lines = content.split('\n')
    
    # Check for markdown-style pipe tables
    pipe_lines = [line for line in lines if '|' in line and line.strip()]
    if len(pipe_lines) >= 2:
        # Parse pipe table
        rows = []
        for line in pipe_lines:
            # Skip separator lines like |---|---|
            if re.match(r'^\s*\|[\s\-\:]+\|\s*$', line):
                continue
            cells = [cell.strip() for cell in line.split('|') if cell.strip()]
            if cells:
                rows.append(cells)
        
        if len(rows) >= 2:
            return {
                "headers": rows[0],
                "rows": rows[1:]
            }
    
    # Check for key-value pairs that could form a 2-column table
    kv_pattern = r'^[\-\•\*]?\s*(.+?):\s*(.+)$'
    kv_pairs = []
    for line in lines:
        line = line.strip()
        match = re.match(kv_pattern, line)
        if match:
            kv_pairs.append([match.group(1).strip(), match.group(2).strip()])
    
    if len(kv_pairs) >= 3:
        return {
            "headers": ["Property", "Value"],
            "rows": kv_pairs
        }
    
    return None


def format_as_page_preview(results: list) -> dict:
    """Format the top result as a detailed page preview."""
    if not results:
        return {
            "source": "No results",
            "content": "No matching documents found.",
            "metadata": {},
            "similarity": 0
        }
    
    top_result = results[0]
    return {
        "source": top_result.get("filename", "Unknown Source"),
        "content": top_result.get("content", ""),
        "metadata": top_result.get("metadata", {}),
        "similarity": top_result.get("similarity", 0.0)
    }


def format_as_image(results: list) -> dict:
    """Format results as image gallery if image URLs are available in metadata."""
    images = []
    
    for r in results:
        metadata = r.get("metadata", {})
        
        # Check for image URL in metadata
        if "image_url" in metadata:
            images.append({
                "url": metadata["image_url"],
                "caption": r.get("filename", ""),
                "source": r.get("filename", ""),
                "similarity": r.get("similarity", 0.0)
            })
        # Check for base64 encoded images
        elif "image_base64" in metadata:
            images.append({
                "url": f"data:image/png;base64,{metadata['image_base64']}",
                "caption": r.get("filename", ""),
                "source": r.get("filename", ""),
                "similarity": r.get("similarity", 0.0)
            })
    
    # If no images found, return empty
    if not images:
        return {
            "images": [],
            "message": "No images found in results"
        }
    
    return {"images": images}
