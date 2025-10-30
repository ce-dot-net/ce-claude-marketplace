#!/usr/bin/env bash

# ACE Plugin - Section Parser Library
# Helper functions for extracting ACE sections from CLAUDE.md files

# Check if file has HTML comment markers
# Usage: has_markers <file_path>
# Returns: 0 if markers found, 1 if not
has_markers() {
    local file="$1"

    if [ ! -f "$file" ]; then
        return 1
    fi

    # Check for both start and end markers
    if grep -q '<!-- ACE_SECTION_START' "$file" && grep -q '<!-- ACE_SECTION_END' "$file"; then
        return 0
    fi

    return 1
}

# Extract version from HTML marker
# Usage: extract_marker_version <file_path>
# Returns: version string (e.g., "3.2.36") or empty if not found
extract_marker_version() {
    local file="$1"

    if [ ! -f "$file" ]; then
        echo ""
        return 1
    fi

    # Extract version from marker: <!-- ACE_SECTION_START v3.2.36 -->
    local version=$(grep '<!-- ACE_SECTION_START' "$file" | head -1 | grep -o 'v[0-9]\+\.[0-9]\+\.[0-9]\+' | tr -d 'v')

    echo "$version"
}

# Extract content before ACE section
# Usage: extract_before_ace <file_path>
# Output: Content before <!-- ACE_SECTION_START marker
extract_before_ace() {
    local file="$1"

    if [ ! -f "$file" ]; then
        return 1
    fi

    # Get line number of start marker
    local start_line=$(grep -n '<!-- ACE_SECTION_START' "$file" | cut -d: -f1)

    if [ -z "$start_line" ]; then
        return 1
    fi

    # Extract everything before the marker
    if [ "$start_line" -gt 1 ]; then
        head -n $((start_line - 1)) "$file"
    fi

    return 0
}

# Extract content after ACE section
# Usage: extract_after_ace <file_path>
# Output: Content after <!-- ACE_SECTION_END --> marker
extract_after_ace() {
    local file="$1"

    if [ ! -f "$file" ]; then
        return 1
    fi

    # Get line number of end marker
    local end_line=$(grep -n '<!-- ACE_SECTION_END' "$file" | cut -d: -f1)

    if [ -z "$end_line" ]; then
        return 1
    fi

    # Extract everything after the marker
    tail -n +$((end_line + 1)) "$file"

    return 0
}

# Validate ACE section structure
# Usage: validate_ace_structure <file_path>
# Returns: 0 if valid, 1 if invalid
validate_ace_structure() {
    local file="$1"

    if [ ! -f "$file" ]; then
        return 1
    fi

    # Check for markers
    if ! has_markers "$file"; then
        return 1
    fi

    # Check that start comes before end
    local start_line=$(grep -n '<!-- ACE_SECTION_START' "$file" | cut -d: -f1)
    local end_line=$(grep -n '<!-- ACE_SECTION_END' "$file" | cut -d: -f1)

    if [ -z "$start_line" ] || [ -z "$end_line" ]; then
        return 1
    fi

    if [ "$start_line" -ge "$end_line" ]; then
        return 1
    fi

    # Check for ACE header within section
    local ace_header_line=$(grep -n '# ACE Orchestration Plugin' "$file" | cut -d: -f1)

    if [ -z "$ace_header_line" ]; then
        return 1
    fi

    if [ "$ace_header_line" -le "$start_line" ] || [ "$ace_header_line" -ge "$end_line" ]; then
        return 1
    fi

    return 0
}

# Add markers to existing ACE content (migration helper)
# Usage: add_markers_to_section <file_path> <version>
# Returns: 0 if successful, 1 if failed
add_markers_to_section() {
    local file="$1"
    local version="$2"

    if [ ! -f "$file" ]; then
        return 1
    fi

    # Check if already has markers
    if has_markers "$file"; then
        return 0  # Already has markers, nothing to do
    fi

    # Find ACE section start (line with "# ACE Orchestration Plugin")
    local ace_start=$(grep -n '# ACE Orchestration Plugin' "$file" | head -1 | cut -d: -f1)

    if [ -z "$ace_start" ]; then
        return 1  # No ACE section found
    fi

    # Find ACE section end (next top-level # header or EOF)
    local ace_end=$(awk -v start="$ace_start" 'NR>start && /^# [^#]/ {print NR; exit}' "$file")

    if [ -z "$ace_end" ]; then
        ace_end=$(wc -l < "$file")
    fi

    # Create temp file with markers
    local temp_file=$(mktemp)

    # Content before ACE
    if [ "$ace_start" -gt 1 ]; then
        head -n $((ace_start - 1)) "$file" > "$temp_file"
    fi

    # Add start marker
    echo "<!-- ACE_SECTION_START v${version} -->" >> "$temp_file"

    # ACE content
    sed -n "${ace_start},${ace_end}p" "$file" >> "$temp_file"

    # Add end marker
    echo "<!-- ACE_SECTION_END v${version} -->" >> "$temp_file"

    # Content after ACE
    if [ "$ace_end" -lt "$(wc -l < "$file")" ]; then
        tail -n +$((ace_end + 1)) "$file" >> "$temp_file"
    fi

    # Replace original file
    mv "$temp_file" "$file"

    return 0
}
