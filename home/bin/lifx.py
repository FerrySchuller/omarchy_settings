#!/usr/bin/env python3
"""lifx.py - LIFX-lampen uitlezen en besturen via het LAN-protocol (UDP 56700).

Geen dependencies: alleen de standaardbibliotheek. Gebaseerd op
https://lan.developer.lifx.com/docs/packet-contents

Lezen:
    lifx                                     # volledige readout
    lifx --json                              # machineleesbaar
    lifx discover                            # lampen in het net zoeken

Besturen:
    lifx on
    lifx off
    lifx toggle
    lifx brightness 40
    lifx color 280 80 60                     # hue, sat%, bri%
    lifx color 0 0 100 3500                  # wit op 3500K
    lifx kelvin 2700

Het IP staat standaard op 192.168.178.173; met `-i <ip>` of door een adres
vooraan te zetten (`lifx 192.168.178.173 off`) gebruik je een andere lamp.
"""

from __future__ import annotations

import argparse
import colorsys
import datetime as dt
import json
import math
import os
import random
import re
import socket
import struct
import subprocess
import sys
import time
import uuid

PORT = 56700
PROTOCOL = 1024
HEADER_LEN = 36
DEFAULT_IP = "192.168.178.173"

# Kleurpresets: naam -> (hue 0-360°, saturatie %, helderheid %, kelvin)
COLORS: dict[str, tuple[int, int, int, int]] = {
    "rood":     (0,   100, 100, 3500),
    "oranje":   (30,  100, 100, 3500),
    "geel":     (55,  100, 100, 3500),
    "groen":    (120, 100, 100, 3500),
    "turkoois": (175, 100, 100, 3500),
    "blauw":    (220, 100, 100, 3500),
    "paars":    (280, 100, 100, 3500),
    "roze":     (325, 100, 100, 3500),
    "wit":      (0,   0,   100, 3500),
    "warm":     (0,   0,   100, 2200),
    "koel":     (0,   0,   100, 6500),
    "nacht":    (0,   0,   8,   2200),
    "lees":     (0,   0,   80,  4500),
    "focus":    (0,   0,   100, 5500),
}

# Engelse synoniemen voor de kleuren
COLOR_ALIASES = {
    "red": "rood", "orange": "oranje", "yellow": "geel", "green": "groen",
    "cyan": "turkoois", "aqua": "turkoois", "teal": "turkoois",
    "blue": "blauw", "purple": "paars", "violet": "paars",
    "pink": "roze", "magenta": "roze",
    "white": "wit", "warmwhite": "warm", "warm-wit": "warm",
    "cool": "koel", "cold": "koel", "daylight": "koel",
    "night": "nacht", "dim": "nacht", "lezen": "lees",
}

# Korte commando-aliassen
COMMAND_ALIASES = {
    "b": "brightness", "br": "brightness", "bri": "brightness",
    "o": "on", "aan": "on",
    "f": "off", "uit": "off",
    "t": "toggle", "wissel": "toggle",
    "c": "color", "kleur": "color",
    "k": "kelvin", "temp": "kelvin",
    "s": "read", "status": "read",
}

# --- message types (device) -------------------------------------------------
GET_SERVICE, STATE_SERVICE = 2, 3
GET_HOST_FIRMWARE, STATE_HOST_FIRMWARE = 14, 15
GET_WIFI_INFO, STATE_WIFI_INFO = 16, 17
GET_WIFI_FIRMWARE, STATE_WIFI_FIRMWARE = 18, 19
GET_POWER, SET_POWER, STATE_POWER = 20, 21, 22
GET_LABEL, SET_LABEL, STATE_LABEL = 23, 24, 25
GET_VERSION, STATE_VERSION = 32, 33
GET_INFO, STATE_INFO = 34, 35
GET_LOCATION, SET_LOCATION, STATE_LOCATION = 48, 49, 50
GET_GROUP, SET_GROUP, STATE_GROUP = 51, 52, 53
STATE_UNHANDLED = 223

# --- message types (light) --------------------------------------------------
GET_COLOR, SET_COLOR, STATE_COLOR = 101, 102, 107
GET_LIGHT_POWER, SET_LIGHT_POWER, STATE_LIGHT_POWER = 116, 117, 118
GET_INFRARED, STATE_INFRARED, SET_INFRARED = 120, 121, 122
GET_AMBIENT_LIGHT, STATE_AMBIENT_LIGHT = 401, 402

