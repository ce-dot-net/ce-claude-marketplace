#!/usr/bin/env bash
# ACE Orchestration Plugin: v4.2.6 → v5.0.0 Migration Script
#
# This script helps users migrate from MCP-based architecture to CLI-based architecture

set -euo pipefail

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ACE Orchestration Plugin v5.0.0 Migration"
echo "  MCP → CLI Architecture"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Step 1: Check ce-ace CLI
echo "📋 Step 1/5: Checking ce-ace CLI installation..."
echo ""

if command -v ce-ace >/dev/null 2>&1; then
  CE_ACE_VERSION=$(ce-ace --version 2>/dev/null || echo "unknown")
  echo -e "${GREEN}✅ ce-ace CLI found${NC} (version: $CE_ACE_VERSION)"
else
  echo -e "${YELLOW}⚠️  ce-ace CLI not found${NC}"
  echo ""
  echo "Installation required:"
  echo "  npm install -g @ace-sdk/cli"
  echo ""
  read -p "Install ce-ace CLI now? (y/n) " -n 1 -r
  echo

  if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Installing ce-ace CLI..."
    npm install -g @ace-sdk/cli || {
      echo -e "${RED}❌ Failed to install ce-ace CLI${NC}"
      echo "Please install manually and run this script again."
      exit 1
    }
    echo -e "${GREEN}✅ ce-ace CLI installed${NC}"
  else
    echo -e "${YELLOW}⚠️  Skipping CLI installation${NC}"
    echo "You'll need to install it before using ACE v5.0.0"
  fi
fi

echo ""

# Step 2: Check for old MCP config
echo "📋 Step 2/5: Checking for old MCP configuration..."
echo ""

MCP_CONFIG="$HOME/.claude/mcp/config.json"
MCP_NEEDS_CLEANUP=false

if [ -f "$MCP_CONFIG" ]; then
  if grep -q "ace-pattern-learning" "$MCP_CONFIG" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Found ace-pattern-learning in MCP config${NC}"
    MCP_NEEDS_CLEANUP=true
  else
    echo -e "${GREEN}✅ MCP config is clean${NC}"
  fi
else
  echo -e "${BLUE}ℹ️  No MCP config found (fresh install)${NC}"
fi

echo ""

# Step 3: Backup MCP config if needed
if [ "$MCP_NEEDS_CLEANUP" = true ]; then
  echo "📋 Step 3/5: Backing up and cleaning MCP config..."
  echo ""

  BACKUP_FILE="${MCP_CONFIG}.backup-v4-$(date +%Y%m%d-%H%M%S)"

  echo "Creating backup: $BACKUP_FILE"
  cp "$MCP_CONFIG" "$BACKUP_FILE"
  echo -e "${GREEN}✅ Backup created${NC}"

  echo "Removing ace-pattern-learning from MCP config..."
  if command -v jq >/dev/null 2>&1; then
    jq 'del(.mcpServers["ace-pattern-learning"])' "$MCP_CONFIG" > "${MCP_CONFIG}.tmp"
    mv "${MCP_CONFIG}.tmp" "$MCP_CONFIG"
    echo -e "${GREEN}✅ MCP config cleaned${NC}"
  else
    echo -e "${YELLOW}⚠️  jq not found - manual cleanup required${NC}"
    echo "Please edit $MCP_CONFIG and remove the 'ace-pattern-learning' entry"
  fi
else
  echo "📋 Step 3/5: Skipping MCP config cleanup (not needed)"
fi

echo ""

# Step 4: Check project CLAUDE.md
echo "📋 Step 4/5: Checking project CLAUDE.md..."
echo ""

if [ -f "CLAUDE.md" ]; then
  if grep -q "ACE_SECTION_START" "CLAUDE.md" 2>/dev/null; then
    CURRENT_VERSION=$(grep -o "ACE_SECTION_START v[0-9.]*" "CLAUDE.md" | head -1 | awk '{print $2}')
    echo -e "${BLUE}ℹ️  Found ACE section (version: ${CURRENT_VERSION})${NC}"

    if [[ "$CURRENT_VERSION" < "v5.0.0" ]]; then
      echo ""
      echo "CLAUDE.md needs updating to v5.0.0"
      echo "Run: /ace-claude-init --update"
      echo ""
    else
      echo -e "${GREEN}✅ CLAUDE.md is up to date${NC}"
    fi
  else
    echo -e "${YELLOW}⚠️  No ACE section found in CLAUDE.md${NC}"
    echo "Run: /ace-claude-init"
  fi
else
  echo -e "${BLUE}ℹ️  No CLAUDE.md in current directory${NC}"
fi

echo ""

# Step 5: Summary and next steps
echo "📋 Step 5/5: Migration Summary"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo ""

if command -v ce-ace >/dev/null 2>&1; then
  echo -e "${GREEN}✅ ce-ace CLI: Installed${NC}"
else
  echo -e "${RED}❌ ce-ace CLI: Not installed${NC}"
fi

if [ "$MCP_NEEDS_CLEANUP" = true ]; then
  echo -e "${GREEN}✅ MCP Config: Cleaned (backup saved)${NC}"
else
  echo -e "${GREEN}✅ MCP Config: No cleanup needed${NC}"
fi

echo ""
echo "Next Steps:"
echo ""
echo "1. Restart Claude Code (to load v5.0.0 plugin)"
echo ""
echo "2. In a project, run:"
echo "   /ace-configure"
echo ""
echo "3. Verify installation:"
echo "   /ace-status"
echo ""
echo "4. Optional - Bootstrap patterns:"
echo "   /ace-bootstrap"
echo ""
echo "5. Start coding! Hooks will auto-run when you implement tasks."
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Additional help
echo -e "${BLUE}ℹ️  Need Help?${NC}"
echo ""
echo "  • README.md - Full documentation"
echo "  • CHANGELOG.md - What changed in v5.0.0"
echo "  • /ace-status - Check connection to ACE server"
echo ""

# Check if running from plugin directory
if [ ! -f "scripts/migrate-to-v5.sh" ]; then
  echo -e "${YELLOW}⚠️  Note: You're not in the plugin directory${NC}"
  echo "This script works best when run from:"
  echo "  plugins/ace/"
  echo ""
fi

echo "Migration complete! 🎉"
echo ""
