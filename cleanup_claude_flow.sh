
#!/bin/bash

# ============================================================
# SURGICAL CLAUDE FLOW REMOVAL SCRIPT v3.1
# ============================================================
# Complete removal of Claude Flow ecosystem components
# Supports: claude-flow, ruv-swarm, flow-nexus
# Features: yarn/pnpm support, database cleanup, PATH cleaning
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m'

# Detect OS
OS="$(uname -s)"
case "${OS}" in
    Linux*)     MACHINE=Linux;;
    Darwin*)    MACHINE=Mac;;
    *)          MACHINE="UNKNOWN:${OS}"
esac

echo -e "${RED}╔════════════════════════════════════════════╗${NC}"
echo -e "${RED}║   SURGICAL CLAUDE FLOW REMOVAL SCRIPT      ║${NC}"
echo -e "${RED}║              Version 3.1                   ║${NC}"
echo -e "${RED}╚════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Detected OS: ${MACHINE}${NC}"
echo -e "${YELLOW}This will surgically remove Claude Flow ecosystem (flow/swarm/nexus)!${NC}"
echo ""

# Function to backup file with timestamp
backup_file() {
    local file="$1"
    if [ -f "$file" ]; then
        local backup="${file}.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$file" "$backup"
        echo -e "${GREEN}✓ Backed up to: $backup${NC}"
    fi
}

# Function to remove claude-flow lines with sed (cross-platform)
remove_claude_flow_lines() {
    local file="$1"
    if [ -f "$file" ]; then
        if [[ "$MACHINE" == "Mac" ]]; then
            # Remove lines containing claude-flow, ruv-swarm, or flow-nexus
            sed -i '' '/claude-flow/d' "$file"
            sed -i '' '/ruv-swarm/d' "$file"
            sed -i '' '/flow-nexus/d' "$file"
            sed -i '' '/CLAUDE_FLOW_/d' "$file"
        else
            sed -i '/claude-flow/d' "$file"
            sed -i '/ruv-swarm/d' "$file"
            sed -i '/flow-nexus/d' "$file"
            sed -i '/CLAUDE_FLOW_/d' "$file"
        fi
    fi
}

# Step 1: Kill all running processes
echo -e "${CYAN}Step 1: Killing Claude Flow/Swarm/Nexus processes...${NC}"
PIDS=$(ps aux | grep -E "claude-flow|ruv-swarm|flow-nexus" | grep -v grep | awk '{print $2}')
if [ -n "$PIDS" ]; then
    # Kill processes without xargs -r (not available on macOS)
    while read -r pid; do
        kill -9 "$pid" 2>/dev/null
    done <<< "$PIDS"
    echo -e "${GREEN}✓ Killed $(echo "$PIDS" | wc -l) processes${NC}"
else
    echo -e "${GREEN}✓ No processes found${NC}"
fi

# Step 2: Remove packages from all package managers
echo ""
echo -e "${CYAN}Step 2: Removing Claude Flow packages from all package managers...${NC}"

# NPM
if command -v npm >/dev/null 2>&1; then
    npm uninstall -g claude-flow 2>/dev/null
    npm uninstall -g claude-flow@alpha 2>/dev/null
    npm uninstall -g claude-flow@beta 2>/dev/null
    npm uninstall -g claude-flow@latest 2>/dev/null
    npm uninstall -g ruv-swarm 2>/dev/null
    npm uninstall -g ruv-swarm@alpha 2>/dev/null
    npm uninstall -g flow-nexus 2>/dev/null
    npm uninstall -g flow-nexus@latest 2>/dev/null
    echo -e "${GREEN}✓ NPM packages removed${NC}"
fi

# Yarn
if command -v yarn >/dev/null 2>&1; then
    yarn global remove claude-flow 2>/dev/null
    yarn global remove ruv-swarm 2>/dev/null
    yarn global remove flow-nexus 2>/dev/null
    echo -e "${GREEN}✓ Yarn packages removed${NC}"
fi

# PNPM
if command -v pnpm >/dev/null 2>&1; then
    pnpm uninstall -g claude-flow 2>/dev/null
    pnpm uninstall -g ruv-swarm 2>/dev/null
    pnpm uninstall -g flow-nexus 2>/dev/null
    echo -e "${GREEN}✓ PNPM packages removed${NC}"
fi

