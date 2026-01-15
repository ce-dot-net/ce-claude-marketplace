---
description: Login to ACE using browser-based device code authentication
---

# ACE Login

Browser-based device code authentication flow. This replaces the old API token entry method.

## Instructions for Claude

When user runs `/ace-login`, execute the device code authentication flow:

### Step 1: Check ace-cli Installation

```bash
#!/usr/bin/env bash
set -euo pipefail

# Check for ace-cli
if ! command -v ace-cli >/dev/null 2>&1; then
  echo "ace-cli not found"
  echo ""
  echo "Installation required:"
  echo "  npm install -g @ace-sdk/cli"
  exit 1
fi

VERSION=$(ace-cli --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
echo "ace-cli found (version: $VERSION)"
```

**If ace-cli not found**: Show installation instructions and exit.

### Step 2: Check for Old Config Format (Migration Warning)

Check BOTH locations for deprecated `apiToken` format:

```bash
DEPRECATED_FORMAT_FOUND=""

# Check OLD location: ~/.ace/config.json
OLD_LOCATION="$HOME/.ace/config.json"
if [ -f "$OLD_LOCATION" ]; then
  OLD_TOKEN=$(jq -r '.apiToken // empty' "$OLD_LOCATION" 2>/dev/null || echo "")
  if [ -n "$OLD_TOKEN" ]; then
    echo "⚠️  Found deprecated config at ~/.ace/config.json"
    echo "   Format: apiToken (org token)"
    DEPRECATED_FORMAT_FOUND="old_location"
  fi
fi

# Check NEW location: ~/.config/ace/config.json for OLD format (apiToken instead of auth.token)
NEW_LOCATION="$HOME/.config/ace/config.json"
if [ -f "$NEW_LOCATION" ]; then
  # Check if it has apiToken (old format) instead of auth.token (new format)
  API_TOKEN=$(jq -r '.apiToken // empty' "$NEW_LOCATION" 2>/dev/null || echo "")
  AUTH_TOKEN=$(jq -r '.auth.token // empty' "$NEW_LOCATION" 2>/dev/null || echo "")

  if [ -n "$API_TOKEN" ] && [ -z "$AUTH_TOKEN" ]; then
    echo "⚠️  Found deprecated format at ~/.config/ace/config.json"
    echo "   Format: apiToken (should be auth.token)"
    DEPRECATED_FORMAT_FOUND="new_location_old_format"
  fi
fi

# Show migration message if deprecated format found
if [ -n "$DEPRECATED_FORMAT_FOUND" ]; then
  echo ""
  echo "The old API token format (ace_xxx) is deprecated."
  echo "This login will set up the new user token authentication (ace_user_xxx)."
  echo ""
  if [ "$DEPRECATED_FORMAT_FOUND" = "old_location" ]; then
    echo "After successful login + configure, you can safely remove the old config:"
    echo "  rm ~/.ace/config.json"
  fi
  echo ""
fi
```

**Note**: The deprecated `apiToken` format can exist in TWO locations:
1. `~/.ace/config.json` - Old location (pre-XDG)
2. `~/.config/ace/config.json` - New location but old format (before device code flow)

The new format uses `auth.token` with user tokens from device code flow.

**Migration Path**:
1. Run `/ace-login` → Creates/updates config at `~/.config/ace/config.json` with `auth.token`
2. Run `/ace-configure` → Saves org/project to `.claude/settings.json`
3. Remove old config: `rm ~/.ace/config.json` (if it exists)

### Step 3: Check Current Authentication Status (New Config)

```bash
AUTH_STATUS=$(ace-cli whoami --json 2>&1 || echo '{"authenticated": false}')
AUTHENTICATED=$(echo "$AUTH_STATUS" | jq -r '.authenticated // false')
TOKEN_STATUS=$(echo "$AUTH_STATUS" | jq -r '.token_status // empty')
```

**If already authenticated with valid token**:
```
Already logged in to ACE.

Email: user@example.com
Organizations: 3 available
Session: Expires in 10 hours

To switch accounts, logout first:
  ace-cli logout
```
Exit here (no need to re-login).

**If not authenticated OR token expired**: Continue to Step 3.

### Step 4: Run Device Code Login

```bash
echo "Starting device code authentication..."
echo ""
ace-cli login --no-browser
```

**Important**: The `ace-cli login --no-browser` command will:
1. Display a verification URL (e.g., `https://ace.code-engine.app/device`)
2. Display a 6-character user code (e.g., `ABC-123`)
3. Wait for the user to complete browser authentication

