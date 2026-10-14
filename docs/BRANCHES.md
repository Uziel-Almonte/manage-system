# Branch strategy

| Branch | Role |
|--------|------|
| `main` | Release branch. Merges arrive by pull request from `dev`. |
| `dev` | Integration branch. The six-week plan calls this `develop`. Day-to-day work lands here. |
| `feature/*` | Short-lived branches cut from `dev`. Open the pull request back into `dev`. |

GitHub Actions runs on pushes and pull requests to `main` and `dev`.

```bash
git checkout dev
git pull
git checkout -b feature/short-description
```

## Branch protection on `main`

Protection is a GitHub setting, not a file in this repository. A repository admin applies it once:

```bash
gh api -X PUT repos/Uziel-Almonte/manage-system/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["Build", "Unit tests", "API / contract tests", "Integration / data tests", "Coverage"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1
  },
  "restrictions": null
}
EOF
```

Until that call succeeds, `main` accepts direct pushes. The checkbox in `TODO` stays open for that reason.

## SonarCloud

SonarCloud is optional and is not part of the pull-request workflow. Connection steps are in `docs/SONARCLOUD.md`.
