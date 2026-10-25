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

## Accepted risks · Riesgos aceptados

- **yt-dlp auto-update.** On every start the app updates `yt-dlp` and `yt-dlp-ejs` from PyPI in the background
  (YouTube changes often), without pinned hashes: only prebuilt wheels, uploaded 7 days ago or more, with `--no-deps`.
  A malicious release that stays on PyPI for 7 days would run inside the app. Everything else is pinned with hashes in
  `requirements.lock`. · yt-dlp se actualiza solo (ver `app.py`); lo demás va fijado con su hash.
- **"fake-ip" proxies (Clash…).** They answer every name with 198.18.0.0/15. That range is refused unless the user
  turns on «Uso un proxy fake-ip» in «Claves de IA»; with it on, the local-network protection of downloads cannot
  work (the proxy decides where to connect). · Apagado de fábrica.
- **Agents with desktop control.** MCP calls that spend money, publish or save to memory need a "Yes" in a native
  Ráfaga Studio window. An agent that can also drive the desktop (not only the MCP tools) could click it, and could
  also unlock Ráfaga Guardia from its page.
- **Integrity manifest next to the code.** `integridad.json` lives in the app folder: whoever can rewrite the code can
  rewrite it too. It is a tripwire for programs that do not know about Ráfaga Guardia, not a signature.

## Ráfaga Guardia · El vigilante de la app

The guardian inside the app (`motor/guardia.py`, page «🛡️ Ráfaga Guardia» at the end of the menu). It protects
**Ráfaga Studio and the keys, money and data inside it, not the whole PC**: it is not an antivirus. The rules in the
code decide and lock; the AI only explains an event when you press «Explicar con IA», and its answer is shown as text,
never acted upon.

**What it records** (`datos/guardia.json`, local, the last 500 events; the app and the MCP server write to it at the
same time with a lock file and atomic replaces). Each event has a date, a type, a severity (alta/media/baja), its
origin (app, mcp, director) and a short detail with no keys, tokens, signed URLs or full paths (only the file name):

- refusals of `motor/seguro.py`: network/UNC paths and shortcuts to network shares, links and connections to the local
  network or reserved IPs (also after a redirect), "fake-ip" proxy addresses, files whose content is not their type;
- refusals of the Director: links or files that did not come from the user or the studio, tools that do not exist;
- the MCP wrapper: you said «No» to a paid/publish/memory question, an agent asked for files from outside its folder,
  a tool called while locked;
- keys: Windows (DPAPI) cannot decrypt them, the file was damaged, it was changed by another program (its hash is not
  one the app wrote), a key from another service pasted into Kling/Seedance «Conectar»;
- the studio memory refusing sensitive data;
- **integrity**: the installer ships `integridad.json` (built by `instalador/integridad.py` every time `rafaga.iss` is
  compiled) with the SHA-256 of `app.py`, `mcp_server.py`, `modal_app.py`, the launcher `.bat` and every `.py` in
  `motor/` and `ui/`. A changed, missing or extra `.py` (a planted module) is an «alta» event. Without a manifest (a
  git checkout) it says «modo desarrollo» and never alerts; an installed copy without it gets a warning.

**«Revisar ahora»** (also once at start-up, in the background) checks the integrity, that the keys file is encrypted
with DPAPI and readable, that the app is installed inside `%LOCALAPPDATA%`, that the MCP registration in Claude's
configs runs this app's `mcp_server.py` with `-s -E`, the hash of the Demucs model and the lock state.

**Lockdown («Bloqueo»).** While locked, the MCP server refuses every tool, the Director refuses anything paid,
publishing or saving to memory, and paid video, image and music calls do not start. It locks by itself only on an
«alta» integrity event or when you say «No» to an MCP agent 3 times in 10 minutes (an agent insisting); you can also
lock it by hand. **Only a person on the page can unlock it**, after a confirmation: no tool, agent or the Director
can, and if `guardia.json` is edited or broken to drop the lock while the app is open, the page puts it back and
warns. New «alta» events (also those written by the MCP process) turn the shield red and show a Windows notification.

**Limits, honestly:** an attacker who can rewrite the app's code can also rewrite the manifest (and `guardia.json`
while the app is closed); this catches tampering by malware or programs that do not know about it, and the installer
only installs under your profile, where other accounts cannot write. It does not see what happens outside the app,
and an agent that drives your mouse and keyboard could click «Sí» or unlock. Packages under `python\` (the installed
Python and its libraries) and the `__pycache__` folders are not in the manifest: the libraries are pinned by hash in
`requirements.lock` at install time.

## Contacto

- **Security vulnerabilities · Vulnerabilidades:** GitHub private vulnerability reporting (above).
- **Code of conduct, privacy requests and other private matters · Conducta, privacidad y otros temas privados:**
  the same private report form, choosing a clear title (for example "Privacy request"). The owner answers within
  7 days.
- **Everything else · Todo lo demás:** [Issues](../../issues) or [Discussions](../../discussions).

## How the app protects users · Cómo protege la app

See the "Security" section of the [privacy notice](PRIVACIDAD.md), Ráfaga Guardia above and the offline security
test suites (`pruebas/seguridad.py`, `pruebas/guardia.py`).
