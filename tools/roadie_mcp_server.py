#!/usr/bin/env python3
"""
R.O.A.D.I.E Model Context Protocol (MCP) Server
================================================
Permite a cualquier Agente de IA (Hermes, Claude, Codex, Antigravity)
controlar la pantalla física de escritorio (Physical Roadie).

Herramientas expuestas (MCP Tools):
- roadie_play_animation: Cambia la cara/emoción en la pantalla AMOLED.
- roadie_show_card: Despliega una tarjeta de texto (recordatorio, nota).
- roadie_start_focus: Inicia un temporizador Pomodoro en el hardware.
- roadie_ask_choice: Despliega dos opciones táctiles interactivas en la pantalla.
- roadie_set_eyes: Ajusta la animación ocular de reposo (normal, calm, still).
- roadie_clear: Limpia la pantalla al estado por defecto.
"""

import sys
import json
from roadie_mac_companion import RoadieHardwareClient, DEFAULT_ANIMATIONS

hw = RoadieHardwareClient()
hw.connect()

TOOLS = [
    {
        "name": "roadie_play_animation",
        "description": "Reproduce una animación emocional en la pantalla física de Roadie en tu escritorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "animation_id": {
                    "type": "string",
                    "description": "ID de la animación (ej: confirmation, thinking, boxing, flower_grow, idle_01_loop)"
                }
            },
            "required": ["animation_id"]
        }
    },
    {
        "name": "roadie_show_card",
        "description": "Muestra una tarjeta de notificación con título y subtítulo en la pantalla de escritorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Título de la tarjeta"},
                "subtitle": {"type": "string", "description": "Subtítulo o detalle"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "roadie_start_focus",
        "description": "Inicia un temporizador Pomodoro de concentración con barra de progreso en la pantalla.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "minutes": {"type": "integer", "description": "Duración en minutos (por defecto 25)"},
                "label": {"type": "string", "description": "Etiqueta de la sesión (ej: TRABAJO, LECTURA)"}
            },
            "required": ["minutes"]
        }
    },
    {
        "name": "roadie_ask_choice",
        "description": "Muestra una pregunta con dos botones táctiles interactivos en la pantalla AMOLED.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Pregunta a mostrar"},
                "option1": {"type": "string", "description": "Texto opción 1 (por defecto SÍ)"},
                "option2": {"type": "string", "description": "Texto opción 2 (por defecto LUEGO)"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "roadie_set_eyes",
        "description": "Ajusta el comportamiento de parpadeo y movimiento de ojos en reposo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["normal", "calm", "still"],
                    "description": "Modo de mirada"
                }
            },
            "required": ["mode"]
        }
    },
    {
        "name": "roadie_clear",
        "description": "Limpia la pantalla y regresa al rostro normal en reposo.",
        "inputSchema": {"type": "object", "properties": {}}
    }
]


def handle_tool_call(name, args):
    if name == "roadie_play_animation":
        res = hw.play_animation(args.get("animation_id", "confirmation"))
        return {"status": "ok", "result": res}
    elif name == "roadie_show_card":
        res = hw.show_card(args.get("title", ""), args.get("subtitle", ""))
        return {"status": "ok", "result": res}
    elif name == "roadie_start_focus":
        res = hw.start_focus_timer(args.get("minutes", 25), args.get("label", "ENFOQUE"))
        return {"status": "ok", "result": res}
    elif name == "roadie_ask_choice":
        res = hw.show_choice(args.get("prompt", ""), args.get("option1", "SÍ"), args.get("option2", "LUEGO"))
        return {"status": "ok", "result": res}
    elif name == "roadie_set_eyes":
        res = hw.set_eye_motion(args.get("mode", "calm"))
        return {"status": "ok", "result": res}
    elif name == "roadie_clear":
        res = hw.clear()
        return {"status": "ok", "result": res}
    else:
        return {"error": f"Herramienta desconocida: {name}"}


def main():
    """Bucle JSON-RPC para MCP stdio."""
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            req = json.loads(line)
            method = req.get("method")
            req_id = req.get("id")

            if method == "tools/list":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
            elif method == "tools/call":
                params = req.get("params", {})
                name = params.get("name")
                args = params.get("arguments", {})
                res = handle_tool_call(name, args)
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}]
                    }
                }
            else:
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}

            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"Error MCP: {e}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
