# Baseline before YAML import work

**Use this if the YAML import work causes regressions and you need to revert.**

| Item | Value |
|------|--------|
| **Git tag** | `pre-yaml-import-v1.0.66` |
| **Commit** | `2a76bdb` (full: `2a76bdb5996d7e1d7c86a5fa3ae9431e43f85cd1`) |
| **Addon version** | 1.0.66 |
| **Frontend version** | 0.71.48 |
| **Date marked** | 2025-03-18 |

## Revert to this state

**Option A – Discard all local changes and match the tag exactly**
```bash
git fetch --tags
git checkout pre-yaml-import-v1.0.66
# Or to move branch back to this point (destructive):
git reset --hard pre-yaml-import-v1.0.66
```

**Option B – Create a new branch from the baseline (keep current branch as-is)**
```bash
git checkout -b recovery-pre-import pre-yaml-import-v1.0.66
```

**Option C – Compare current code to baseline**
```bash
git diff pre-yaml-import-v1.0.66 --stat
```

Do not delete the tag `pre-yaml-import-v1.0.66` until you are confident the YAML import work is stable.
