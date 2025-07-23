import os
import secrets
import string
import hashlib
import toml

def generate_password(length: int = 12) -> str:
    """
    Generate a secure random password with upper, lower, digits, and special chars.
    """
    alphabet = string.ascii_letters + string.digits + string.punctuation
    while True:
        pw = ''.join(secrets.choice(alphabet) for _ in range(length))
        if len(pw) >= length and any(c in string.punctuation for c in pw):
            return pw

def hash_password(raw_password: str) -> str:
    """
    Return the SHA-256 hash of the provided raw password.
    """
    return hashlib.sha256(raw_password.encode()).hexdigest()

def update_secrets_for_user(username: str, length: int = 12,
                            secrets_path: str = ".streamlit/secrets.toml") -> str:
    """
    For EXISTING USER only! Updates their password hash in [users] and [auth].
    Returns the new plain password.
    """
    if not os.path.exists(secrets_path):
        raise FileNotFoundError(f"File not found: {secrets_path}")

    data = toml.load(secrets_path)
    users = data.get("users", {})
    if username not in users:
        raise ValueError(f"User '{username}' not found in {secrets_path}!")

    api_key = users[username].get("api_key")
    workspace_id = users[username].get("workspace_id")
    raw = generate_password(length)
    pw_hash = hash_password(raw)

    # Update sections
    data["users"][username]["password_hash"] = pw_hash
    data.setdefault("auth", {})[username] = {"password_hash": pw_hash}

    # Save file
    with open(secrets_path, "w") as f:
        toml.dump(data, f)

    return raw

if __name__ == "__main__":
    # Пример использования — только для существующего пользователя!
    username = input("Username: ").strip()
    try:
        new_pw = update_secrets_for_user(username, length=14)
        print(f"Neues Passwort für '{username}': {new_pw}")
        print("Hash gespeichert in .streamlit/secrets.toml")
    except Exception as e:
        print("Error:", e)
