# ACE Plugin Configuration Guide

**Important**: The ACE plugin requires configuration before use. You must set up your own server URL, API token, and project ID.

---

## Security Note ⚠️

**NEVER commit** `plugin.json` with real credentials to a public repository!

- ✅ Use environment variables
- ✅ Use the template (`plugin.template.json`)
- ❌ Don't hardcode API tokens
- ❌ Don't share credentials

---

## Setup Options

### Option 1: Environment Variables (Recommended)

**Step 1**: Add to your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
# ACE Plugin Configuration
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU"
export ACE_PROJECT_ID="prj_5bc0b560221052c1"
```

**Step 2**: Reload your shell:

```bash
source ~/.zshrc  # or ~/.bashrc
```

**Step 3**: Copy the template:

```bash
cd plugins/ace-orchestration
cp plugin.template.json plugin.json
```

**Step 4**: Restart Claude Code to pick up environment variables.

**Verification**:

```bash
echo $ACE_SERVER_URL     # Should show your URL
echo $ACE_API_TOKEN      # Should show your token
echo $ACE_PROJECT_ID     # Should show your project ID
```

---

### Option 2: Direct Configuration (Local Testing Only)

**For local testing only** - create `plugin.json` from template:

```bash
cd plugins/ace-orchestration
cp plugin.template.json plugin.json
```

Edit `plugin.json` and replace the environment variable references:

```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "env": {
        "ACE_SERVER_URL": "http://localhost:9000",
        "ACE_API_TOKEN": "ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU",
        "ACE_PROJECT_ID": "prj_5bc0b560221052c1"
      }
    }
  }
}
```

**⚠️ Warning**: This method is **only for local testing**. Never commit this file!

---

## Configuration Values

### ACE_SERVER_URL

**Purpose**: ACE server endpoint

**Formats**:
- Local development: `http://localhost:9000`
- Production: `https://ace.your-domain.com`

**How to get**:
- For local: Start your ACE server on port 9000
- For production: Get from your ACE server administrator

**Test it**:
```bash
curl $ACE_SERVER_URL/health
# Expected: {"status":"healthy"}
```

---

### ACE_API_TOKEN

**Purpose**: Authentication token for ACE server

**Format**: `ace_` followed by 48 alphanumeric characters

**Example**: `ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU`

**How to get**:
- For local development: Check your server configuration
- For production: Generate via ACE server admin interface

**Security**:
- ⚠️ Treat like a password
- ❌ Never commit to git
- ❌ Never share publicly
- ✅ Rotate regularly

**Test it**:
```bash
curl $ACE_SERVER_URL/playbook \
  -H "Authorization: Bearer $ACE_API_TOKEN" \
  -H "X-ACE-Project: $ACE_PROJECT_ID"
```

---

### ACE_PROJECT_ID

**Purpose**: Multi-tenant project isolation

**Format**: `prj_` followed by 16 hexadecimal characters

**Example**: `prj_5bc0b560221052c1`

**How to get**:
- For local development: Generate with `uuidgen | head -c 16`
- For production: Create via ACE server admin interface

**Usage**:
- Isolates patterns between projects
- Each project has its own pattern database
- Prevents pattern leakage

**Generate locally**:
```bash
echo "prj_$(uuidgen | tr '[:upper:]' '[:lower:]' | head -c 16)"
```

---

## Verification

### Check Environment Variables

```bash
# Check all required variables are set
env | grep ACE_

# Expected output:
# ACE_SERVER_URL=http://localhost:9000
# ACE_API_TOKEN=ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU
# ACE_PROJECT_ID=prj_5bc0b560221052c1
```

### Test Server Connection

```bash
# Health check
curl $ACE_SERVER_URL/health

# Get playbook (with auth)
curl $ACE_SERVER_URL/playbook \
  -H "Authorization: Bearer $ACE_API_TOKEN" \
  -H "X-ACE-Project: $ACE_PROJECT_ID"
```

### Test Plugin in Claude Code

```bash
# Start Claude Code
claude-code

# In Claude Code, run:
/ace-status

# Expected: Statistics about your pattern database
```

---

## Troubleshooting

### Plugin not loading

**Symptom**: ACE commands not available in Claude Code

**Solutions**:
1. Check environment variables are set (run `env | grep ACE_`)
2. Restart Claude Code completely
3. Check `plugin.json` exists and is valid JSON
4. Verify MCP client is built (`ls ../../mcp-clients/ce-ai-ace-client/dist/index.js`)

### "Connection refused" error

**Symptom**: Cannot connect to ACE server

