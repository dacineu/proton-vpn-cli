# TODO List: Achievements & Future Improvements

**Release**: 0.1.8
**Date**: 2026-03-15

---

## ✅ Achieved in This Release

### Core Features
- [x] Enable free tier country/city server selection in `connect` command
- [x] Implement `protonvpn servers list` command with filtering
- [x] Support filters: `--country`, `--city`, `--p2p`, `--securecore`, `--tor`
- [x] Enforce tier restrictions (free users cannot use feature flags)
- [x] Display server details in formatted table (Server, Country, City, Features)

### Code Quality
- [x] Refactor: Moved `FEATURES_TO_DISPLAY` to shared `command_utils.py`
- [x] Refactor: Moved `compose_requested_features()` to shared utility
- [x] Remove duplicate code in `server.py` and `location_discovery.py`
- [x] Clean up unused imports
- [x] All 74 unit tests passing

### Documentation
- [x] `CODEBASE_ANALYSIS.md` - Comprehensive project analysis
- [x] `RELEASE_0.1.8.md` - User-facing release notes
- [x] `IMPLEMENTATION_DOCUMENTATION_0.1.8.md` - Technical implementation details
- [x] Updated `versions.yml` with version 0.1.8 entry
- [x] Inline code comments and docstrings

### Release Process
- [x] Created git commit with conventional commit message
- [x] Created annotated git tag `v0.1.8`
- [x] Verified all modified files are staged and committed
- [x] Confirmed test suite passes without errors

---

## 🚧 Future Improvements (Backlog)

### Testing (High Priority)
- [ ] Add unit tests for `servers list` command
  - [ ] Basic listing with mock server data
  - [ ] Country filter test
  - [ ] City filter test
  - [ ] Feature filter test (P2P, Secure Core, Tor)
  - [ ] Tier restriction test (free user with --p2p fails)
  - [ ] Authentication required test
  - [ ] No servers match test
- [ ] Add integration tests for full flow (signin → list → connect)
- [ ] Increase test coverage for `Controller.find_logical_server()` with free tier
- [ ] Test edge cases: empty server list, invalid city names, case sensitivity

### Documentation (Medium Priority)
- [ ] Update README.md with new `servers list` command
- [ ] Add examples for free tier usage in README
- [ ] Create man page for CLI (if project maintains one)
- [ ] Document command structure in docs/
- [ ] Add migration guide from 0.1.7 to 0.1.8

### Features & Enhancements (Medium Priority)
- [ ] Add `--limit` option to `servers list` for pagination
- [ ] Add `--sort` option (by name, country, city)
- [ ] Add `--output json` for machine-readable format
- [ ] Add server load/capacity metrics to listing (if available from API)
- [ ] Add ping/latency column (if measurable)
- [ ] Implement `protonvpn servers connect` with interactive selection
- [ ] Add ability to save preferred servers to config
- [ ] Show free vs paid servers visually in listing (e.g., marker column)

### Refactoring (Low Priority)
- [ ] Extract `ServerFilter` class to encapsulate filtering logic
- [ ] Split `Controller` into smaller services (ServerFinder, ConnectionManager)
- [ ] Create base command class to reduce boilerplate
- [ ] Move all CLI-specific formatting to separate module
- [ ] Define constants for timeout values (currently hardcoded 10s)
- [ ] Add type hints to public methods in Controller for better IDE support

### UX Improvements (Low Priority)
- [ ] Colorize output (green for free servers, blue for paid)
- [ ] Add progress indicator during server list fetch
- [ ] Show count of matching servers vs total
- [ ] Improve error message for city not found (suggest closest match)
- [ ] Cache server list locally to reduce API calls for listing
- [ ] Add `--refresh` flag to force server list update

### Build & Release (Low Priority)
- [ ] Set up automatic package builds in CI/CD
- [ ] Create GitHub/GitLab release automatically from tag
- [ ] Add automated upload to package repositories
- [ ] Generate changelog from git commits instead of versions.yml
- [ ] Verify devtools submodule is always available (vendoring?)

### Code Quality (Ongoing)
- [ ] Run pylint and fix remaining warnings
- [ ] Address `# pylint: disable=` comments where possible
- [ ] Reduce cyclomatic complexity in `find_logical_server`
- [ ] Add more comprehensive error handling in `servers list`
- [ ] Validate server list data structure before processing
- [ ] Consider using dataclasses for server display rows

---

## Known Issues from Implementation

1. **No tests for `servers list`** - Command works but lacks test coverage
2. **Devtools submodule dependency** - `scripts/create_changelogs.py` fails if submodule not initialized
3. **Hard-coded timeout values** - 10 seconds appears in multiple places
4. **Controller complexity** - `find_logical_server` has ~50 lines with many branches
5. **Feature filter duplication** - Exclusion logic is subtle and may be error-prone if extended
6. **No pagination** - Server list could become large; `servers list` shows all at once
7. **Error messages in exception handlers** - Some still reference old behavior (need verification)

---

## Milestones for Next Release (0.1.9 or 0.2.0)

### Must-Have
- [ ] All new features have comprehensive test coverage (>80%)
- [ ] Update README with new commands and free tier capabilities
- [ ] Fix any bugs discovered in 0.1.8 usage

### Nice-to-Have
- [ ] JSON output option for scripting
- [ ] Interactive server selection
- [ ] Server metrics (load, ping) in listing
- [ ] Pagination support
- [ ] Colorized output

---

## Release Checklist (for future)

- [ ] Update `versions.yml` with new version
- [ ] Run full test suite: `pytest -v`
- [ ] Lint code: `flake8` / `pylint`
- [ ] Update README.md
- [ ] Update CHANGELOG.md
- [ ] Build packages (DEB and RPM)
- [ ] Test package installation in clean VM
- [ ] Create git tag with annotated message
- [ ] Push tag to remote
- [ ] Create GitHub/GitLab release from tag
- [ ] Publish packages to repository
- [ ] Announce release to users

---

**Current Release Status**: ✅ Production Ready (0.1.8)
