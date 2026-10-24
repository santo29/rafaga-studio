# Contributing to Ráfaga Studio · Cómo contribuir

Thanks for helping! · ¡Gracias por ayudar! The code, comments and UI texts are in Spanish; issues and pull requests
are welcome in Spanish or English.

## Before you start · Antes de empezar

1. Read the [Code of Conduct](CODE_OF_CONDUCT.md).
2. For anything bigger than a small fix, open an issue first so we can agree on the approach.
3. Security problems never go in public issues: follow [SECURITY.md](SECURITY.md).

## Set up · Preparar el entorno

```bat
git clone https://github.com/santo29/rafaga-studio.git
cd rafaga-studio
"Ráfaga Studio.bat"
```

The `.bat` creates `.venv` with the exact, hash-pinned versions of `requirements.lock`.

## Run the tests · Pasar las pruebas

```bat
.venv\Scripts\python -m pruebas
```

The whole suite runs offline, with fake AI services and no keys. **Every pull request must pass it.** If you add a
feature, add a small test next to the similar ones: engine tests go in `pruebas/__main__.py` or `pruebas/seguridad.py` (MIT);
the other `pruebas/*.py` test the app.

## Code style · Estilo del código

- Write like the surrounding code: Spanish names and comments, short functions, comments only for the *why*.
- Every text the user sees goes through `t("…")` and needs its translation in `idiomas/en.json`, `pt.json` and
  `fr.json` (`pruebas/idioma.py` checks it).
- Never trust input from outside (files, links, AI answers, MCP calls): use the checks in `motor/seguro.py`.
- Keys and tokens never go in code, logs, URLs or tests. Tests use fake keys.
- No new dependency for a few lines of code. New dependencies go in `requirements.txt` and the lock is regenerated
  with `instalador/actualizar_lock.py`.

## Good first contributions · Buenas primeras contribuciones

- A new free provider in `motor/nubes.py` (images, video, voice).
- Vocal styles in `motor/cabina.py` and music genres in `motor/musica.py`.
- Translations and wording fixes in `idiomas/`.
- New subtitle styles, filters and effects for the editor (`motor/edicion.py`).

## Licensing of contributions · Licencia de lo que aportas

The engine (`motor/`, `idiomas/`, `mcp_server.py`, `modal_app.py`, `pruebas/__main__.py`, `pruebas/seguridad.py`, `ejemplos/`)
is MIT: contributions to it are accepted under the MIT license. The desktop app (`app.py`, `ui/`) is source-available
with all rights reserved, and so are the other tests (`pruebas/*.py`), `pruebas/real.py`, `instalador/actualizar_lock.py` and
`instalador/`: by contributing to them you agree that the owner may use your contribution in Ráfaga Studio
under its own license.
