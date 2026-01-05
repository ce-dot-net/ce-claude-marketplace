# ACE Hook Testing Strategy Analysis
**Date**: 2026-01-05
**Branch**: feat/bats-hook-testing
**Analysts**: TDD Orchestrator + Architecture Reviewer + Lead Engineer

---

## Executive Summary

**Current State**: 32 tests covering 1 of 8 hooks (12.5% coverage)

**Quality Grade**: A- (excellent behavioral coverage, proven regression detection)

**Key Finding**: Infrastructure is solid but needs refactoring BEFORE adding more hooks

**Recommendation**: Refactor + expand to 67 total tests covering top 4 priority hooks

---

## Decision Points for HITL

### Option A: PR Now, Expand Later
- Ship Issue #3 regression protection immediately
- 7 of 8 hooks remain untested
- Effort: 0 hours (ready now)

### Option B: Refactor + Priority Hooks (Recommended)
- Clean foundation for expansion
- Cover critical security gate + complex hooks
- 4 of 8 hooks tested (50%)
- Effort: 17-24 hours over 4 sprints

### Option C: Minimum Refactor + 1 High-Risk Hook
- Ship faster than Option B
- Addresses highest-risk hook only
- Effort: 10-14 hours

---

## Recommended: Option B

**Why**:
1. ace_permission_request = security gate (MUST test)
2. ace_pretooluse = 270 LOC, complex algorithms (HIGH RISK)
3. ace_posttooluse = ground truth database (CRITICAL)
4. Refactoring prevents technical debt

**Timeline**: 3 weeks, 4 sprints

See full analysis in this file for details.