PRODUCTS_URL = "https://raw.githubusercontent.com/LIFX/products/master/products.json"
PRODUCTS_CACHE = os.path.expanduser("~/.cache/lifx/products.json")


# --- protocol ---------------------------------------------------------------
def build_packet(msg_type, *, target=b"\x00" * 8, source=0, seq=0,
                 res_required=True, ack_required=False,
                 tagged=False, addressable=True, payload=b"") -> bytes:
    """Bouw een LIFX-pakket: 36-byte header + payload."""
    size = HEADER_LEN + len(payload)
    flags = PROTOCOL | (0x1000 if addressable else 0) | (0x2000 if tagged else 0)
    header = struct.pack("<HHI", size, flags, source)
    header += target + b"\x00" * 6
    header += bytes([(1 if res_required else 0) | (2 if ack_required else 0)])
    header += bytes([seq & 0xFF])
    header += b"\x00" * 8 + struct.pack("<H", msg_type) + b"\x00" * 2
    assert len(header) == HEADER_LEN, len(header)
    return header + payload


def parse_packet(data: bytes) -> dict:
    size, flags, source = struct.unpack_from("<HHI", data, 0)
    return {
        "size": size,
        "protocol": flags & 0x0FFF,
        "addressable": bool(flags & 0x1000),
        "tagged": bool(flags & 0x2000),
        "source": source,
        "target": data[8:16],
        "sequence": data[23],
        "type": struct.unpack_from("<H", data, 32)[0],
        "payload": data[36:size],
    }


def mac_str(raw: bytes) -> str:
    return ":".join(f"{b:02x}" for b in raw[:6])


class Device:
    """Eén LIFX-lamp op een bekend IP-adres."""

    def __init__(self, ip: str, timeout: float = 1.0):
        self.ip = ip
        self.timeout = timeout
        self.source = random.getrandbits(32)
        self.seq = 0
        self.mac: str | None = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.settimeout(timeout)
        self.sock.bind(("", 0))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.sock.close()

    def request(self, msg_type, payload=b"", expect=None, timeout=None, retries=3):
        """Stuur een pakket en geef het antwoord terug als (type, payload).

        LIFX praat UDP zonder betrouwbaarheid: pakketten vallen regelmatig weg.
        Daarom sturen we hetzelfde pakket tot `retries` keer opnieuw.
        """
        self.seq = (self.seq + 1) & 0xFF
        packet = build_packet(msg_type, source=self.source, seq=self.seq, payload=payload)
        for _ in range(max(1, retries)):
            self.sock.sendto(packet, (self.ip, PORT))
            self.sock.settimeout(self.timeout if timeout is None else timeout)
            while True:
                try:
                    data, _ = self.sock.recvfrom(2048)
                except socket.timeout:
                    break
                if len(data) < HEADER_LEN:
                    continue
                pkt = parse_packet(data)
                if pkt["source"] != self.source:
                    continue
                if pkt["type"] == STATE_UNHANDLED:
                    return None
                if expect is None or pkt["type"] in expect:
                    self.mac = mac_str(pkt["target"])
                    return pkt["type"], pkt["payload"]
        return None


# --- productnaam ------------------------------------------------------------
def product_name(pid: int) -> str | None:
    """Naam bij een product-id, via een lokale cache (of eenmalig ophalen)."""
    if not os.path.exists(PRODUCTS_CACHE):
        try:
            import urllib.request
            os.makedirs(os.path.dirname(PRODUCTS_CACHE), exist_ok=True)
            with urllib.request.urlopen(PRODUCTS_URL, timeout=8) as resp:
                data = resp.read()
            with open(PRODUCTS_CACHE, "wb") as fh:
                fh.write(data)
        except Exception:
            return None
    try:
        with open(PRODUCTS_CACHE, encoding="utf-8") as fh:
            registry = json.load(fh)
    except Exception:
        return None
    for vendor in registry:
        for product in vendor.get("products", []):
            if product.get("pid") == pid:
                return product.get("name")
    return None


# --- helpers ----------------------------------------------------------------
def hsbk_to_rgb(hue: int, saturation: int, brightness: int) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(hue / 65535.0, saturation / 65535.0, brightness / 65535.0)
    return round(r * 255), round(g * 255), round(b * 255)