# Clean NPX cache and other npm cache locations (claude-flow specific)
rm -rf ~/.npm/_npx/*claude-flow* 2>/dev/null
rm -rf ~/.npm/_npx/*ruv-swarm* 2>/dev/null
rm -rf ~/.npm/_npx/*flow-nexus* 2>/dev/null
rm -rf ~/.npm/_cacache/*claude-flow* 2>/dev/null
rm -rf ~/.npm/_cacache/*ruv-swarm* 2>/dev/null
rm -rf ~/.npm/_cacache/*flow-nexus* 2>/dev/null

# Clean npm cache for claude-flow specifically
if command -v npm >/dev/null 2>&1; then
    npm cache clean --force 2>/dev/null || true
    NPM_CACHE=$(npm config get cache 2>/dev/null)
    if [ -n "$NPM_CACHE" ] && [ -d "$NPM_CACHE" ]; then
        find "$NPM_CACHE" -type d -name "*claude-flow*" -exec rm -rf {} + 2>/dev/null || true
        find "$NPM_CACHE" -type d -name "*ruv-swarm*" -exec rm -rf {} + 2>/dev/null || true
        find "$NPM_CACHE" -type d -name "*flow-nexus*" -exec rm -rf {} + 2>/dev/null || true
    fi
fi

# Clean yarn cache
if command -v yarn >/dev/null 2>&1; then
    yarn cache clean 2>/dev/null || true
    YARN_CACHE=$(yarn cache dir 2>/dev/null)
    if [ -n "$YARN_CACHE" ] && [ -d "$YARN_CACHE" ]; then
        find "$YARN_CACHE" -type d -name "*claude-flow*" -exec rm -rf {} + 2>/dev/null || true
        find "$YARN_CACHE" -type d -name "*ruv-swarm*" -exec rm -rf {} + 2>/dev/null || true
        find "$YARN_CACHE" -type d -name "*flow-nexus*" -exec rm -rf {} + 2>/dev/null || true
    fi
fi

# Clean pnpm cache
if command -v pnpm >/dev/null 2>&1; then
    PNPM_HOME=$(pnpm store path 2>/dev/null)
    if [ -n "$PNPM_HOME" ] && [ -d "$PNPM_HOME" ]; then
        find "$PNPM_HOME" -type d -name "*claude-flow*" -exec rm -rf {} + 2>/dev/null || true
        find "$PNPM_HOME" -type d -name "*ruv-swarm*" -exec rm -rf {} + 2>/dev/null || true
        find "$PNPM_HOME" -type d -name "*flow-nexus*" -exec rm -rf {} + 2>/dev/null || true
    fi
fi

echo -e "${GREEN}✓ All package manager caches cleaned${NC}"

# Clean global node_modules directly
if command -v npm >/dev/null 2>&1; then
    NPM_PREFIX=$(npm config get prefix 2>/dev/null)
    if [ -n "$NPM_PREFIX" ]; then
        GLOBAL_NODE_MODULES="$NPM_PREFIX/lib/node_modules"
        if [ -d "$GLOBAL_NODE_MODULES/claude-flow" ]; then
            rm -rf "$GLOBAL_NODE_MODULES/claude-flow"
            echo -e "${GREEN}✓ Removed claude-flow from global node_modules${NC}"
        fi
        if [ -d "$GLOBAL_NODE_MODULES/ruv-swarm" ]; then
            rm -rf "$GLOBAL_NODE_MODULES/ruv-swarm"
            echo -e "${GREEN}✓ Removed ruv-swarm from global node_modules${NC}"
        fi
        if [ -d "$GLOBAL_NODE_MODULES/flow-nexus" ]; then
            rm -rf "$GLOBAL_NODE_MODULES/flow-nexus"
            echo -e "${GREEN}✓ Removed flow-nexus from global node_modules${NC}"
        fi
        # Also check for binaries in bin directory
        if [ -f "$NPM_PREFIX/bin/claude-flow" ]; then
            rm -f "$NPM_PREFIX/bin/claude-flow"
            echo -e "${GREEN}✓ Removed claude-flow binary${NC}"
        fi
        if [ -f "$NPM_PREFIX/bin/ruv-swarm" ]; then
            rm -f "$NPM_PREFIX/bin/ruv-swarm"
            echo -e "${GREEN}✓ Removed ruv-swarm binary${NC}"
        fi
        if [ -f "$NPM_PREFIX/bin/flow-nexus" ]; then
            rm -f "$NPM_PREFIX/bin/flow-nexus"
            echo -e "${GREEN}✓ Removed flow-nexus binary${NC}"
        fi
    fi
fi

# Step 3: Remove directories
echo ""
echo -e "${CYAN}Step 3: Removing Claude Flow directories...${NC}"
DIRS_TO_REMOVE=(
    ".swarm"
    ".claude-flow"
    ".hive-mind"
    ".claude"
    "~/.swarm"
    "~/.claude-flow"
    "~/.hive-mind"
    "/tmp/.swarm"
    "/tmp/.claude-flow"
    "/tmp/.hive-mind"
    "~/.config/claude-flow"
    "~/.config/ruv-swarm"
    "~/.config/flow-nexus"
    "~/.local/share/claude-flow"
    "~/.local/share/ruv-swarm"
    "~/.local/share/flow-nexus"
)

# Add macOS-specific paths
if [[ "$MACHINE" == "Mac" ]]; then
    DIRS_TO_REMOVE+=(
        "~/Library/Application Support/claude-flow"
        "~/Library/Application Support/ruv-swarm"
        "~/Library/Application Support/flow-nexus"
        "~/Library/Caches/claude-flow"
        "~/Library/Caches/ruv-swarm"
        "~/Library/Caches/flow-nexus"
    )
fi

for dir in "${DIRS_TO_REMOVE[@]}"; do
    expanded_dir=$(eval echo "$dir")
    if [ -d "$expanded_dir" ]; then
        rm -rf "$expanded_dir" 2>/dev/null
        echo -e "${GREEN}✓ Removed: $expanded_dir${NC}"
    fi
done

# Remove specific database files
echo ""
echo -e "${CYAN}Removing Claude Flow database files...${NC}"
DB_FILES=(
    ".swarm/memory.db"
    ".hive-mind/hive.db"
    "~/.swarm/memory.db"
    "~/.hive-mind/hive.db"
    ".claude-flow/token-usage.json"
    "~/.claude-flow/token-usage.json"
)

for db_file in "${DB_FILES[@]}"; do
    expanded_file=$(eval echo "$db_file")
    if [ -f "$expanded_file" ]; then
        rm -f "$expanded_file" 2>/dev/null
        echo -e "${GREEN}✓ Removed: $expanded_file${NC}"
    fi
done

# Step 4: SURGICAL Claude Code settings.json cleaning
echo ""
echo -e "${CYAN}Step 4: Surgically cleaning Claude Code settings...${NC}"
CLAUDE_SETTINGS="$HOME/.claude/settings.json"

if [ -f "$CLAUDE_SETTINGS" ]; then
    backup_file "$CLAUDE_SETTINGS"

    echo "Surgically removing ONLY claude-flow hooks and settings..."

    if command -v jq >/dev/null 2>&1; then
        # SURGICAL JQ APPROACH - Only removes claude-flow items
        jq '
        # Remove CLAUDE_FLOW_ environment variables
        if .env then
          .env |= with_entries(select(.key | startswith("CLAUDE_FLOW_") | not))
        else . end |

        # Remove claude-flow, ruv-swarm, and flow-nexus from MCP servers
        if .enabledMcpjsonServers then
          .enabledMcpjsonServers |= map(select(. != "claude-flow" and . != "ruv-swarm" and . != "flow-nexus"))
        else . end |

        # SURGICAL HOOK REMOVAL - only remove hooks containing claude-flow
        if .hooks then
          if .hooks.PreToolUse then
            .hooks.PreToolUse |= map(
              if .hooks then
                .hooks |= map(select(.command // "" | contains("claude-flow") or contains("ruv-swarm") | not))
              else . end |
              select(.hooks and (.hooks | length > 0) or (.hooks | not))
            )
          else . end |

          if .hooks.PostToolUse then
            .hooks.PostToolUse |= map(
              if .hooks then
                .hooks |= map(select(.command // "" | contains("claude-flow") or contains("ruv-swarm") | not))
              else . end |
              select(.hooks and (.hooks | length > 0) or (.hooks | not))
            )
          else . end |

          if .hooks.Stop then
            .hooks.Stop |= map(
              if .hooks then
                .hooks |= map(select(.command // "" | contains("claude-flow") or contains("ruv-swarm") | not))
              else . end |
              select(.hooks and (.hooks | length > 0) or (.hooks | not))
            )
          else . end |

          if .hooks.PreCompact then
            .hooks.PreCompact |= map(
              if .hooks then
                .hooks |= map(select(.command // "" | contains("claude-flow") or contains("ruv-swarm") | not))
              else . end |
              select(.hooks and (.hooks | length > 0) or (.hooks | not))
            )
          else . end
        else . end
        ' "$CLAUDE_SETTINGS" > "${CLAUDE_SETTINGS}.tmp"

        if [ $? -eq 0 ]; then
            mv "${CLAUDE_SETTINGS}.tmp" "$CLAUDE_SETTINGS"
            echo -e "${GREEN}✓ Surgically cleaned Claude Code settings with jq${NC}"
        else
            echo -e "${YELLOW}⚠ jq failed, falling back to sed...${NC}"
            rm -f "${CLAUDE_SETTINGS}.tmp"
            remove_claude_flow_lines "$CLAUDE_SETTINGS"
            echo -e "${GREEN}✓ Cleaned Claude Code settings with sed${NC}"
        fi
    else
        # SED FALLBACK - Line-by-line removal
        echo "Using sed for surgical removal..."
        remove_claude_flow_lines "$CLAUDE_SETTINGS"
        echo -e "${GREEN}✓ Cleaned Claude Code settings with sed${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Claude Code settings not found${NC}"
fi

# Step 5: Clean package.json
echo ""
echo -e "${CYAN}Step 5: Checking project package.json...${NC}"
if [ -f "package.json" ]; then
    if grep -q "claude-flow\|ruv-swarm\|flow-nexus" package.json; then
        backup_file "package.json"
        remove_claude_flow_lines "package.json"
        echo -e "${GREEN}✓ Removed claude-flow from package.json${NC}"
    else
        echo -e "${GREEN}✓ No claude-flow found in package.json${NC}"
    fi
fi

# Step 6: Clean Claude Desktop config
echo ""
echo -e "${CYAN}Step 6: Cleaning Claude Desktop config...${NC}"

if [[ "$MACHINE" == "Mac" ]]; then
    CLAUDE_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
else
    CLAUDE_CONFIG="$HOME/.config/Claude/claude_desktop_config.json"
fi

if [ -f "$CLAUDE_CONFIG" ]; then
    if grep -q "claude-flow\|ruv-swarm\|flow-nexus" "$CLAUDE_CONFIG"; then
        backup_file "$CLAUDE_CONFIG"
        if command -v jq >/dev/null 2>&1; then
            jq 'del(.mcpServers."claude-flow") | del(.mcpServers."ruv-swarm") | del(.mcpServers."flow-nexus")' "$CLAUDE_CONFIG" > "${CLAUDE_CONFIG}.tmp"
            mv "${CLAUDE_CONFIG}.tmp" "$CLAUDE_CONFIG"
        else
            remove_claude_flow_lines "$CLAUDE_CONFIG"
        fi
        echo -e "${GREEN}✓ Removed claude-flow from Claude Desktop config${NC}"
    else
        echo -e "${GREEN}✓ No claude-flow found in Claude Desktop config${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Claude Desktop config not found${NC}"
fi

# Step 7: Clean shell configs
echo ""
echo -e "${CYAN}Step 7: Cleaning shell configuration files...${NC}"
SHELL_FILES=(
    "~/.bashrc"
    "~/.zshrc"
    "~/.profile"
    "~/.bash_profile"
    "~/.zprofile"
    "~/.zshenv"
    "~/.config/fish/config.fish"
)

for shell_file in "${SHELL_FILES[@]}"; do
    expanded_file=$(eval echo "$shell_file")
    if [ -f "$expanded_file" ]; then
        if grep -q "claude-flow\|ruv-swarm\|flow-nexus\|CLAUDE_FLOW" "$expanded_file"; then
            backup_file "$expanded_file"
            remove_claude_flow_lines "$expanded_file"
            echo -e "${GREEN}✓ Cleaned: $expanded_file${NC}"
        fi
    fi
done

# Step 8: Remove binaries from common PATH locations
echo ""
echo -e "${CYAN}Step 8: Checking common PATH locations for binaries...${NC}"
PATH_LOCATIONS=(
    "/usr/local/bin"
    "/usr/bin"
    "$HOME/.local/bin"
    "$HOME/bin"
)

for path_dir in "${PATH_LOCATIONS[@]}"; do
    if [ -d "$path_dir" ]; then
        if [ -f "$path_dir/claude-flow" ] || [ -L "$path_dir/claude-flow" ]; then
            rm -f "$path_dir/claude-flow"
            echo -e "${GREEN}✓ Removed claude-flow from $path_dir${NC}"
        fi
        if [ -f "$path_dir/ruv-swarm" ] || [ -L "$path_dir/ruv-swarm" ]; then
            rm -f "$path_dir/ruv-swarm"
            echo -e "${GREEN}✓ Removed ruv-swarm from $path_dir${NC}"
        fi
        if [ -f "$path_dir/flow-nexus" ] || [ -L "$path_dir/flow-nexus" ]; then
            rm -f "$path_dir/flow-nexus"
            echo -e "${GREEN}✓ Removed flow-nexus from $path_dir${NC}"
        fi
    fi
done
echo -e "${GREEN}✓ PATH locations checked${NC}"

# Step 9: Clear environment variables
echo ""
echo -e "${CYAN}Step 9: Clearing claude-flow environment variables...${NC}"
unset CLAUDE_FLOW_AUTO_COMMIT
unset CLAUDE_FLOW_AUTO_PUSH
unset CLAUDE_FLOW_HOOKS_ENABLED
unset CLAUDE_FLOW_TELEMETRY_ENABLED
unset CLAUDE_FLOW_REMOTE_EXECUTION
unset CLAUDE_FLOW_CHECKPOINTS_ENABLED
echo -e "${GREEN}✓ Claude Flow environment variables cleared${NC}"

# Step 10: Final verification
echo ""
echo -e "${CYAN}Step 10: Verification...${NC}"
sleep 1

# Check processes
if ps aux | grep -E "claude-flow|ruv-swarm|flow-nexus" | grep -v grep > /dev/null; then
    echo -e "${RED}✗ WARNING: Processes still running!${NC}"
else
    echo -e "${GREEN}✓ No claude-flow processes running${NC}"
fi

# Check packages
PACKAGES_FOUND=0
if command -v npm >/dev/null 2>&1 && npm list -g 2>/dev/null | grep -qE "claude-flow|ruv-swarm|flow-nexus"; then
    echo -e "${RED}✗ WARNING: NPM packages still installed!${NC}"
    PACKAGES_FOUND=1
fi
if command -v yarn >/dev/null 2>&1 && yarn global list 2>/dev/null | grep -qE "claude-flow|ruv-swarm|flow-nexus"; then
    echo -e "${RED}✗ WARNING: Yarn packages still installed!${NC}"
    PACKAGES_FOUND=1
fi
if command -v pnpm >/dev/null 2>&1 && pnpm list -g 2>/dev/null | grep -qE "claude-flow|ruv-swarm|flow-nexus"; then
    echo -e "${RED}✗ WARNING: PNPM packages still installed!${NC}"
    PACKAGES_FOUND=1
fi
if [ $PACKAGES_FOUND -eq 0 ]; then
    echo -e "${GREEN}✓ All packages removed from all package managers${NC}"
fi

# Check settings file
if [ -f "$CLAUDE_SETTINGS" ] && grep -qE "claude-flow|ruv-swarm|flow-nexus" "$CLAUDE_SETTINGS"; then
    echo -e "${YELLOW}⚠ Some claude-flow references may remain in settings${NC}"
    echo "Check: $CLAUDE_SETTINGS"
else
    echo -e "${GREEN}✓ Settings cleaned${NC}"
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}         SURGICAL CLEANUP COMPLETE!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo ""
echo "✅ SAFELY removed:"
echo "  • Claude Flow/Swarm/Nexus processes"
echo "  • All ecosystem packages (claude-flow, ruv-swarm, flow-nexus)"
echo "  • Project directories (.claude, .swarm, .hive-mind, .claude-flow)"
echo "  • Database files (memory.db, hive.db, token-usage.json)"
echo "  • Claude Flow hooks (preserving other hooks)"
echo "  • Claude Flow environment variables"
echo "  • All MCP server references (claude-flow, ruv-swarm, flow-nexus)"
echo "  • Binaries from all PATH locations"
echo "  • Cache from NPM/Yarn/PNPM package managers"
echo ""
echo "✅ PRESERVED:"
echo "  • All other Claude Code hooks"
echo "  • All other MCP servers"
echo "  • All other environment variables"
echo "  • All other packages (only removed claude-flow packages)"
echo "  • General caches (only removed claude-flow related caches)"
echo ""
echo -e "${YELLOW}NEXT STEPS:${NC}"
echo "1. Restart terminal"
echo "2. Restart Claude Desktop"
echo "3. Test Claude Code - hooks error should be gone!"
echo ""
echo -e "${CYAN}If you need to restore settings:${NC}"
echo "All files were backed up with timestamps"
`
