# mcp-ailiance — flotte LLM souveraine en serveur MCP

Expose la gateway **Ailiance** (`https://gateway.ailiance.fr`, OpenAI-compatible,
sans authentification, servie depuis la France) comme un **serveur MCP** : tu peux
appeler ton inférence souveraine depuis Claude Desktop / Cowork, Cursor, ou tout
client MCP, sans dépendance cloud.

## Outils exposés

| Outil | Rôle |
|---|---|
| `ailiance_models` | Liste les modèles souverains (alias + statut) |
| `ailiance_chat` | Inférence souveraine (auto-router `ailiance` ou alias précis) |
| `ailiance_hardware` | Expert matériel : KiCad/PCB, SPICE, STM32, embarqué, EMC, IoT… |
| `ailiance_vision` | Analyse d'image (schéma, photo de carte, plan) via Pixtral souverain |
| `ailiance_audit` | Inférence audit-grade (chaîne `deliberate` + trace, conformité IA Act) |
| `ailiance_status` | Santé de la gateway + modèles prêts |

> **Note vision** : `ailiance_vision` envoie l'image au format multimodal OpenAI
> (`image_url`, data-URI base64 pour les fichiers locaux — rien n'est uploadé
> ailleurs que sur la gateway souveraine). Le rendu dépend du passthrough
> multimodal côté gateway sur le worker Pixtral.

## Installation

```bash
cd mcp-ailiance
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Test rapide en ligne de commande (protocole MCP via stdio) :

```bash
python ailiance_mcp.py   # démarre le serveur ; Ctrl-C pour quitter
```

## Brancher dans Claude Desktop / Cowork

Ajouter au fichier `claude_desktop_config.json`
(macOS : `~/Library/Application Support/Claude/claude_desktop_config.json`) :

```json
{
  "mcpServers": {
    "ailiance": {
      "command": "/CHEMIN/VERS/mcp-ailiance/.venv/bin/python",
      "args": ["/CHEMIN/VERS/mcp-ailiance/ailiance_mcp.py"],
      "env": {
        "AILIANCE_GATEWAY": "https://gateway.ailiance.fr"
      }
    }
  }
}
```

Redémarre Claude : les 4 outils `ailiance_*` apparaissent. Demande par ex.
« utilise ailiance_hardware pour me proposer un schéma d'alimentation 5 V / 3 A en KiCad ».

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `AILIANCE_GATEWAY` | `https://gateway.ailiance.fr` | Base URL (mettre une IP Tailscale pour du LAN-only) |
| `AILIANCE_TIMEOUT` | `120` | Timeout HTTP (s) — les gros modèles peuvent être lents |

## Souveraineté

Aucune donnée ne quitte l'infrastructure Ailiance : matériel personnel en France
(Tailscale + tunnel Cloudflare), zéro log de prompt persisté, dossier de
conformité EU AI Act (Art. 13/15/52/53, Annexe IV) par modèle. Tout le code de la
gateway est Apache-2.0 : <https://github.com/ailiance/ailiance>.
