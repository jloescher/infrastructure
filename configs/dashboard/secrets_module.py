import os
import shutil
import subprocess
from datetime import datetime

import yaml

SECRETS_DIR = "/opt/dashboard/secrets"
SOPS_CONFIG = "/opt/dashboard/.sops.yaml"
AGE_KEY_PATH = "/opt/dashboard/secrets/age.key"
APP_SECRET_SCOPES = ("shared", "production", "staging")


def ensure_secrets_dir():
    os.makedirs(SECRETS_DIR, exist_ok=True)


def get_secrets_file(app_name):
    return os.path.join(SECRETS_DIR, f"{app_name}.yaml")


def get_global_secrets_file():
    return os.path.join(SECRETS_DIR, "global.yaml")


def sops_encrypt(file_path):
    try:
        env = os.environ.copy()
        env["SOPS_AGE_KEY_FILE"] = AGE_KEY_PATH
        result = subprocess.run(
            ["sops", "--encrypt", "--in-place", file_path],
            capture_output=True,
            text=True,
            env=env,
            cwd="/opt/dashboard",
        )
        return {"success": result.returncode == 0, "error": result.stderr if result.returncode != 0 else None}
    except Exception as e:
        return {"success": False, "error": str(e)}


def sops_decrypt(file_path):
    try:
        env = os.environ.copy()
        env["SOPS_AGE_KEY_FILE"] = AGE_KEY_PATH
        result = subprocess.run(
            ["sops", "--decrypt", file_path],
            capture_output=True,
            text=True,
            env=env,
            cwd="/opt/dashboard",
        )
        if result.returncode == 0:
            return {"success": True, "data": result.stdout}
        return {"success": False, "error": result.stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}


def sops_decrypt_to_file(encrypted_path, output_path):
    try:
        env = os.environ.copy()
        env["SOPS_AGE_KEY_FILE"] = AGE_KEY_PATH
        result = subprocess.run(
            ["sops", "--decrypt", "--output", output_path, encrypted_path],
            capture_output=True,
            text=True,
            env=env,
            cwd="/opt/dashboard",
        )
        return {"success": result.returncode == 0, "error": result.stderr if result.returncode != 0 else None}
    except Exception as e:
        return {"success": False, "error": str(e)}


def is_encrypted(file_path):
    if not os.path.exists(file_path):
        return False
    try:
        with open(file_path, "r") as f:
            content = f.read()
            return "sops" in content and "enc" in content
    except Exception:
        return False


def _normalize_secret_map(secret_map):
    normalized = {}
    for k, v in (secret_map or {}).items():
        item = v or {}
        updated_at = item.get("updated_at", "")
        if isinstance(updated_at, datetime):
            updated_at = updated_at.isoformat()
        normalized[str(k)] = {
            "value": str(item.get("value", "")),
            "description": str(item.get("description", "")),
            "updated_at": str(updated_at),
        }
    return normalized


def _empty_scoped_map():
    return {scope: {} for scope in APP_SECRET_SCOPES}


def _parse_scoped_app_secret_data(data):
    scoped = _empty_scoped_map()

    if not data:
        return scoped

    # New schema
    if any(scope in data for scope in APP_SECRET_SCOPES):
        for scope in APP_SECRET_SCOPES:
            scoped[scope] = _normalize_secret_map(data.get(scope, {}))
        return scoped

    # Legacy schema compatibility: secrets -> shared
    legacy = data.get("secrets", {}) if isinstance(data, dict) else {}
    scoped["shared"] = _normalize_secret_map(legacy)
    return scoped


def load_scoped_app_secrets(app_name):
    secrets_file = get_secrets_file(app_name)
    if not os.path.exists(secrets_file):
        return _empty_scoped_map()

    if is_encrypted(secrets_file):
        result = sops_decrypt(secrets_file)
        if not result["success"]:
            return _empty_scoped_map()
        try:
            data = yaml.safe_load(result["data"]) or {}
        except Exception:
            return _empty_scoped_map()
        return _parse_scoped_app_secret_data(data)

    try:
        with open(secrets_file, "r") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return _empty_scoped_map()
    return _parse_scoped_app_secret_data(data)


def save_scoped_app_secrets(app_name, scoped_secrets):
    ensure_secrets_dir()
    secrets_file = get_secrets_file(app_name)
    temp_path = os.path.join(SECRETS_DIR, f".{app_name}.tmp.yaml")

    payload = {scope: _normalize_secret_map((scoped_secrets or {}).get(scope, {})) for scope in APP_SECRET_SCOPES}

    with open(temp_path, "w") as f:
        yaml.safe_dump(payload, f, default_flow_style=False, sort_keys=True)

    try:
        encrypt_result = sops_encrypt(temp_path)
        if encrypt_result["success"]:
            shutil.move(temp_path, secrets_file)
            os.chmod(secrets_file, 0o600)
            return {"success": True}
        os.unlink(temp_path)
        return encrypt_result
    except Exception as e:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        return {"success": False, "error": str(e)}