**Solutions**:
1. Check server is running: `curl $ACE_SERVER_URL/health`
2. Verify `ACE_SERVER_URL` is correct (no trailing slash)
3. Check firewall/network settings
4. For localhost: Ensure server is running on port 9000

### "Unauthorized" error

**Symptom**: 401/403 errors from server

**Solutions**:
1. Verify `ACE_API_TOKEN` is correct
2. Check token hasn't expired
3. Ensure token has correct format (`ace_...`)
4. Check server logs for authentication errors

### "Project not found" error

**Symptom**: Server rejects requests for project ID

**Solutions**:
1. Verify `ACE_PROJECT_ID` format is correct (`prj_...`)
2. Create project on server if needed
3. Check server supports multi-tenant mode

---

## Production Deployment

### For Distributed Plugins

If distributing your plugin to others:

1. **Use the template**: Include only `plugin.template.json`
2. **Documentation**: Provide this CONFIGURATION.md
3. **Don't include**: Never include `plugin.json` with real credentials
4. **Add to .gitignore**:
   ```
   plugins/ace-orchestration/plugin.json
   plugins/ace-orchestration/.env
   ```

### For Production Server

When deploying to production:

1. **Deploy ACE server** to cloud (AWS/GCP/Azure)
2. **Configure SSL/HTTPS**: Use Let's Encrypt or cloud provider
3. **Set production URL**: Update `ACE_SERVER_URL` to `https://ace.your-domain.com`
4. **Generate production tokens**: Use strong random tokens
5. **Project management**: Set up project creation workflow

---

## Example Configurations

### Local Development

```bash
# ~/.zshrc or ~/.bashrc
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU"
export ACE_PROJECT_ID="prj_5bc0b560221052c1"
```

### Production (Team Shared Server)

```bash
# ~/.zshrc or ~/.bashrc
export ACE_SERVER_URL="https://ace.yourcompany.com"
export ACE_API_TOKEN="ace_prod_token_from_admin"
export ACE_PROJECT_ID="prj_your_project_id"
```

### Multi-Project Setup

```bash
# ~/.zshrc or ~/.bashrc

# Default project
export ACE_SERVER_URL="https://ace.yourcompany.com"
export ACE_API_TOKEN="ace_your_token"
export ACE_PROJECT_ID="prj_default_project"

# Function to switch projects
ace_use_project() {
  case $1 in
    frontend)
      export ACE_PROJECT_ID="prj_frontend_abc123"
      ;;
    backend)
      export ACE_PROJECT_ID="prj_backend_def456"
      ;;
    *)
      echo "Unknown project: $1"
      return 1
      ;;
  esac
  echo "Switched to project: $1 ($ACE_PROJECT_ID)"
}

# Usage: ace_use_project frontend
```

---

## Security Best Practices

1. **Rotate tokens regularly**: Generate new tokens every 90 days
2. **Use project-specific tokens**: Don't share tokens across projects
3. **Limit token scope**: If server supports it, use read-only tokens for viewing
4. **Monitor usage**: Check server logs for suspicious activity
5. **Revoke compromised tokens**: Immediately revoke if leaked
6. **Use HTTPS in production**: Always use SSL/TLS for production servers

---

## Quick Reference

### Files

- `plugin.template.json` - Template with env vars (safe to commit)
- `plugin.json` - Your config with real values (DON'T commit)
- `.env.example` - Example environment file (safe to commit)
- `CONFIGURATION.md` - This guide

### Environment Variables

| Variable | Required | Format | Example |
|----------|----------|--------|---------|
| `ACE_SERVER_URL` | Yes | URL | `http://localhost:9000` |
| `ACE_API_TOKEN` | Yes | `ace_...` | `ace_wFIuXzQ...` |
| `ACE_PROJECT_ID` | Yes | `prj_...` | `prj_5bc0b56...` |
| `ACE_CACHE_TTL_MINUTES` | No | Number | `5` |

### Commands

```bash
# Set up environment variables
echo 'export ACE_SERVER_URL="..."' >> ~/.zshrc
echo 'export ACE_API_TOKEN="..."' >> ~/.zshrc
echo 'export ACE_PROJECT_ID="..."' >> ~/.zshrc
source ~/.zshrc

# Create plugin.json from template
cp plugin.template.json plugin.json

# Test configuration
curl $ACE_SERVER_URL/health
/ace-status  # In Claude Code
```

---

## Support

If you have issues:

1. Check this guide
2. Verify environment variables are set
3. Test server connection manually
4. Check server logs
5. File an issue on GitHub

---

**Remember**: Never commit credentials to git! Always use environment variables or configuration management.
