"""Shim de sys.path para o app de cadastros (usa imports absolutos `src.*`).

Em produção o `app.py` insere a pasta do app no `sys.path`; os testes replicam
o mesmo shim para importar `src.*` diretamente.
"""

from __future__ import annotations

import sys
from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "apps" / "coleta_cadastros_escolas"
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))
