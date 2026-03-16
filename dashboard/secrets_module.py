import os
import subprocess
import yaml
import shutil

from datetime import datetime

SECRETS_DIR = "/opt/dashboard/secrets"
SOPS_CONFIG = "/opt/dashboard/.sops.yaml"
AGE_KEY_PATH = "/opt/dashboard/secrets/age.key"

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
            capture_output=True, text=True, env=env, cwd="/opt/dashboard"
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
            capture_output=True, text=True, env=env, cwd="/opt/dashboard"
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
            capture_output=True, text=True, env=env, cwd="/opt/dashboard"
        )
        return {"success": result.returncode == 0, "error": result.stderr if result.returncode != 0 else None}
    except Exception as e:
        return {"success": False, "error": str(e)}

def is_encrypted(file_path):
    if not os.path.exists(file_path):
        return False
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            return 'sops' in content and 'enc' in content
    except:
        return False

def load_app_secrets(app_name):
    secrets_file = get_secrets_file(app_name)
    
    if not os.path.exists(secrets_file):
        return {}
    
    if is_encrypted(secrets_file):
        result = sops_decrypt(secrets_file)
        if result["success"]:
            try:
                data = yaml.safe_load(result["data"])
                secrets = data.get("secrets", {}) if data else {}
                for k, v in secrets.items():
                    if isinstance(v.get("updated_at"), datetime):
                        v["updated_at"] = v["updated_at"].isoformat()
                return secrets
            except:
                return {}
        return {}
    else:
        with open(secrets_file, 'r') as f:
            data = yaml.safe_load(f)
            return data.get("secrets", {}) if data else {}

def save_app_secrets(app_name, secrets):
    ensure_secrets_dir()
    secrets_file = get_secrets_file(app_name)
    
    string_secrets = {}
    for k, v in secrets.items():
        string_secrets[k] = {
            "value": str(v.get("value", "")),
            "description": str(v.get("description", "")),
            "updated_at": str(v.get("updated_at", ""))
        }
    
    temp_path = os.path.join(SECRETS_DIR, f".{app_name}.tmp.yaml")
    
    with open(temp_path, 'w') as f:
        f.write('secrets:\n')
        for sk, sv in string_secrets.items():
            escaped_value = sv["value"].replace('\\', '\\\\').replace('"', '\\"')
            escaped_desc = sv["description"].replace('\\', '\\\\').replace('"', '\\"')
            escaped_time = sv["updated_at"].replace('\\', '\\\\').replace('"', '\\"')
            f.write(f'    {sk}:\n')
            f.write(f'        value: "{escaped_value}"\n')
            f.write(f'        description: "{escaped_desc}"\n')
            f.write(f'        updated_at: "{escaped_time}"\n')
    
    try:
        encrypt_result = sops_encrypt(temp_path)
        if encrypt_result["success"]:
            shutil.move(temp_path, secrets_file)
            os.chmod(secrets_file, 0o600)
            return {"success": True}
        else:
            os.unlink(temp_path)
            return encrypt_result
    except Exception as e:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        return {"success": False, "error": str(e)}

def set_app_secret(app_name, key, value, description=""):
    secrets = load_app_secrets(app_name)
    secrets[key] = {
        "value": value,
        "description": description,
        "updated_at": datetime.utcnow().isoformat()
    }
    return save_app_secrets(app_name, secrets)

def delete_app_secret(app_name, key):
    secrets = load_app_secrets(app_name)
    if key in secrets:
        del secrets[key]
        return save_app_secrets(app_name, secrets)
    return {"success": True}

def get_app_secret(app_name, key):
    secrets = load_app_secrets(app_name)
    secret = secrets.get(key)
    if secret:
        return secret.get("value")
    return None

def list_app_secrets(app_name):
    secrets = load_app_secrets(app_name)
    return [
        {"key": k, "description": v.get("description", ""), "updated_at": v.get("updated_at", "")}
        for k, v in secrets.items()
    ]

def load_global_secrets():
    secrets_file = get_global_secrets_file()
    
    if not os.path.exists(secrets_file):
        return {}
    
    if is_encrypted(secrets_file):
        result = sops_decrypt(secrets_file)
        if result["success"]:
            try:
                data = yaml.safe_load(result["data"])
                secrets = data.get("secrets", {}) if data else {}
                for k, v in secrets.items():
                    if isinstance(v.get("updated_at"), datetime):
                        v["updated_at"] = v["updated_at"].isoformat()
                return secrets
            except:
                return {}
        return {}
    else:
        with open(secrets_file, 'r') as f:
            data = yaml.safe_load(f)
            return data.get("secrets", {}) if data else {}

def save_global_secrets(secrets):
    ensure_secrets_dir()
    secrets_file = get_global_secrets_file()
    
    string_secrets = {}
    for k, v in secrets.items():
        string_secrets[k] = {
            "value": str(v.get("value", "")),
            "description": str(v.get("description", "")),
            "updated_at": str(v.get("updated_at", ""))
        }
    
    temp_path = os.path.join(SECRETS_DIR, ".global.tmp.yaml")
    
    with open(temp_path, 'w') as f:
        f.write('secrets:\n')
        for sk, sv in string_secrets.items():
            escaped_value = sv["value"].replace('\\', '\\\\').replace('"', '\\"')
            escaped_desc = sv["description"].replace('\\', '\\\\').replace('"', '\\"')
            escaped_time = sv["updated_at"].replace('\\', '\\\\').replace('"', '\\"')
            f.write(f'    {sk}:\n')
            f.write(f'        value: "{escaped_value}"\n')
            f.write(f'        description: "{escaped_desc}"\n')
            f.write(f'        updated_at: "{escaped_time}"\n')
    
    try:
        encrypt_result = sops_encrypt(temp_path)
        if encrypt_result["success"]:
            shutil.move(temp_path, secrets_file)
            os.chmod(secrets_file, 0o600)
            return {"success": True}
        else:
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
    from datetime import datetime
    secrets = load_global_secrets()
    secrets[key] = {
        "value": value,
        "description": description,
        "updated_at": datetime.utcnow().isoformat()
    }
    return save_global_secrets(secrets)

def export_secrets_for_deployment(app_name, environment="production"):
    app_secrets = load_app_secrets(app_name)
    global_secrets = load_global_secrets()
    
    env_vars = {}
    
    for key, data in global_secrets.items():
        env_vars[key] = data.get("value", "")
    
    for key, data in app_secrets.items():
        env_vars[key] = data.get("value", "")
    
    return env_vars

def generate_env_file_content(app_name, environment="production", additional_vars=None):
    env_vars = export_secrets_for_deployment(app_name, environment)
    
    if additional_vars:
        env_vars.update(additional_vars)
    
    lines = []
    for key, value in sorted(env_vars.items()):
        if value and isinstance(value, str) and (' ' in value or '"' in value or "'" in value):
            lines.append(f'{key}="{value}"')
        else:
            lines.append(f"{key}={value}")
    
    return "\n".join(lines)