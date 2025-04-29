import json
from datetime import datetime

def validate_license_key(input_key, filename="valid_keys.json"):
    input_key_cleaned = input_key.replace("-", "").lower()
    
    try:
        with open(filename, 'r') as f:
            valid_keys = json.load(f)
    except FileNotFoundError:
        print("No valid keys file found.")
        return False

    for key_info in valid_keys:
        stored_key_cleaned = key_info['key'].replace("-", "").lower()

        if input_key_cleaned == stored_key_cleaned:
            if key_info["type"] == "permanent":
                print("Permanent License Validated!")
                return True
            elif key_info["type"] == "temporary":
                expires_at = key_info.get("expires_at")
                if not expires_at:
                    print("Temporary license missing expiration date. Invalid license.")
                    return False
                expiration_time = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if datetime.utcnow() <= expiration_time:
                    print(f"Temporary License Validated! (expires {expires_at})")
                    return True
                else:
                    print(f"License has expired on {expires_at}.")
                    return False
            else:
                print("Unknown license type.")
                return False
    
    print("Invalid License Key.")
    return False
