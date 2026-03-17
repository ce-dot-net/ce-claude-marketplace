
import sys
import json
import uuid
from pathlib import Path
from ..config import get_config
import subprocess
import os

# Common abbreviations to expand (ported from plugin)
ABBREVIATIONS = {
    ' JWT ': ' JSON Web Token ',
    ' API ': ' REST API ',
    ' DB ': ' database ',
    ' env ': ' environment ',
    ' auth ': ' authentication ',
    ' config ': ' configuration ',
    ' deps ': ' dependencies ',
    ' repo ': ' repository ',
}

def expand_abbreviations(prompt):
    """Expand common abbreviations for better semantic search"""
    result = f" {prompt} "
    for abbrev, full in ABBREVIATIONS.items():
        result = result.replace(abbrev, full)
    return result.strip()

def run(prompt):
    """
    Run pre-task logic:
    1. Expand abbreviations
    2. Manage session pinning
    3. Call ace-cli search
    4. Provide output to user
    """
    try:
        # Get config
        config = get_config()
        if not config['project']:
            print("⚠️ [ACE] No project context found. Run '/ace_configure' or 'ace-cli configure'")
            return

        # 1. Expand prompt
        search_query = expand_abbreviations(prompt)
        
        # 2. Session Pinning
        session_id = str(uuid.uuid4())
        # In plugin this was stored in /tmp for other hooks to pick up.
        # We'll do the same for consistency with legacy scripts if they exist
        try:
            session_file = Path(f"/tmp/ace-session-{config['project']}.txt")
            session_file.write_text(session_id)
        except Exception:
            pass # Non-fatal

        # 3. Call ace-cli search
        # We use the CLI directly
        cmd = ['ace-cli', 'search', search_query, '--json']
        
        env = dict(os.environ)
        if config['org']:
            env['ACE_ORG_ID'] = config['org']
        if config['project']:
            env['ACE_PROJECT_ID'] = config['project']

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env
        )

        if result.returncode != 0:
            print(f"❌ [ACE] Search failed: {result.stderr}")
            return

        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"❌ [ACE] Invalid JSON from CLI: {result.stdout}")
            return

        # 4. Format Output
        pattern_list = response.get('similar_patterns', [])
        pattern_count = len(pattern_list)
        domains_summary = response.get('domains_summary', {})

        if pattern_count > 0:
            print(f"✅ [ACE] Found {pattern_count} relevant patterns for session {session_id[:8]}")
            
            # Show domain summary
            abstract_domains = domains_summary.get('abstract', [])
            if abstract_domains:
                domains_str = ', '.join(abstract_domains[:3])
                if len(abstract_domains) > 3:
                    domains_str += f' (+{len(abstract_domains) - 3} more)'
                print(f"   Domains: {domains_str}")

            # Show top 3 bullets
            for bullet in pattern_list[:3]:
                content = bullet.get('content', '')
                if len(content) > 80:
                    content = content[:77] + '...'
                domain = bullet.get('domain', 'general')
                helpful = bullet.get('helpful', 0)
                print(f"   • [{domain}] {content} (+{helpful})")
            
            if pattern_count > 3:
                print(f"   ... and {pattern_count - 3} more patterns")
            
        else:
            print("ℹ️  [ACE] No patterns found for this query")

    except Exception as e:
        print(f"❌ [ACE] Pre-task hook error: {e}")
