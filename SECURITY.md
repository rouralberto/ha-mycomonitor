# Security policy

## Supported versions

Only the latest release receives fixes.

## Reporting a vulnerability

Please use GitHub's **private vulnerability reporting** ("Report a
vulnerability" under the repository's *Security* tab). Do not open a public
issue. You should get a reply within a week.

## Scope and sensitive data

- **API keys** (e.g. AEMET OpenData) are stored in Home Assistant's config
  entries. They are redacted from diagnostics and never logged.
- **Observation coordinates** are treated as sensitive. They are never
  exposed in entity attributes, logs or diagnostics, and exports leave them
  out unless explicitly requested.

If you find a path where either leaks, please report it as above.
