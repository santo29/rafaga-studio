# Security policy · Política de seguridad

## Reporting a vulnerability · Reportar una vulnerabilidad

Please **do not open a public issue**. Report it privately through GitHub:
**Security → Report a vulnerability** on this repository (private vulnerability reporting).

Include what you found, how to reproduce it and the impact you expect. You will get an answer within 7 days. Once it is
fixed, you will be credited in the changelog unless you prefer otherwise.

## Scope · Qué cubre

Especially interesting:

- Ways to leak the user's API keys (stored encrypted with DPAPI in `datos/claves.json`) or send them to the wrong host.
- Ways for a web page, a downloaded video, an AI answer or an MCP call to read local files, reach the local network or
  run code.
- Supply-chain issues in the installer (`instalador/rafaga.iss`) or the pinned dependencies (`requirements.lock`).

Out of scope: problems in third-party AI services themselves, and attacks that need full control of the user's
Windows account.

## Contacto

- **Security vulnerabilities · Vulnerabilidades:** GitHub private vulnerability reporting (above).
- **Code of conduct, privacy requests and other private matters · Conducta, privacidad y otros temas privados:**
  the same private report form, choosing a clear title (for example "Privacy request"). The owner answers within
  7 days.
- **Everything else · Todo lo demás:** [Issues](../../issues) or [Discussions](../../discussions).

## How the app protects users · Cómo protege la app

See the "Security" section of the [privacy notice](PRIVACIDAD.md) and the offline security test suite
(`pruebas/seguridad.py`).