def load_app_secrets(app_name, scope="shared"):
    scoped = load_scoped_app_secrets(app_name)
    return scoped.get(scope, {})


def save_app_secrets(app_name, secrets, scope="shared"):
    scoped = load_scoped_app_secrets(app_name)
    scoped[scope] = _normalize_secret_map(secrets)
    return save_scoped_app_secrets(app_name, scoped)


def set_app_secret(app_name, key, value, description="", scope="shared"):
    scoped = load_scoped_app_secrets(app_name)
    if scope not in scoped:
        scoped[scope] = {}
    scoped[scope][key] = {
        "value": value,
        "description": description,
        "updated_at": datetime.utcnow().isoformat(),
    }
    return save_scoped_app_secrets(app_name, scoped)


def delete_app_secret(app_name, key, scope=None):
    scoped = load_scoped_app_secrets(app_name)
    changed = False

    if scope:
        if key in scoped.get(scope, {}):
            del scoped[scope][key]
            changed = True
    else:
        for env_scope in APP_SECRET_SCOPES:
            if key in scoped.get(env_scope, {}):
                del scoped[env_scope][key]
                changed = True

    if not changed:
        return {"success": True}
    return save_scoped_app_secrets(app_name, scoped)


def get_app_secret(app_name, key, scope="shared"):
    scoped = load_scoped_app_secrets(app_name)
    if key in scoped.get(scope, {}):
        return scoped[scope][key].get("value")
    if scope != "shared" and key in scoped.get("shared", {}):
        return scoped["shared"][key].get("value")
    return None


def list_app_secrets(app_name, scope=None):
    scoped = load_scoped_app_secrets(app_name)
    items = []

    scopes = APP_SECRET_SCOPES if scope is None else (scope,)
    for env_scope in scopes:
        for key, data in scoped.get(env_scope, {}).items():
            items.append(
                {
                    "key": key,
                    "scope": env_scope,
                    "description": data.get("description", ""),
                    "updated_at": data.get("updated_at", ""),
                }
            )

    items.sort(key=lambda item: (item.get("key", ""), item.get("scope", "")))
    return items


def load_global_secrets():
    secrets_file = get_global_secrets_file()
    if not os.path.exists(secrets_file):
        return {}

    if is_encrypted(secrets_file):
        result = sops_decrypt(secrets_file)
        if not result["success"]:
            return {}
        try:
            data = yaml.safe_load(result["data"]) or {}
            return _normalize_secret_map(data.get("secrets", {}))
        except Exception:
            return {}

    try:
        with open(secrets_file, "r") as f:
            data = yaml.safe_load(f) or {}
            return _normalize_secret_map(data.get("secrets", {}))
    except Exception:
        return {}


def save_global_secrets(secrets):
    ensure_secrets_dir()
    secrets_file = get_global_secrets_file()
    temp_path = os.path.join(SECRETS_DIR, ".global.tmp.yaml")

    payload = {"secrets": _normalize_secret_map(secrets)}

    with open(temp_path, "w") as f:
        yaml.safe_dump(payload, f, default_flow_style=False, sort_keys=True)

    try:
        encrypt_result = sops_encrypt(temp_path)
        if encrypt_result["success"]:
            shutil.move(temp_path, secrets_file)
            os.chmod(secrets_file, 0o600)
            return {"success": True}
        os.unlink(temp_path)
        return encrypt_result
    except Exception as e:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        return {"success": False, "error": str(e)}


def get_global_secret(key):
    secrets = load_global_secrets()
    secret = secrets.get(key)
    if secret:
        return secret.get("value")
    return None


def set_global_secret(key, value, description=""):
    secrets = load_global_secrets()
    secrets[key] = {
        "value": value,
        "description": description,
        "updated_at": datetime.utcnow().isoformat(),
    }
    return save_global_secrets(secrets)


def export_secrets_for_deployment(app_name, environment="production"):
    app_scoped = load_scoped_app_secrets(app_name)
    global_secrets = load_global_secrets()

    env_vars = {}

    for key, data in global_secrets.items():
        env_vars[key] = data.get("value", "")

    for key, data in app_scoped.get("shared", {}).items():
        env_vars[key] = data.get("value", "")

    env_scope = environment if environment in APP_SECRET_SCOPES else "production"
    for key, data in app_scoped.get(env_scope, {}).items():
        env_vars[key] = data.get("value", "")

    return env_vars


def generate_env_file_content(app_name, environment="production", additional_vars=None):
    env_vars = export_secrets_for_deployment(app_name, environment)
    if additional_vars:
        env_vars.update(additional_vars)

    lines = []
    for key, value in sorted(env_vars.items()):
        if value and isinstance(value, str) and (" " in value or '"' in value or "'" in value):
            lines.append(f'{key}="{value}"')
        else:
            lines.append(f"{key}={value}")

    return "\n".join(lines)
