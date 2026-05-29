#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ailiance_mcp — Serveur MCP pour la flotte LLM souveraine Ailiance.

Expose la gateway Ailiance (OpenAI-compatible, https://gateway.ailiance.fr,
sans authentification, servie depuis la France) comme outils MCP, utilisables
depuis Claude Desktop / Cowork, Cursor, ou tout client MCP.

Outils :
  - ailiance_models()        : liste les modèles souverains disponibles + statut
  - ailiance_chat(...)        : inférence souveraine (auto-router ou alias précis)
  - ailiance_hardware(...)    : expert matériel (KiCad, SPICE, STM32, embarqué…)
  - ailiance_status()         : santé de la gateway

Aucune donnée ne quitte l'infrastructure : la gateway tourne sur du matériel
personnel en France (Tailscale + Cloudflare tunnel), aucun log de prompt
persisté, dossier de conformité EU AI Act par modèle.

Variables d'environnement :
  AILIANCE_GATEWAY   base URL de la gateway (défaut https://gateway.ailiance.fr)
  AILIANCE_TIMEOUT   timeout HTTP en secondes (défaut 120)
"""
from __future__ import annotations

import base64
import mimetypes
import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

GATEWAY = os.environ.get("AILIANCE_GATEWAY", "https://gateway.ailiance.fr").rstrip("/")
TIMEOUT = float(os.environ.get("AILIANCE_TIMEOUT", "120"))

mcp = FastMCP("ailiance")

# Domaines hardware -> alias d'expert (LoRA mascarade / spécialistes).
# On peut aussi laisser l'auto-router ("ailiance") décider.
HARDWARE_ALIASES = {
    "kicad": "ailiance-kicad",
    "pcb": "ailiance-kicad",
    "spice": "ailiance-spice",
    "ngspice": "ailiance-spice",
    "stm32": "ailiance-stm32",
    "emc": "ailiance-emc",
    "embedded": "ailiance-embedded",
    "embarque": "ailiance-embedded",
    "platformio": "ailiance-platformio",
    "freecad": "ailiance-freecad",
    "dsp": "ailiance-dsp",
    "iot": "ailiance-iot",
    "power": "ailiance-power",
    "components": "ailiance-components-review",
    "coder": "ailiance-coder",
}


async def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT)


@mcp.tool()
async def ailiance_models() -> str:
    """Liste les modèles de la flotte souveraine Ailiance (alias + statut).

    Utile pour savoir quel `model` passer à ailiance_chat. L'alias spécial
    "ailiance" laisse l'auto-router choisir le meilleur worker selon le domaine.
    """
    async with await _client() as c:
        r = await c.get(f"{GATEWAY}/v1/models")
        r.raise_for_status()
        data = r.json().get("data", [])
    if not data:
        return "Aucun modèle retourné par la gateway."
    lines = [f"{len(data)} modèles souverains disponibles (gateway {GATEWAY}) :", ""]
    for m in data:
        status = m.get("status", "?")
        mark = "●" if status == "ready" else "○"
        lines.append(f"  {mark} {m['id']}  [{status}]")
    lines.append("")
    lines.append('Astuce : model="ailiance" = auto-router (choisit le worker par domaine).')
    return "\n".join(lines)


@mcp.tool()
async def ailiance_chat(
    prompt: str,
    model: str = "ailiance",
    system: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    deliberate: bool = False,
) -> str:
    """Inférence souveraine via la flotte Ailiance (servie depuis la France).

    Args:
        prompt: la requête utilisateur.
        model: alias du modèle ("ailiance" = auto-router, ou un alias précis
            comme "ailiance-mistral-medium", "ailiance-qwen", "ailiance-coder").
        system: message système optionnel.
        temperature: créativité (0 = déterministe).
        max_tokens: longueur max de la réponse.
        deliberate: si vrai, active la chaîne validateurs+retry (router v0.3,
            audit-grade) côté gateway via extra_body.

    Renvoie la réponse, suivie du worker effectivement choisi par le routeur.
    """
    def build_payload(use_system: bool):
        msgs = []
        if system and use_system:
            msgs.append({"role": "system", "content": system})
        user = prompt if (use_system or not system) else f"{system}\n\n{prompt}"
        msgs.append({"role": "user", "content": user})
        p = {
            "model": model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if deliberate:
            p["chain_policy"] = "deliberate"
            p["include_audit"] = True
        return p

    async def call(use_system: bool):
        async with await _client() as c:
            resp = await c.post(f"{GATEWAY}/v1/chat/completions",
                                json=build_payload(use_system))
            try:
                return resp, resp.json()
            except Exception:  # noqa: BLE001
                resp.raise_for_status()
                raise

    r, data = await call(use_system=True)
    # Repli : certains workers (LoRA mascarade Qwen) exigent des rôles alternés
    # et rejettent un message system séparé -> on le fusionne dans le prompt.
    if isinstance(data, dict) and "error" in data and system:
        msg = str(data["error"].get("message", "")).lower()
        if "roles must alternate" in msg or "jinja" in msg or "system" in msg:
            r, data = await call(use_system=False)

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        if isinstance(data, dict) and "error" in data:
            return f"Erreur gateway : {data['error'].get('message', data['error'])}"
        return f"Réponse inattendue de la gateway : {data}"

    served = data.get("model", model)
    route = r.headers.get("x-route-decision") or r.headers.get("x-ailiance-route")
    footer = f"\n\n— servi par : {served} (souverain 🇫🇷"
    if route:
        footer += f", route : {route}"
    footer += ")"
    return content + footer


@mcp.tool()
async def ailiance_hardware(prompt: str, domain: str = "kicad") -> str:
    """Expert matériel souverain : KiCad/PCB, SPICE, STM32, embarqué, EMC, IoT…

    Route la requête vers l'expert LoRA Ailiance du domaine demandé. Idéal pour
    de la conception électronique, des schémas, du code embarqué ou des revues
    de composants.

    Args:
        prompt: la demande technique.
        domain: l'un de kicad/pcb, spice, stm32, emc, embedded, platformio,
            freecad, dsp, iot, power, components, coder. Inconnu => auto-router.
    """
    alias = HARDWARE_ALIASES.get(domain.strip().lower(), "ailiance")
    sys_prompt = (
        "Tu es un expert matériel de la flotte souveraine Ailiance. "
        f"Domaine : {domain}. Réponds de façon précise et actionnable."
    )
    return await ailiance_chat(
        prompt=prompt, model=alias, system=sys_prompt,
        temperature=0.2, max_tokens=2048,
    )


@mcp.tool()
async def ailiance_vision(prompt: str, image: str,
                          model: str = "ailiance-pixtral",
                          max_tokens: int = 1024) -> str:
    """Analyse une image avec le worker vision souverain (Pixtral 12B).

    Args:
        prompt: la question/instruction sur l'image (ex. "décris ce schéma",
            "lis les valeurs des composants", "y a-t-il une erreur de câblage ?").
        image: chemin local d'un fichier image OU URL http(s). Les chemins
            locaux sont encodés en data-URI base64 (rien n'est uploadé ailleurs
            que sur la gateway souveraine).
        model: worker vision (défaut "ailiance-pixtral").

    Idéal pour relire un schéma, une photo de carte, un plan ou un PDF rendu.
    """
    if image.startswith(("http://", "https://", "data:")):
        url = image
    else:
        path = os.path.expanduser(image)
        if not os.path.exists(path):
            return f"Image introuvable : {path}"
        mime = mimetypes.guess_type(path)[0] or "image/png"
        b64 = base64.b64encode(open(path, "rb").read()).decode()
        url = f"data:{mime};base64,{b64}"

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": url}},
            ],
        }],
        "max_tokens": max_tokens,
        "stream": False,
    }
    async with await _client() as c:
        r = await c.post(f"{GATEWAY}/v1/chat/completions", json=payload)
        data = r.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        if isinstance(data, dict) and "error" in data:
            return f"Erreur gateway (vision) : {data['error'].get('message', data['error'])}"
        return f"Réponse inattendue de la gateway : {data}"
    return content + f"\n\n— vision souveraine 🇫🇷 ({data.get('model', model)})"


@mcp.tool()
async def ailiance_audit(prompt: str, model: str = "ailiance",
                         system: Optional[str] = None,
                         max_tokens: int = 2048) -> str:
    """Inférence souveraine en mode audit-grade (chaîne deliberate + trace).

    Active la chaîne validateurs+retry (router v0.3) de la gateway via
    `chain_policy=deliberate` et `include_audit=true` : la réponse est validée
    (DRC/ERC/ngspice selon le domaine) et accompagnée d'une trace d'audit,
    utile pour de la conception électronique ou tout livrable vérifiable
    (conformité EU AI Act).
    """
    return await ailiance_chat(
        prompt=prompt, model=model, system=system,
        temperature=0.2, max_tokens=max_tokens, deliberate=True,
    )


@mcp.tool()
async def ailiance_status() -> str:
    """Vérifie la santé de la gateway souveraine et le nombre de modèles prêts."""
    async with await _client() as c:
        try:
            r = await c.get(f"{GATEWAY}/v1/models")
            r.raise_for_status()
            data = r.json().get("data", [])
        except Exception as e:  # noqa: BLE001
            return f"Gateway {GATEWAY} INJOIGNABLE : {e}"
    ready = sum(1 for m in data if m.get("status") == "ready")
    return (f"Gateway {GATEWAY} OK — {ready}/{len(data)} modèles prêts. "
            "Inférence souveraine, servie depuis la France, sans dépendance cloud.")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
