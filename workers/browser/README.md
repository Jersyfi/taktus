# `browser` — web pages checked in headless Chromium

A worker behind the worker contract v1 that looks at a web application the way a person does:
it opens a page, does what a flow does there — types, clicks, follows a path — and reads what
the page shows (ADR-0218). A step names the capability `browser.check` and gives the worker its
checks in `task.inputs.checks`. Each check is one step of the assignment, and the step's
artifact `check-N` is its report.

```
python3 workers/browser/worker.py --port 9000
```

## A check

| Field | Means |
|---|---|
| `url` | the page to open |
| `name` | what the report calls the check; the URL where it names none |
| `steps` | what is done on the page before it is read, in order: `{click: selector}`, `{fill: selector, value: text}` or `{fill: selector, value_env: NAME}`, `{press: key}`, `{goto: path}`, `{wait: selector}` |
| `expect` | texts the page must show |
| `absent` | texts the page must not show |
| `status` | the HTTP status the page must answer with; by default any below 400 |
| `security` | `true`: the check is also a passive security check (ADR-0234); a task's `inputs.security: true` makes every check one |

A passive security check reports, under `security`, whether the page was served over TLS and
with which protocol, which protecting response headers are missing, which headers name the
server's software, which cookies lack `Secure` or `HttpOnly` (by name), and which of a fixed list
of well-known paths — `/.git/HEAD`, `/.git/config`, `/.env`, `/.svn/entries`, `/.htpasswd`,
`/.aws/credentials`, `/id_rsa`, `/server-status`, `/phpinfo.php`, `/.DS_Store` — answers 200
with the content its name promises. Every finding makes the check not pass. Nothing is tried on
the application: no payload, no form, no guessed identifier; no header's or cookie's value and
nothing an exposed path holds enters the report.

The report names the status, the title, each expected text found or not, each absent text seen
or not, each step done or why not, the console's errors, the requests that failed, the hosts
refused, the digest of the page's visible text and of a full-page screenshot, and `passed`. A
check that does not hold is a finding, not a failure of the step: a process reads `passed` and
decides by rule. The step fails only where the browser itself could not run.

## The frame

Every host a check's URL names, and every host the task declares in `task.inputs.hosts`, is held
against the frame's `allowed_hosts` before the browser starts, and a refused host stops the
assignment (W-13). Inside the browser every request to any other host is refused and named in
the report's `blocked`, so that a page cannot reach what the frame does not allow.

A credential arrives by its name. A step `{fill: selector, value_env: NAME}` types the value of
the credential the execution adapter put into the environment under that name; no event, no
artifact and no log line carries it.

## How it is built

Everything the contract asks around the steps — capabilities, the estimate, the event stream,
consumption and a boundary with a checkpoint after every step, a stop at a boundary, refusal
outside the frame, the limits, steering, handover, the outbound binding, the faults — is the
reference worker's (`workers/script/`). `worker.py` loads that file and gives it other steps:
it declares `browser.check`, `browser.headless` and `workspace.isolated`, plans a step per
check, and estimates each at `TAKTUS_BROWSER_CHECK_SECONDS` compute seconds (8 by default).
`browse.py` drives headless Chromium through Playwright for one check.

Its image is `Dockerfile` in this directory (`docker build -f workers/browser/Dockerfile .`):
the driver at the exact versions `requirements.txt` names — the extra `browser` of
`pyproject.toml`, which the tests run with — and the headless Chromium of that release.
Playwright brings its own Node runtime, so the image scan judges the driver's release too: a
driver is raised when its runtime carries a fixed high or critical vulnerability. That runtime
needs `libatomic1`, which the image installs before the driver.

## Proven

`tests/conformance/test_worker_v1_browser.py` runs the conformance suite against it, checking a
served page three times, and two faults of the frame, each failing exactly its check.
`tests/workers/test_browser_worker.py` holds a check to its report: a flow typed and clicked, a
host refused inside the browser, a credential typed and never reported, a check that does not
hold reported as a finding. Both need Chromium (`uv run playwright install chromium`) and say so
where it is missing. The removal test is pending, so it is not *verified*.
