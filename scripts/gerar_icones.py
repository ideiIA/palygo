"""Gera os ícones PNG do app (192 e 512) só com a biblioteca padrão: fundo roxo, bola lima com costura.
Uso: python scripts/gerar_icones.py"""

import struct
import zlib
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "playgo" / "app"
ROXO, LIMA, ESCURO = (108, 76, 255), (183, 243, 75), (22, 22, 43)


def pixel(x: float, y: float) -> tuple[int, int, int]:
    """Coordenadas de 0 a 1."""
    dx, dy = x - 0.5, y - 0.5
    d = (dx * dx + dy * dy) ** 0.5
    if d < 0.27:
        # costura da bola: uma faixa curva escura
        faixa = abs(dy - 0.12 * ((dx / 0.27) ** 2) + 0.06)
        return ESCURO if faixa < 0.018 and abs(dx) < 0.25 else LIMA
    if d < 0.31:
        return ESCURO
    # degradê diagonal do roxo para o rosa
    t = (x + y) / 2
    return tuple(int(a + (b - a) * t) for a, b in zip(ROXO, (255, 61, 129)))


def png(tamanho: int) -> bytes:
    linhas = bytearray()
    for j in range(tamanho):
        linhas.append(0)
        for i in range(tamanho):
            linhas.extend(pixel((i + 0.5) / tamanho, (j + 0.5) / tamanho))

    def bloco(tipo: bytes, dados: bytes) -> bytes:
        corpo = tipo + dados
        return struct.pack(">I", len(dados)) + corpo + struct.pack(">I", zlib.crc32(corpo) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", tamanho, tamanho, 8, 2, 0, 0, 0)) + bloco(b"IDAT", zlib.compress(bytes(linhas), 9)) + bloco(b"IEND", b"")


if __name__ == "__main__":
    for t in (192, 512):
        (DESTINO / f"icon-{t}.png").write_bytes(png(t))
        print(f"icon-{t}.png")
