# IM Session Memory

Registers every action Claude Code takes during a session.
Saves to `logs/claude_session_log.json`.

## When to use

Import and call `registrar()` **after every file write, fix, or build** so the log
stays accurate. Call it even when something fails.

## API

```python
from agent.session_memory import registrar, get_resumen

# After writing/editing a file
registrar(
    archivo="frontend/index.html",
    accion="reemplazó panel p-investigacion",
    resultado="OK",
    bytes_antes=45000,
    bytes_despues=46200,
)

# After a failed fix
registrar(
    archivo="agent/orchestrator.py",
    accion="intentó agregar retry loop",
    resultado="ERROR: SyntaxError línea 142",
)

# At end of session — print summary
import json
print(json.dumps(get_resumen(), ensure_ascii=False, indent=2))
```

## Log format

```json
{
  "sesion": "2026-05-08",
  "acciones": [
    {
      "timestamp": "14:32:07",
      "archivo": "frontend/index.html",
      "accion": "reemplazó frontend completo",
      "resultado": "OK",
      "bytes_antes": 240033,
      "bytes_despues": 95000
    }
  ]
}
```

## Rules

1. **Always log** — success AND failure, no exceptions.
2. **Use relative paths** — `frontend/index.html`, not full absolute paths.
3. **accion describes WHAT changed** — "agregó retry loop en _pm_b", not "edited file".
4. **resultado** — `"OK"` if it worked, otherwise the error message.
5. **Call at end of session** — `get_resumen()` and show the user.

## Location

- Module: `agent/session_memory.py`
- Log file: `logs/claude_session_log.json`
- Multiple sessions accumulate in the same file, indexed by date.
