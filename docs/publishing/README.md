# Publishing Documentation

Documentation for releasing and publishing the ACE Orchestration plugin.

## Contents

### Publishing Guides

- **[PUBLISHING_STRATEGY.md](./PUBLISHING_STRATEGY.md)** - Overall strategy for publishing the plugin to npm and GitHub
- **[PRE-PUBLISH-CHECKLIST.md](./PRE-PUBLISH-CHECKLIST.md)** - Comprehensive checklist before each release
- **[PUBLISH_NOW.md](./PUBLISH_NOW.md)** - Quick guide for executing a release

### Configuration

- **[GITHUB_PACKAGES_SETUP.md](./GITHUB_PACKAGES_SETUP.md)** - Setting up GitHub Packages for npm distribution

## Release Process

### Pre-Release

1. Review [PRE-PUBLISH-CHECKLIST.md](./PRE-PUBLISH-CHECKLIST.md)
2. Update version numbers in all required files
3. Update CHANGELOG.md with release notes
4. Run full test suite

### Publishing

1. Follow [PUBLISH_NOW.md](./PUBLISH_NOW.md) for step-by-step instructions
2. Create GitHub release with tag
3. Publish to npm registry
4. Verify installation works

### Post-Release

1. Verify plugin appears in marketplace
2. Test installation on clean environment
3. Monitor for issues

## Version Files to Update

When releasing, update versions in:
- `.claude-plugin/marketplace.json`
- `plugins/ace-orchestration/plugin.json`
- `mcp-clients/ce-ai-ace-client/package.json`
- `CHANGELOG.md`

## Related Documentation

- **Testing**: [../guides/TESTING_CHECKLIST.md](../guides/TESTING_CHECKLIST.md)
- **Setup**: [../guides/SETUP_INSTRUCTIONS.md](../guides/SETUP_INSTRUCTIONS.md)
- **Releases**: [../../plugins/ace-orchestration/docs/releases/](../../plugins/ace-orchestration/docs/releases/)
