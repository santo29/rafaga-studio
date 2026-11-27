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
feature, add a small test next to the similar ones: engine tests go in `pruebas/__main__.py` or `pruebas/seguridad.py`;
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

- A new interface language: a new `idiomas/<code>.json` with every key of `en.json`, plus its entries in `IDIOMAS`,
  `_PAISES` and `_WINDOWS` (`motor/idioma.py`) and Edge voices in `VOCES` (`motor/desde_prompt.py`), so narration
  starts in that language. `pruebas/idioma.py` checks that no translation is missing.
- Translations and wording fixes in `idiomas/`.
- Vocal styles in `motor/cabina.py` and music genres in `motor/musica.py`.
- New subtitle styles: the entry in `motor/edicion.py` and its drawing in the ASS styles of `motor/video.py`.
- A new free provider for images or video: its call in `motor/ia.py` and its place in `ORDEN` (`motor/nubes.py`).
  It sends user data to another service, so it also needs its row in [PRIVACIDAD.md](PRIVACIDAD.md).

Look for issues labeled [good first issue](https://github.com/santo29/rafaga-studio/issues?q=is%3Aopen+label%3A%22good+first+issue%22),
and ask anything in [Discussions](https://github.com/santo29/rafaga-studio/discussions).

Busca los issues con la etiqueta [good first issue](https://github.com/santo29/rafaga-studio/issues?q=is%3Aopen+label%3A%22good+first+issue%22)
y pregunta lo que quieras en [Discussions](https://github.com/santo29/rafaga-studio/discussions).

## Licensing of contributions · Licencia de lo que aportas

Ráfaga Studio is [GPL-3.0](LICENSE): contributions are accepted under that same license. The name and logo stay
trademarks of the owner.

Ráfaga Studio tiene licencia [GPL-3.0](LICENSE): lo que aportas se acepta con esa misma licencia. El nombre y el logo
siguen siendo marcas del titular.
