"""Banner (cabeçalho) padrão das aplicações do HUB.

Todas as telas abrem com o mesmo cabeçalho — logo, título e subtítulo — sobre
o cartão ``.title-container`` definido no CSS global do HUB (``app.py``).
Centralizar o markup garante que nenhum módulo abra a tela com um modelo
diferente dos demais.
"""

from __future__ import annotations

from typing import Any


def banner_titulo(
    st_mod: Any,
    titulo: str,
    subtitulo: str,
    logo_base64: str | None = None,
    subtitulo_sem_logo: str | None = None,
) -> None:
    """Renderiza o cabeçalho padrão do HUB.

    ``titulo``/``subtitulo`` — textos do cabeçalho.
    ``logo_base64`` — logo em base64; sem ela, o cabeçalho fica só com os textos.
    ``subtitulo_sem_logo`` — subtítulo alternativo usado quando não há logo.
    """
    if logo_base64:
        html = f"""
        <div class="title-container" style="display:flex; align-items:center; gap:1.5rem;">
            <img src="data:image/png;base64,{logo_base64}"
                 style="width:68px; height:68px; border-radius:12px;
                        box-shadow:0 4px 12px rgba(0,0,0,0.2);
                        background:#fff; padding:5px;" />
            <div>
                <h1 style="margin:0; padding:0; line-height:1.2; color:white !important;">
                    {titulo}
                </h1>
                <p style="margin-top:0.3rem; color:#bfdbfe; font-size:1rem; margin-bottom:0;">
                    {subtitulo}
                </p>
            </div>
        </div>"""
    else:
        html = f"""
        <div class="title-container">
            <h1>{titulo}</h1>
            <p>{subtitulo_sem_logo or subtitulo}</p>
        </div>"""
    st_mod.markdown(html, unsafe_allow_html=True)
