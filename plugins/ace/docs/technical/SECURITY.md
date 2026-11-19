# Security Configuration - ACE Plugin

**Date**: 2025-01-21
**Version**: 3.0.0

---

## ✅ Security Improvements Applied

### Issue: Hardcoded Credentials

**Problem**: `plugin.json` contained hardcoded:
- ACE server URL
- API token
- Project ID

**Risk**: If committed to public repo, anyone could:
- Access your ACE server
- View/modify your patterns
- Impersonate your project

---

## 🔒 Solution: Environment Variables

### Files Created

1. **`plugin.template.json`**
   - Template with `${env:VAR_NAME}` placeholders
   - ✅ Safe to commit to git
   - Used for distribution

2. **`.env.example`**
   - Example environment variable configuration
   - ✅ Safe to commit to git
   - Shows users what to configure

3. **`CONFIGURATION.md`**
   - Complete setup guide
   - Security best practices
   - Troubleshooting help

4. **`.gitignore`** (updated)
   - Ignores `plugin.json` (with real credentials)
   - Ignores `.env` files
   - Prevents accidental commits

---

## 🛡️ Security Checklist

### Before Distributing

- [ ] Remove `plugin.json` from git (if already committed)
- [ ] Include `plugin.template.json` instead
- [ ] Add `.gitignore` to ignore `plugin.json`
- [ ] Include `CONFIGURATION.md` guide
- [ ] Include `.env.example` template

### For Users

- [ ] Copy `plugin.template.json` to `plugin.json`
- [ ] Set environment variables in shell profile
- [ ] Never commit `plugin.json` with real credentials
- [ ] Rotate API tokens regularly
- [ ] Use HTTPS in production

---

## 📋 Current Configuration

### Template (plugin.template.json)

```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/../../mcp-clients/ce-ai-ace-client/dist/index.js"],
      "env": {
        "ACE_SERVER_URL": "${env:ACE_SERVER_URL}",
        "ACE_API_TOKEN": "${env:ACE_API_TOKEN}",
        "ACE_PROJECT_ID": "${env:ACE_PROJECT_ID}"
      }
    }
  }
}
```

### Environment Setup

```bash
# Add to ~/.zshrc or ~/.bashrc
export ACE_SERVER_URL="https://ace-api.code-engine.app"
export ACE_API_TOKEN="ace_your_token_here"
export ACE_PROJECT_ID="prj_your_project_id"
```

---

## 🚨 What NOT to Do

### ❌ DON'T commit plugin.json

```bash
# Bad - exposes credentials
git add plugins/ace-orchestration/plugin.json
git commit -m "Add config"
git push
```

### ❌ DON'T hardcode credentials

```json
{
  "env": {
    "ACE_API_TOKEN": "ace_xxxxxxxxxxxxxxxx"
  }
}
```

### ❌ DON'T share tokens publicly

```bash
# Bad - token visible in public repo
export ACE_API_TOKEN="ace_xxxxxxxxxxxxxxxx"
```

---

## ✅ What TO Do

### ✅ DO use environment variables

```bash
# Good - loads from environment
export ACE_API_TOKEN="$(cat ~/.ace/token)"
```

### ✅ DO use the template

```bash
# Good - safe to commit
git add plugins/ace-orchestration/plugin.template.json
git commit -m "Add plugin template"
```

### ✅ DO document setup

Include CONFIGURATION.md in your repository so users know how to configure safely.

---

## 🔐 Token Management

### Generate Secure Tokens

```bash
# Generate strong random token
python3 -c "import secrets; print('ace_' + secrets.token_urlsafe(48)[:48])"

# Or use openssl
echo "ace_$(openssl rand -base64 36 | tr -d '/+=' | head -c 48)"
```

### Rotate Tokens Regularly

```bash
# 1. Generate new token
NEW_TOKEN=$(python3 -c "import secrets; print('ace_' + secrets.token_urlsafe(48)[:48])")

# 2. Update server to accept both tokens
# (allows graceful migration)

# 3. Update environment variable
export ACE_API_TOKEN="$NEW_TOKEN"

# 4. Restart Claude Code

# 5. Remove old token from server
```

### Store Tokens Securely

```bash
# Option 1: Shell profile
echo "export ACE_API_TOKEN='$(cat ~/.ace/token)'" >> ~/.zshrc

# Option 2: Keychain (macOS)
security add-generic-password -a "$USER" -s "ACE_API_TOKEN" -w "ace_..."

# Option 3: Password manager
# Store in 1Password, LastPass, etc.
```

---

## 🔍 Security Audit

### Check for Exposed Credentials

```bash
# Search git history for tokens
git log -p | grep -i "ace_"

# Check current files
grep -r "ace_[a-zA-Z0-9_-]" . --exclude-dir=node_modules

# Scan for hardcoded URLs
grep -r "https://ace-api.code-engine.app" . --exclude="*.md"
```

### Remove Committed Credentials

If you've already committed credentials:

```bash
# Use git filter-branch (nuclear option)
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch plugins/ace-orchestration/plugin.json' \
  --prune-empty --tag-name-filter cat -- --all

# Force push (WARNING: destructive)
git push origin --force --all
git push origin --force --tags

# Revoke the exposed token immediately!
```

---

## 📊 Security Levels

### Level 1: Local Development (Current)
```bash
ACE_SERVER_URL="https://ace-api.code-engine.app"
ACE_API_TOKEN="ace_dev_token_12345"
```

- ✅ Quick setup
- ✅ Easy testing
- ⚠️ Token in plain text
- ⚠️ No encryption

### Level 2: Production with HTTPS
```bash
ACE_SERVER_URL="https://ace.your-domain.com"
ACE_API_TOKEN="ace_prod_xxxxx"
```

- ✅ Encrypted in transit
- ✅ Token in environment
- ⚠️ Still in shell history

### Level 3: Secrets Management
```bash
ACE_SERVER_URL="https://ace.your-domain.com"
ACE_API_TOKEN="$(aws secretsmanager get-secret-value --secret-id ace-token --query SecretString --output text)"
```

- ✅ Token in secrets manager
- ✅ Rotated automatically
- ✅ Audited access
- ✅ Production ready

---

## 🚀 Production Deployment

### Pre-deployment Checklist

- [ ] Server deployed with HTTPS
- [ ] Unique tokens per user/project
- [ ] Token rotation policy in place
- [ ] Monitoring and alerts configured
- [ ] plugin.template.json tested
- [ ] CONFIGURATION.md reviewed
- [ ] Security audit completed

### Post-deployment

- [ ] Monitor access logs
- [ ] Set up token expiration
- [ ] Implement rate limiting
- [ ] Regular security reviews
- [ ] Incident response plan

---

## 📚 Resources

- **Configuration Guide**: [CONFIGURATION.md](./CONFIGURATION.md)
- **Plugin README**: [README.md](./README.md)
- **Environment Template**: [.env.example](./.env.example)

---

## 🆘 Incident Response

### If Token is Exposed

1. **Immediately revoke** the token on server
2. **Generate new token** and update environment
3. **Restart Claude Code** to pick up new token
4. **Audit access logs** for suspicious activity
5. **Rotate all related credentials**
6. **Document the incident**

### If Server is Compromised

1. **Take server offline** immediately
2. **Revoke all tokens**
3. **Investigate breach scope**
4. **Restore from clean backup**
5. **Issue new tokens** to all users
6. **Implement additional security measures**

---

**Remember**: Security is not a one-time task. Regular audits and updates are essential!
