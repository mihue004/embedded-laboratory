import json
from pathlib import Path

from serial.tools import list_ports


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "host" / "config" / "devices.json"
CONFIG_VERSION = 2


def discover_devices(port_provider=None):
    """Discover USB serial devices."""
    if port_provider is None:
        port_provider = list_ports.comports

    devices = []

    for port in port_provider():
        vid = getattr(port, "vid", None)
        pid = getattr(port, "pid", None)
        serial_number = getattr(port, "serial_number", None)

        device_id = None

        if serial_number:
            vendor = f"{vid:04x}" if vid is not None else "unknown"
            product = f"{pid:04x}" if pid is not None else "unknown"
            device_id = f"usb:{vendor}:{product}:{serial_number}"

        devices.append({
            "device_id": device_id,
            "assignable": device_id is not None,
            "port": getattr(port, "device", None),
            "vid": vid,
            "pid": pid,
            "serial_number": serial_number,
            "description": getattr(port, "description", None),
            "manufacturer": getattr(port, "manufacturer", None),
            "product": getattr(port, "product", None),
            "hardware_id": getattr(port, "hwid", None),
            "location": getattr(port, "location", None),
        })

    return devices


def empty_device_config():
    return {
        "version": CONFIG_VERSION,
        "devices": {},
    }


def save_device_config(config, config_path=None):
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = path.with_suffix(path.suffix + ".tmp")

    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(config, file, indent=2)

    temporary_path.replace(path)


def load_device_config(config_path=None):
    """Load configuration and migrate legacy role-based files."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if not path.exists():
        return empty_device_config()

    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    if not isinstance(config, dict):
        raise ValueError("Invalid device configuration")

    if not isinstance(config.get("devices"), dict):
        raise ValueError("Invalid device configuration")

    version = config.get("version")

    if version == 1:
        migrated = {
            "version": CONFIG_VERSION,
            "devices": config["devices"],
        }
        save_device_config(migrated, path)
        return migrated

    if version != CONFIG_VERSION:
        raise ValueError("Unsupported device configuration version")

    return config


def register_devices(discovered_devices, config_path=None):
    """Register discovered devices without assigning roles."""
    config = load_device_config(config_path)
    changed = False

    for device in discovered_devices:
        device_id = device.get("device_id")

        if not device_id or not device.get("assignable"):
            continue

        if device_id not in config["devices"]:
            config["devices"][device_id] = {
                "device_id": device_id,
                "manufacturer": device.get("manufacturer"),
                "product": device.get("product"),
                "description": device.get("description"),
                "settings": {},
            }
            changed = True

    if changed:
        save_device_config(config, config_path)

    return config


def get_device_overview(discovered_devices=None, config_path=None):
    """Return registered devices with their current connection status."""
    if discovered_devices is None:
        discovered_devices = discover_devices()

    config = register_devices(discovered_devices, config_path)

    discovered_by_id = {
        device["device_id"]: device
        for device in discovered_devices
        if device.get("device_id")
    }

    overview = []

    for device_id, stored in config["devices"].items():
        current = discovered_by_id.get(device_id)

        overview.append({
            **stored,
            "connected": current is not None,
            "port": current.get("port") if current else None,
            "assignable": True,
            "vid": current.get("vid") if current else None,
            "pid": current.get("pid") if current else None,
            "serial_number": (
                current.get("serial_number") if current else None
            ),
            "hardware_id": (
                current.get("hardware_id") if current else None
            ),
            "location": current.get("location") if current else None,
        })

    return {
        "devices": overview,
        "unassignable_devices": [
            device for device in discovered_devices
            if not device.get("assignable")
        ],
    }