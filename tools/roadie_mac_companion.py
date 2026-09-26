#!/usr/bin/env python3
"""
R.O.A.D.I.E Mac Desktop Companion & Hardware Bridge
===================================================
Conecta tu Mac con el dispositivo físico de escritorio (ESP32-S3 AMOLED)
utilizando HERMES AGENT (https://api.jobits.digital) como cerebro principal.

Funcionalidades idénticas al ecosistema Hey Taby:
- Asistente de escritorio interactivo (voz/texto).
- Control visual de animaciones en la pantalla AMOLED de tu escritorio.
- Temporizadores de concentración Pomodoro (Focus Timer).
- Gestión de tareas y notas sincronizadas con el Kanban de Hermes.
- Detección de toques en pantalla (CHOICE_SIGNAL) y eventos táctiles.
- Servidor MCP integrado para que otros agentes invoquen a Roadie.
"""

import sys
import os
import time
import json
import re
import threading
import urllib.request
import urllib.error

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

# Configuración del Cerebro Hermes Agent (VPS)
HERMES_API_URL = os.environ.get("ROADIE_API_URL", "https://api.jobits.digital/api/v1/chat")
HERMES_TOKEN = os.environ.get("ROADIE_API_TOKEN", "roadie_1f21a1c803c24583a3c28ecce0599fb0e6bb4f5d")

DEFAULT_ANIMATIONS = {
    "idle": "idle_01_loop",
    "thinking": "thinking",
    "success": "confirmation",
    "celebrate": "boxing",
    "attention": "flower_grow",
    "focus": "timer"
}


