---
name: boss-zhipin-scraper
description: Search and analyze BOSS直聘 job listings through the repository's low-frequency Chrome CDP CLI. Use when the user asks to search zhipin.com jobs, inspect job details, export JSON/CSV, or summarize already-collected job data.
---

# BOSS直聘 job search

Use the repository's existing CLI. Do not reimplement the BOSS request flow in a new script and do not add a second browser automation layer.

## Before running commands

1. Work from the repository root and confirm that `scripts/boss_cdp_raw.py` exists.
2. Confirm Python 3.10+ and the dependencies from `requirements.txt` are available.
3. Ask the user to log in manually in the dedicated CDP browser when needed. The skill must not request, store, or handle SMS codes, passwords, CAPTCHA answers, or cookies.
4. Keep searches low frequency: start with one page and no more than three detail pages unless the user explicitly asks for a larger scope.

## Standard workflow

Run the environment check first:

```text
python scripts/boss_cdp_raw.py --check --cdp-port 9222
```

If the dedicated browser is not running, start it and wait for the user to finish login:

```text
python scripts/boss_cdp_raw.py --setup-chrome --cdp-port 9222
```

Then search a small result set:

```text
python scripts/boss_cdp_raw.py --keyword "AI Agent" --city 上海 --pages 1 --no-detail --output ~/.boss-zhipin-scraper/job-result/jobs.json
```

For selected jobs, fetch details with `--detail` and `--max-details 3`, or use the repository's documented two-stage workflow when available. Prefer JSON output for machine analysis and CSV only when the user asks for a spreadsheet-friendly export.

After data already exists, use the repository summary script instead of rereading unrelated personal files:

```text
python scripts/job_summary.py --top 15
```

## Safety and stopping rules

- Use only the user's dedicated CDP browser and the repository's isolated profile. Never copy the main browser profile by default.
- Do not send messages, upload resumes, submit applications, or perform other external job-seeking actions. Those actions remain under the user's control.
- Do not bypass CAPTCHA, spoof browser fingerprints, hide CDP, rotate proxies, or evade BOSS security controls.
- If BOSS returns `code 37`, an abnormal-environment message, a CAPTCHA, or an `about:blank` redirect, stop immediately. Explain the observed condition and wait for the user; do not retry repeatedly.
- Do not treat missing or DOM-obfuscated salary text as reliable plaintext. Preserve the CLI's `salary_source` field and report uncertainty.
- Do not read or commit `job-data`, browser profiles, cookies, resumes, application materials, or other local personal data unless the user explicitly provides a specific file for analysis.

## Reporting

Report the exact command, output path, number of pages/details requested, and any skipped or failed step. Distinguish data returned by BOSS from analysis or recommendations inferred from the saved results.
