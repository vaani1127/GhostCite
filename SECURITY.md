# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Report them privately with
GitHub's [private vulnerability reporting](https://github.com/vaani1127/GhostCite/security/advisories/new).
We aim to acknowledge reports within 3 days and to fix confirmed issues as quickly as
possible.

If you find a leaked SerpApi key anywhere in this repository or its history, report it
the same way. Do not use the key.

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## How GhostCite protects your key and your data

* **The API key**
  * It is read only from the environment or a local `.env` file, which is gitignored and
    excluded from Docker builds.
  * It is held in a `SecretStr` and never logged.
  * It is redacted from every error message. Exceptions from the HTTP library, which
    contain the request URL, are never chained.
* **Cache and recordings**
  * Cache keys and stored responses never contain the key.
  * Recorded responses are sanitized: no key, no links into the account's search
    archive.
  * A test fails if a committed fixture contains a key-shaped string, an e-mail address
    or such a link.
* **The Account API response** contains the key and the account e-mail. GhostCite reads
  only the two count fields and discards the rest.
* **The web UI**
  * It binds to 127.0.0.1 by default and warns about any other interface. The Docker
    setup publishes it on 127.0.0.1 only.
  * It sets strict security headers and a Content Security Policy, uses no cookies, no
    analytics and no external assets, and never writes uploads to disk.
  * It limits upload size, references per job, concurrent jobs, and searches per job and
    per server.
* **HTML reports** escape all text from search results and only link to http(s) URLs.
* **Secret scanning.** gitleaks runs as a pre-commit hook and in CI over the full git
  history.

## If your key leaks

Rotate it immediately at <https://serpapi.com/manage-api-key>, then update your `.env`
file and any CI secrets.