class RoadieHardwareClient:
    """Maneja la conexión serial USB con la pantalla AMOLED de Waveshare."""

    def __init__(self, port=None, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.connection = None
        self._lock = threading.Lock()

    def find_port(self):
        if not list_ports:
            return None
        ports = list_ports.comports()
        for p in ports:
            # En macOS los ESP32 nativos enumeran típicamente como usbmodem
            if "usbmodem" in p.device.lower() or (p.vid == 0x303A):
                return p.device
        return ports[0].device if ports else None

    def connect(self):
        if not serial:
            print("⚠️ Advertencia: 'pyserial' no está instalado. Modo emulación activado.")
            return False

        if not self.port:
            self.port = self.find_port()

        if not self.port:
            print("⚠️ No se detectó ninguna pantalla ESP32 conectada por USB.")
            return False

        try:
            self.connection = serial.Serial(self.port, self.baudrate, timeout=0.2)
            self.connection.dtr = False
            self.connection.rts = False
            print(f"✅ Conectado a pantalla ROADIE en {self.port} a {self.baudrate} baudios.")
            return True
        except Exception as e:
            print(f"❌ Error abriendo puerto serial {self.port}: {e}")
            self.connection = None
            return False

    def send_command(self, cmd, timeout=3.0):
        if not self.connection:
            print(f"[Simulador Hardware] Comando: {cmd}")
            return "SIMULATED_OK"

        with self._lock:
            try:
                self.connection.reset_input_buffer()
                self.connection.write((cmd + "\n").encode("utf-8"))
                self.connection.flush()

                deadline = time.monotonic() + timeout
                buffer = bytearray()
                while time.monotonic() < deadline:
                    waiting = self.connection.in_waiting or 1
                    chunk = self.connection.read(waiting)
                    if chunk:
                        buffer.extend(chunk)
                        if b"\n" in buffer:
                            lines = buffer.decode("utf-8", errors="replace").split("\n")
                            for line in lines:
                                line = line.strip()
                                if line.startswith("TABY:OK") or line.startswith("ROADIE:OK"):
                                    return line
                                if line.startswith("TABY:CHOICE_SIGNAL"):
                                    return line
                return "TIMEOUT"
            except Exception as e:
                print(f"⚠️ Error de transmisión USB: {e}")
                return f"ERROR: {e}"

    def play_animation(self, animation_id):
        """Reproduce una animación facial en la pantalla AMOLED."""
        return self.send_command(animation_id)

    def show_card(self, title, subtitle=""):
        """Muestra una tarjeta de texto en el display."""
        title = title.replace("|", " ").replace("\n", " ").strip()
        subtitle = subtitle.replace("|", " ").replace("\n", " ").strip()
        return self.send_command(f"UI/title_subtitle?demo:{title}|{subtitle}")

    def show_choice(self, prompt, opt1="SÍ", opt2="LUEGO"):
        """Muestra un selector táctil de 2 opciones en la pantalla."""
        prompt = prompt.replace("|", " ").strip()
        return self.send_command(f"UI/choice_2?demo:{prompt}|{opt1}|{opt2}")

    def start_focus_timer(self, minutes=25, label="ENFOQUE"):
        """Inicia un temporizador Pomodoro en el hardware."""
        seconds = int(minutes) * 60
        return self.send_command(f"UI/timer?demo:{label}|{seconds}|{seconds}||run|0")

    def set_eye_motion(self, mode="normal"):
        """Ajusta el ritmo de la mirada: normal, calm, still."""
        if mode in ("normal", "calm", "still"):
            return self.send_command(f"EYE_MOTION {mode}")
        return None

    def clear(self):
        """Limpia la pantalla y regresa al estado en reposo."""
        return self.send_command("CLEAR")


class HermesBrainClient:
    """Cliente para comunicarse con el cerebro Hermes Agent en el VPS."""

    def __init__(self, api_url=HERMES_API_URL, token=HERMES_TOKEN):
        self.api_url = api_url
        self.token = token

    def ask(self, prompt, session_id="mac-desktop-companion"):
        """Envía un prompt a Hermes Agent y recibe su respuesta y metadatos."""
        payload = {
            "message": prompt,
            "session_id": session_id,
            "stream": False
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }

        try:
            req = urllib.request.Request(
                self.api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            return {"error": f"HTTP {e.code}: {err_body}"}
        except Exception as e:
            return {"error": str(e)}


class RoadieMacCompanion:
    """Coordinador del Asistente de Escritorio en macOS."""

    def __init__(self):
        self.hardware = RoadieHardwareClient()
        self.brain = HermesBrainClient()
        self.running = True

    def start(self):
        print("=" * 60)
        print("🤖 R.O.A.D.I.E DESKTOP COMPANION PARA MAC")
        print("   Cerebro: Hermes Agent (api.jobits.digital)")
        print("   Hardware: Waveshare ESP32-S3 Touch AMOLED")
        print("=" * 60)

        # Conectar hardware
        self.hardware.connect()
        self.hardware.play_animation(DEFAULT_ANIMATIONS["idle"])

        print("\nComandos especiales disponibles:")
        print("  /focus [min]   -> Inicia un temporizador Pomodoro en tu mesa")
        print("  /card [txt]    -> Muestra una tarjeta en la pantalla física")
        print("  /eyes [modo]   -> Ajusta mirada (normal, calm, still)")
        print("  /anim [id]     -> Prueba una animación (confirmation, boxing, etc.)")
        print("  /clear         -> Limpia la pantalla")
        print("  /exit          -> Salir\n")

        while self.running:
            try:
                user_input = input("Tú > ").strip()
                if not user_input:
                    continue

                if user_input.lower() in ("/exit", "/quit"):
                    break

                # Manejo de comandos rápidos de escritorio (tipo Hey Taby)
                if user_input.startswith("/focus"):
                    parts = user_input.split()
                    mins = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 25
                    print(f"⏱️ Iniciando sesión de enfoque de {mins} minutos...")
                    self.hardware.start_focus_timer(mins, "TRABAJO PROFUNDO")
                    continue

                if user_input.startswith("/card"):
                    text = user_input[5:].strip()
                    self.hardware.show_card("ROADIE NOTA", text)
                    continue

                if user_input.startswith("/eyes"):
                    parts = user_input.split()
                    mode = parts[1] if len(parts) > 1 else "calm"
                    self.hardware.set_eye_motion(mode)
                    print(f"👀 Mirada ajustada a: {mode}")
                    continue

                if user_input.startswith("/anim"):
                    parts = user_input.split()
                    anim = parts[1] if len(parts) > 1 else "confirmation"
                    self.hardware.play_animation(anim)
                    continue

                if user_input.startswith("/clear"):
                    self.hardware.clear()
                    continue

                # Flujo normal con el Cerebro Hermes Agent
                # 1. Cambiar estado visual del hardware a "Pensando"
                self.hardware.play_animation(DEFAULT_ANIMATIONS["thinking"])
                print("Roadie está pensando...")

                # 2. Consultar al agente en el VPS
                response = self.brain.ask(user_input)

                if "error" in response:
                    print(f"❌ Error de Hermes: {response['error']}")
                    self.hardware.play_animation("idle_01_loop")
                    continue

                agent_text = response.get("response", response.get("reply", response.get("message", "")))
                if not agent_text and isinstance(response, str):
                    agent_text = response

                # 3. Detectar intenciones visuales o animar éxito
                if "!" in agent_text or "listo" in agent_text.lower() or "completado" in agent_text.lower():
                    self.hardware.play_animation(DEFAULT_ANIMATIONS["success"])
                else:
                    self.hardware.play_animation(DEFAULT_ANIMATIONS["idle"])

                print(f"\nRoadie > {agent_text}\n")

            except (KeyboardInterrupt, EOFError):
                break

        print("\n👋 Cerrando R.O.A.D.I.E Desktop Companion. ¡Hasta pronto!")
        self.hardware.clear()


if __name__ == "__main__":
    app = RoadieMacCompanion()
    app.start()
