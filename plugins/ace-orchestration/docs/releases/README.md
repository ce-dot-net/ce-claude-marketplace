# ACE Orchestration - Release Documentation

Release-specific notes, test results, and migration guides.

## Contents

### Version 3.2

- **[RELEASE_NOTES_v3.2.md](./RELEASE_NOTES_v3.2.md)** - Release notes for version 3.2.x series
- **[TEST_RESULTS_v3.2.md](./TEST_RESULTS_v3.2.md)** - Comprehensive test results for version 3.2

## Current Version

See [../../CHANGELOG.md](../../CHANGELOG.md) for the complete version history.

Latest release: Check [GitHub Releases](https://github.com/ce-dot-net/ce-claude-marketplace/releases)

## Version History Highlights

### v3.2.10+ (2025-10-23)
- **Documentation**: Complete paper compliance verification (95% alignment)
- **Enhancement Roadmap**: Detailed analysis of missing 5% and implementation priorities
- **Architecture Updates**: Comprehensive documentation of all components
- **Bug Fix**: Trajectory format documentation (array of objects)
- Updated examples in ace-learning skill
- Added IMPORTANT warnings

### v3.2.9 (2025-10-23)
- **Feature**: Version detection and auto-update for `/ace-claude-init`
- Smart update process preserves user content

### v3.2.8 (2025-10-23)
- **Feature**: MANDATORY skill usage rules
- Three-layer enforcement for consistent skill triggering
- Aggressive skill descriptions

### v3.2.6 - v3.2.7
- Various improvements and bug fixes

### v3.2.4
- Complete automatic learning cycle with skills
- Server-side intelligence

## Upgrade Path

See [../../README.md](../../README.md) for upgrade instructions.

Quick upgrade:
```bash
claude plugin update ace-orchestration
/ace-claude-init  # Update project CLAUDE.md
```

## Related Documentation

- **Main Changelog**: [../../CHANGELOG.md](../../CHANGELOG.md)
- **Installation**: [../guides/INSTALL.md](../guides/INSTALL.md)
- **Configuration**: [../guides/CONFIGURATION.md](../guides/CONFIGURATION.md)