**Show the user**:
```
Please open this URL in your browser:
  https://ace.code-engine.app/device

Enter this code when prompted:
  ABC-123

Waiting for authentication...
```

The CLI will poll and complete automatically once the user authorizes.

### Step 5: Verify Authentication Success

```bash
# Wait a moment for token to be saved
sleep 1

# Verify login succeeded
AUTH_STATUS=$(ace-cli whoami --json 2>&1)
AUTHENTICATED=$(echo "$AUTH_STATUS" | jq -r '.authenticated // false')

if [ "$AUTHENTICATED" = "true" ]; then
  EMAIL=$(echo "$AUTH_STATUS" | jq -r '.user.email // "unknown"')
  ORG_COUNT=$(echo "$AUTH_STATUS" | jq -r '.user.organizations | length // 0')
  TOKEN_STATUS=$(echo "$AUTH_STATUS" | jq -r '.token_status // "unknown"')

  echo ""
  echo "Login successful!"
  echo ""
  echo "  Email: $EMAIL"
  echo "  Organizations: $ORG_COUNT available"
  echo "  Session: $TOKEN_STATUS"
else
  echo ""
  echo "Login verification failed"
  echo ""
  echo "Please try again or check your network connection."
  exit 1
fi
```

### Step 6: Check Project Configuration & Suggest Next Steps

```bash
# Check if project is configured
CONFIG_FILE=".claude/settings.json"
OLD_CONFIG="$HOME/.ace/config.json"

if [ -f "$CONFIG_FILE" ]; then
  PROJECT_ID=$(jq -r '.env.ACE_PROJECT_ID // empty' "$CONFIG_FILE" 2>/dev/null || echo "")
  if [ -n "$PROJECT_ID" ]; then
    echo ""
    echo "  Project: $PROJECT_ID (configured)"
    echo ""
    echo "You're all set! ACE will now work with your tasks."

    # Remind about old config cleanup if it exists
    if [ -f "$OLD_CONFIG" ]; then
      echo ""
      echo "💡 You can now safely remove the old config:"
      echo "   rm ~/.ace/config.json"
    fi
  else
    echo ""
    echo "Next step:"
    echo "  Run /ace-configure to select your organization and project"
  fi
else
  echo ""
  echo "Next step:"
  echo "  Run /ace-configure to select your organization and project"
fi
```

## When to Use

- **First time setup**: Before running `/ace-configure`
- **Token expired**: After "ACE session expired" warning (48h+ gap)
- **Switching accounts**: Login with different credentials
- **After logout**: Re-authenticate after `ace-cli logout`

## How Device Code Flow Works

1. **Request code**: CLI requests a device code from ACE server
2. **User authorization**: User opens URL, enters code, approves access
3. **Token exchange**: CLI polls server until authorized, receives tokens
4. **Token storage**: Tokens saved to `~/.config/ace/config.json`

**Benefits over API tokens**:
- No need to copy/paste tokens manually
- Tokens auto-refresh (28-day refresh token lifetime)
- Secure browser-based authentication
- Works with SSO/OAuth providers

## Token Lifecycle

| Token Type | Lifetime | Refresh |
|------------|----------|---------|
| Access Token | ~1 hour | Auto-refreshes at 5-min threshold |
| Refresh Token | 28 days | Re-login required after expiry |

**48h standby scenario**: If you close your laptop for 48+ hours:
- Access token will expire (1 hour)
- ace-cli will auto-refresh using refresh token (if within 28 days)
- ACE hooks will warn if re-login is needed

## Troubleshooting

### "Device code expired"
The 6-character code is only valid for 15 minutes. Run `/ace-login` again.

### "Network error during polling"
Check your internet connection. The CLI polls every 5 seconds for up to 5 minutes.

### "Already authenticated" but ACE not working
Your access token may have expired. Run:
```bash
ace-cli whoami --json
```
Check `token_status` field. If "expired", run `/ace-login` again.

### "Device limit reached"
You've logged in on too many devices (default limit: 2). Options:
1. **Revoke a device**: Visit https://ace.code-engine.app/dashboard/devices
2. **Logout from another device**: Run `ace-cli logout` on another machine

After revoking, run `/ace-login` again.

### Logout and re-login
```bash
ace-cli logout
/ace-login
```

## See Also

- `/ace-configure` - Select organization and project after login
- `/ace-status` - Check current ACE connection status
- `ace-cli whoami --json` - View authentication details
- `ace-cli logout` - Clear stored credentials
