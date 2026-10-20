#!/usr/bin/env python3
"""Vigia de fora: pergunta a um webhook se o serviço está de pé e avisa no WhatsApp quando cai e quando volta.

Variáveis (secrets do repositório): VIGIA_URL, VIGIA_TOKEN, ALERTA_URL, ALERTA_TOKEN, ALERTA_NUMERO.
O webhook responde só 200 (ok) ou 500 (falha), sem dado. O estado entre rodadas fica no cache do Actions.

Regra (anti-spam): "caiu" depois de 2 falhas seguidas, "continua fora" 1x por hora, "voltou" na primeira
rodada boa. O job só fica vermelho nos avisos de queda (o GitHub manda e-mail e push uma vez).
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SEGUIDAS = 2
LEMBRAR = 3600


def _min(seg: float) -> str:
    return f"{round(seg / 60)} min"


def transicao(estado: dict, probs: list[str], agora: float) -> tuple[dict, str | None]:
    n = estado.get("falhas_seguidas", 0)
    if not probs:
        msg = f"🟢 Nina voltou. Ficou {_min(agora - estado['desde'])} fora do ar." if estado.get("avisado_em") else None
        return {"falhas_seguidas": 0}, msg
    novo = {"falhas_seguidas": n + 1, "desde": estado.get("desde", agora) if n else agora,
            "avisado_em": estado.get("avisado_em")}
    detalhe = "; ".join(probs)
    if novo["falhas_seguidas"] >= SEGUIDAS and not novo["avisado_em"]:
        novo["avisado_em"] = agora
        return novo, (f"🔴 Nina fora do ar há {_min(agora - novo['desde'])}: {detalhe}. "
                      "(vigia de fora, GitHub Actions) Olhar: docker ps no VPS (nina, nina-porteiro, n8n).")
    if novo["avisado_em"] and agora - novo["avisado_em"] >= LEMBRAR:
        novo["avisado_em"] = agora
        return novo, f"🔴 Nina continua fora do ar ({_min(agora - novo['desde'])}): {detalhe}."
    return novo, None


def _chamar(url: str, token: str):
    pedido = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "User-Agent": "nina-vigia"})
    try:
        with urllib.request.urlopen(pedido, timeout=40) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # timeout, DNS, recusou: o servidor não respondeu
        return None, str(getattr(e, "reason", None) or e)[:120]


ESPERA_NOVA_TENTATIVA = 10  # o runner do GitHub às vezes fica sem rede por um instante (20/10: Errno 101)


def _so_ipv4(original):
    """getaddrinfo só com IPv4: o runner do GitHub não tem IPv6 e o VPS publica AAAA."""
    def getaddrinfo(host, porta, family=0, *args, **kwargs):
        return original(host, porta, socket.AF_INET, *args, **kwargs)
    return getaddrinfo


def checar(chamar, dormir=time.sleep) -> list[str]:
    status, texto = chamar()
    if status is None:  # sem resposta pode ser a rede do runner: tenta mais uma vez antes de contar
        dormir(ESPERA_NOVA_TENTATIVA)
        status, texto = chamar()
    if status == 200:
        return []
    if status is None:
        return [f"VPS sem resposta: {texto}"]
    if status == 500:
        return ["Nina fora: o VPS respondeu, mas o porteiro ou o OpenJarvis não"]
    if status in (401, 403):
        return [f"token do vigia recusado (HTTP {status}): confira o secret VIGIA_TOKEN"]
    return [f"n8n ou Traefik do VPS respondeu HTTP {status}"]


def _postar(url: str, corpo: bytes, cabec: dict) -> None:
    urllib.request.urlopen(urllib.request.Request(url, data=corpo, headers=cabec, method="POST"), timeout=30).read()


def enviar_whatsapp(texto: str, url: str, token: str, numero: str, postar=_postar) -> None:
    if not (url and token and numero):
        print("aviso: sem os secrets da UAZAPI, WhatsApp não enviado")
        return
    try:
        postar(url.rstrip("/") + "/send/text", json.dumps({"number": numero, "text": texto}).encode(),
               {"token": token, "Content-Type": "application/json"})
        print("aviso: WhatsApp enviado")
    except Exception as e:  # o job já vai vermelho: o e-mail do GitHub ainda chega
        print(f"aviso: WhatsApp falhou ({e})")


def rodada(probs: list[str], arq_estado: Path, enviar, agora: float | None = None) -> int:
    agora = time.time() if agora is None else agora
    try:
        estado = json.loads(arq_estado.read_text())
    except (OSError, ValueError):
        estado = {}
    novo, aviso = transicao(estado, probs, agora)
    arq_estado.parent.mkdir(parents=True, exist_ok=True)
    arq_estado.write_text(json.dumps(novo))
    print(time.strftime("%F %T", time.gmtime(agora)), "UTC |", "; ".join(probs) or "ok", "| falhas seguidas:",
          novo.get("falhas_seguidas", 0))
    if not aviso:
        return 0
    enviar(aviso)
    print("AVISO:", aviso)
    return 1 if aviso.startswith("🔴") else 0


if __name__ == "__main__":
    socket.getaddrinfo = _so_ipv4(socket.getaddrinfo)
    e = os.environ
    arq = Path(sys.argv[sys.argv.index("--estado") + 1]) if "--estado" in sys.argv else Path("estado/estado.json")
    probs = checar(lambda: _chamar(e["VIGIA_URL"], e["VIGIA_TOKEN"]))
    sys.exit(rodada(probs, arq, lambda t: enviar_whatsapp(t, e.get("ALERTA_URL", ""), e.get("ALERTA_TOKEN", ""),
                                                          e.get("ALERTA_NUMERO", ""))))
