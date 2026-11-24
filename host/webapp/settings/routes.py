import sys
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "host" / "testbench"))

import device_manager
from device_communication import device_communication

settings_bp = Blueprint("settings", __name__)


@settings_bp.get("/")
def settings_page():
    return render_template("settings.html")


@settings_bp.get("/api/devices")
def devices_api():
    return jsonify(device_manager.get_device_overview())


def _connect_device(device_id):
    overview = device_manager.get_device_overview()

    device = next(
        (
            entry for entry in overview["devices"]
            if entry.get("device_id") == device_id
        ),
        None,
    )

    if not device:
        raise ValueError("Unknown device")

    if not device.get("connected") or not device.get("port"):
        raise RuntimeError("Device is not connected")

    device_communication.connect(device_id, device["port"])
    return device_id


@settings_bp.get("/api/devices/<device_id>/version")
def get_device_version_api(device_id):
    try:
        _connect_device(device_id)
        version = device_communication.get_version(device_id)

        return jsonify({
            "success": True,
            "device_id": device_id,
            "version": version,
        })

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except (RuntimeError, TimeoutError, OSError) as exc:
        return jsonify({"error": str(exc)}), 502


@settings_bp.get("/api/devices/<device_id>/config")
def get_device_config_api(device_id):
    try:
        _connect_device(device_id)
        config = device_communication.get_config(device_id)

        return jsonify({
            "success": True,
            "device_id": device_id,
            "config": config,
        })

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except (RuntimeError, TimeoutError, OSError) as exc:
        return jsonify({"error": str(exc)}), 502


@settings_bp.post("/api/devices/<device_id>/config")
def set_device_config_api(device_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not isinstance(data.get("config"), dict):
        return jsonify({"error": "A configuration object is required"}), 400

    try:
        _connect_device(device_id)
        device_communication.set_config(device_id, data["config"])
        config = device_communication.get_config(device_id)

        return jsonify({
            "success": True,
            "device_id": device_id,
            "config": config,
        })

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except (RuntimeError, TimeoutError, OSError) as exc:
        return jsonify({"error": str(exc)}), 502