def pct(value: int) -> float:
    return round(value / 65535 * 100, 1)


def decode_label(raw: bytes) -> str:
    return raw.split(b"\x00")[0].decode("utf-8", "replace")


def to_int(text: str, what: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise SystemExit(f"lifx: {what} moet een getal zijn, kreeg {text!r}")


# --- uitlezen ---------------------------------------------------------------
def read_state(ip: str, timeout: float) -> dict:
    info: dict = {"ip": ip}

    with Device(ip, timeout) as dev:
        reply = dev.request(GET_VERSION, expect={STATE_VERSION})
        if reply is None:
            raise SystemExit(f"lifx: {ip} antwoordt niet op poort {PORT} (lamp offline of ander net?)")
        vendor, product, version = struct.unpack_from("<III", reply[1], 0)
        info["mac"] = dev.mac
        info["vendor"] = vendor
        info["product_id"] = product
        info["product"] = product_name(product)
        info["version_raw"] = version

        reply = dev.request(GET_HOST_FIRMWARE, expect={STATE_HOST_FIRMWARE})
        if reply:
            build, minor, major = struct.unpack_from("<Q8xHH", reply[1], 0)
            info["firmware"] = f"{major}.{minor}"
            info["firmware_build"] = dt.datetime.fromtimestamp(
                build / 1e9, dt.timezone.utc).isoformat(timespec="seconds")

        reply = dev.request(GET_COLOR, expect={STATE_COLOR})
        if reply:
            hue, sat, bri, kelvin, _res, power = struct.unpack_from("<HHHHHH", reply[1], 0)
            rgb = hsbk_to_rgb(hue, sat, bri)
            color = {
                "hue_deg": round(hue / 65535 * 360, 1),
                "saturation_pct": pct(sat),
                "brightness_pct": pct(bri),
                "kelvin": kelvin,
                "hsbk_raw": [hue, sat, bri, kelvin],
                "rgb_hex": "#%02x%02x%02x" % rgb,
                "rgb": list(rgb),
            }
            if len(reply[1]) >= 52:
                color["label"] = decode_label(reply[1][12:44])
            info["color"] = color
            info["power"] = "on" if power == 0xFFFF else ("off" if power == 0 else "transition")

        reply = dev.request(GET_POWER, expect={STATE_POWER})
        if reply:
            info["power_level_pct"] = pct(struct.unpack_from("<H", reply[1], 0)[0])

        reply = dev.request(GET_WIFI_INFO, expect={STATE_WIFI_INFO})
        if reply:
            signal, = struct.unpack_from("<f", reply[1], 0)
            try:
                info["wifi_rssi_dbm"] = round(10 * math.log10(signal))
            except (ValueError, OverflowError):
                info["wifi_signal_raw"] = signal

        reply = dev.request(GET_LABEL, expect={STATE_LABEL})
        if reply:
            info["label"] = decode_label(reply[1][:32])

        reply = dev.request(GET_LOCATION, expect={STATE_LOCATION})
        if reply:
            info["location"] = {
                "uuid": str(uuid.UUID(bytes=reply[1][:16])),
                "label": decode_label(reply[1][16:48]),
            }

        reply = dev.request(GET_GROUP, expect={STATE_GROUP})
        if reply:
            info["group"] = {
                "uuid": str(uuid.UUID(bytes=reply[1][:16])),
                "label": decode_label(reply[1][16:48]),
            }

        reply = dev.request(GET_INFO, expect={STATE_INFO})
        if reply:
            when, uptime, downtime = struct.unpack_from("<QQQ", reply[1], 0)
            info["uptime_s"] = round(uptime / 1e9)
            info["downtime_s"] = round(downtime / 1e9)
            info["device_time_ns"] = when

        reply = dev.request(GET_AMBIENT_LIGHT, expect={STATE_AMBIENT_LIGHT}, timeout=0.4, retries=1)
        if reply:
            info["ambient_lux"] = round(struct.unpack_from("<f", reply[1], 0)[0], 1)

        reply = dev.request(GET_INFRARED, expect={STATE_INFRARED}, timeout=0.4, retries=1)
        if reply:
            info["infrared_pct"] = pct(struct.unpack_from("<H", reply[1], 0)[0])

    return info


def print_state(info: dict) -> None:
    def row(label, value):
        if value is not None:
            print(f"  {label:<16} {value}")

    print(f"LIFX lamp @ {info['ip']}")
    row("MAC", info.get("mac"))
    row("Product", f"{info.get('product') or '?'} (id {info.get('product_id')})")
    row("Firmware", info.get("firmware"))
    row("Label", info.get("label"))
    row("Power", info.get("power"))

    color = info.get("color")
    if color:
        print(f"  {'Kleur':<16} H {color['hue_deg']:>5}°  S {color['saturation_pct']:>5}%  "
              f"V {color['brightness_pct']:>5}%  {color['kelvin']}K  ->  {color['rgb_hex']}")

    if "wifi_rssi_dbm" in info:
        row("Wifi", f"{info['wifi_rssi_dbm']} dBm")
    loc = info.get("location")
    if loc:
        row("Locatie", f"{loc['label']}  ({loc['uuid']})")
    grp = info.get("group")
    if grp:
        row("Groep", f"{grp['label']}  ({grp['uuid']})")
    if info.get("uptime_s") is not None:
        row("Uptime", f"{dt.timedelta(seconds=info['uptime_s'])}  ({info['uptime_s']}s)")
    if info.get("ambient_lux") is not None:
        row("Omgevingslicht", f"{info['ambient_lux']} lux")
    if info.get("infrared_pct") is not None:
        row("Infrarood", f"{info['infrared_pct']}%")


# --- zoeken -----------------------------------------------------------------
def broadcast_targets() -> list[str]:
    """Alle broadcast-adressen van de actieve interfaces (plus de algemene)."""
    targets = {"255.255.255.255"}
    try:
        out = subprocess.run(["ip", "-o", "-4", "addr", "show"],
                             capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            if " brd " in line:
                targets.add(line.split(" brd ")[1].split()[0])
    except Exception:
        pass
    return sorted(targets)


def discover(timeout: float) -> list[dict]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    sock.bind(("", 0))
    packet = build_packet(GET_SERVICE, source=random.getrandbits(32),
                          tagged=True, addressable=True)
    for _ in range(3):
        for target in broadcast_targets():
            sock.sendto(packet, (target, PORT))
        time.sleep(0.15)
    seen: dict[str, dict] = {}
    while True:
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            break
        if len(data) < HEADER_LEN:
            continue
        pkt = parse_packet(data)
        if pkt["type"] != STATE_SERVICE or pkt["source"] != packet_source(packet):
            continue
        service, port = struct.unpack_from("<BI", pkt["payload"], 0)
        seen[addr[0]] = {"ip": addr[0], "mac": mac_str(pkt["target"]),
                         "service": "UDP" if service == 1 else str(service), "port": port}
    sock.close()
    return sorted(seen.values(), key=lambda d: tuple(int(o) for o in d["ip"].split(".")))


def packet_source(packet: bytes) -> int:
    return struct.unpack_from("<I", packet, 4)[0]


# --- besturen ---------------------------------------------------------------
def cmd_power(ip: str, timeout: float, level: int | None, duration: int,
              dry_run: bool = False) -> str:
    if dry_run:
        return {0: "off", 0xFFFF: "on", None: "toggle"}[level]
    with Device(ip, timeout) as dev:
        if level is None:  # toggle
            reply = dev.request(GET_POWER, expect={STATE_POWER})
            if reply is None:
                raise SystemExit(f"lifx: {ip} antwoordt niet")
            level = 0 if struct.unpack_from("<H", reply[1], 0)[0] else 0xFFFF
        if dev.request(SET_POWER, struct.pack("<HI", level, duration),
                       expect={STATE_POWER}) is None:
            raise SystemExit(f"lifx: {ip} bevestigde het power-commando niet")
        return "on" if level else "off"


def cmd_set_color(ip: str, timeout: float, duration: int,
                  hue: int, sat: int, bri: int, kelvin: int,
                  power_on: bool = True, dry_run: bool = False) -> None:
    """Zet een kleur en (tenzij power_on=False) zet de lamp daarbij aan.

    SetColor raakt de power-stand niet aan: staat de lamp uit, dan blijft die
    uit. Daarom sturen we er SetPower achteraan. Kleur eerst, power daarna,
    anders licht de lamp heel even op in de oude kleur.
    """
    payload = struct.pack("<BHHHHI", 0, hue, sat, bri, kelvin, duration)
    if dry_run:
        return
    with Device(ip, timeout) as dev:
        if dev.request(SET_COLOR, payload, expect={STATE_COLOR}) is None:
            raise SystemExit(f"lifx: {ip} bevestigde het kleur-commando niet")
        if power_on and dev.request(SET_POWER, struct.pack("<HI", 0xFFFF, duration),
                                    expect={STATE_POWER}) is None:
            print(f"lifx: {ip} bevestigde niet dat de lamp aanging", file=sys.stderr)


_COLOR_LIST = "  " + "  ".join(COLORS)

EPILOG = f"""\
commando's:
  read | s                volledige status van de lamp  (dit is de default)
  on | o   off | f        lamp aan of uit  (ook: aan, uit)
  toggle | t              wissel aan/uit   (ook: wissel)
  brightness | b <0-100>  helderheid; kleur en temperatuur blijven staan
  kelvin | k <1500-9000>  wit op die kleurtemperatuur
  color | c <h> <s> <b> [k]
                          zet kleur: hue 0-360°, saturatie 0-100%,
                          helderheid 0-100%, kelvin (optioneel, default 3500)
  <kleurnaam> [0-100]     kleurpreset, eventueel meteen op die helderheid
  discover                lampen zoeken via broadcast

kleuren:
{_COLOR_LIST}
  Engelse namen werken ook (red, green, blue, purple, pink, warmwhite, ...).

snelle aliassen:
  b = brightness  o = on  f = off  t = toggle  c = color  k = kelvin  s = status

voorbeelden:
  lifx                    status van de standaardlamp
  lifx f                  uit
  lifx o                  aan
  lifx paars              paars op volle helderheid (zet de lamp ook aan)
  lifx rood 30            rood op 30%
  lifx b 100              volle helderheid, kleur blijft staan
  lifx b +10              tien procent helderder  (b -10 voor dimmen)
  lifx warm               wit op 2200K
  lifx k 2700             warm wit
  lifx -d 1500 c 200 100 50   kleur met 1,5 s overgang
  lifx -i 192.168.178.174 on  andere lamp
  lifx --json | jq .color     machineleesbaar verder verwerken

de standaardlamp is {DEFAULT_IP}; een adres vooraan (`lifx 10.0.0.5 off`) of
-i <ip> kiest een andere. De lamp praat UDP op poort {PORT} zonder
betrouwbaarheid: pakketten vallen weleens weg, daarom stuurt dit script elk
bericht tot 3x opnieuw. Reageert er niets, dan zegt het dat gewoon.
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LIFX-lampen uitlezen en besturen via het LAN-protocol.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", nargs="?", default="read", metavar="COMMAND",
                        help="wat je wil doen; zie de commando's onderaan (default: read)")
    parser.add_argument("args", nargs="*", metavar="ARG",
                        help="argumenten voor het commando, bijv. de 3 waarden van 'color'")
    parser.add_argument("-i", "--ip", default=DEFAULT_IP, metavar="IP",
                        help=f"IP van de lamp, of 'discover' (default: {DEFAULT_IP})")
    parser.add_argument("-t", "--timeout", type=float, default=1.0, metavar="SEC",
                        help="wachttijd per antwoord in seconden (default: 1.0)")
    parser.add_argument("-d", "--duration", type=int, default=0, metavar="MS",
                        help="overgangstijd voor on/off/color in ms (default: 0)")
    parser.add_argument("--json", action="store_true",
                        help="readout als JSON in plaats van een tabel")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="laat zien wat er zou gebeuren, zonder de lamp te besturen")
    parser.add_argument("--no-power", action="store_true",
                        help="zet alleen de kleur; laat de lamp uit als die uit staat")

    # Sta zowel `lifx off` als `lifx 192.168.178.173 off` toe: een leidend adres
    # wordt naar --ip vertaald.
    argv = sys.argv[1:]
    if argv and (argv[0] == "discover" or re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", argv[0])):
        argv = ["--ip", argv[0], *argv[1:]]
    opts = parser.parse_args(argv)

    if opts.ip == "discover":
        found = discover(opts.timeout)
        if opts.json:
            print(json.dumps(found, indent=2))
        elif not found:
            print("Geen lampen gevonden via broadcast.")
            print("Tip: broadcast werkt niet altijd (meerdere interfaces op één subnet, "
                  "of de lamp zit achter een repeater). Gebruik dan het IP direct.")
        else:
            for d in found:
                print(f"  {d['ip']:<16} {d['mac']}  {d['service']}:{d['port']}")
        return 0

    ip, cmd, args = opts.ip, COMMAND_ALIASES.get(opts.command, opts.command), opts.args
    power_on = not opts.no_power

    if cmd == "read":
        info = read_state(ip, opts.timeout)
        print(json.dumps(info, indent=2, ensure_ascii=False) if opts.json else "", end="")
        if not opts.json:
            print_state(info)
        return 0

    if cmd in {"on", "off", "toggle"}:
        level = {"on": 0xFFFF, "off": 0, "toggle": None}[cmd]
        state = cmd_power(ip, opts.timeout, level, opts.duration, opts.dry_run)
        print(f"{ip}: {state}" + ("  (dry-run)" if opts.dry_run else ""))
        return 0

    if cmd in {"brightness", "kelvin"}:
        if not args:
            parser.error(f"{cmd} heeft een waarde nodig")
        value = to_int(args[0], "die waarde")
        relative = args[0][:1] in "+-" and cmd == "brightness"
        with Device(ip, opts.timeout) as dev:
            reply = dev.request(GET_COLOR, expect={STATE_COLOR})
            if reply is None:
                raise SystemExit(f"lifx: {ip} antwoordt niet")
            hue, sat, bri, kelvin = struct.unpack_from("<HHHH", reply[1], 0)
            if cmd == "kelvin":
                kelvin, sat = max(1500, min(9000, value)), 0
            else:
                # `lifx b +10` / `lifx b -10` stelt bij t.o.v. de huidige waarde
                target = round(bri / 65535 * 100) + value if relative else value
                bri = max(0, min(100, target)) * 65535 // 100
            cmd_set_color(ip, opts.timeout, opts.duration, hue, sat, bri, kelvin,
                          power_on=power_on, dry_run=opts.dry_run)
        print((f"{ip}: {cmd} {args[0]}" if relative else f"{ip}: {cmd} {value}")
              + ("  (dry-run)" if opts.dry_run else ""))
        return 0

    if cmd == "color":
        if len(args) < 3:
            parser.error("color heeft hue (0-360), sat (%) en brightness (%) nodig")
        hue = to_int(args[0], "hue")
        sat = to_int(args[1], "saturatie")
        bri = to_int(args[2], "helderheid")
        kelvin = to_int(args[3], "kelvin") if len(args) > 3 else 3500
        cmd_set_color(ip, opts.timeout, opts.duration,
                      hue % 360 * 65535 // 360,
                      max(0, min(100, sat)) * 65535 // 100,
                      max(0, min(100, bri)) * 65535 // 100,
                      max(1500, min(9000, kelvin)),
                      power_on=power_on, dry_run=opts.dry_run)
        print(f"{ip}: hue {hue}°  sat {sat}%  bri {bri}%  {kelvin}K"
              + ("  (dry-run)" if opts.dry_run else ""))
        return 0

    # kleurpreset, optioneel gevolgd door een helderheid
    color_name = COLOR_ALIASES.get(cmd, cmd)
    if color_name in COLORS:
        hue, sat, bri, kelvin = COLORS[color_name]
        if args:
            bri = max(0, min(100, to_int(args[0], "helderheid")))
        cmd_set_color(ip, opts.timeout, opts.duration,
                      hue % 360 * 65535 // 360, sat * 65535 // 100,
                      bri * 65535 // 100, kelvin,
                      power_on=power_on, dry_run=opts.dry_run)
        print(f"{ip}: {color_name}" + (f" op {bri}%" if args else "")
              + ("  (dry-run)" if opts.dry_run else ""))
        return 0

    parser.error(
        f"onbekend commando of kleur: {cmd!r}\n"
        "Commando's: read, on, off, toggle, brightness, kelvin, color, discover.\n"
        f"Kleuren: {', '.join(COLORS)}\n"
        "Zie `lifx --help` voor uitleg en voorbeelden.")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        sys.exit(130)
