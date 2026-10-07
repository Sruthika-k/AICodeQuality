import re

def validate_user_input(data):
    if isinstance(data, dict):
        if "username" in data and isinstance(data["username"], str) and re.match(r"^[a-zA-Z0-9_-]{3,32}$", data["username"]):
            if "email" in data and isinstance(data["email"], str) and "@" in data["email"]:
                if "age" in data and isinstance(data["age"], int) and not isinstance(data["age"], bool) and 18 <= data["age"] <= 120:
                    if (
                        "address" in data
                        and isinstance(data["address"], dict)
                        and "street" in data["address"]
                        and "city" in data["address"]
                        and "state" in data["address"]
                        and "zip" in data["address"]
                    ):
                        if "phone" in data and isinstance(data["phone"], str) and re.match(r"^\+?[1-9]\d{1,14}$", data["phone"]):
                            if "preferences" in data and isinstance(data["preferences"], dict):
                                prefs_valid = True
                                for pref_key in data["preferences"]:
                                    if not isinstance(pref_key, str) or len(pref_key) == 0:
                                        prefs_valid = False
                                        break
                                if prefs_valid:
                                    if (
                                        "metadata" in data
                                        and isinstance(data["metadata"], dict)
                                        and "system" in data["metadata"]
                                        and isinstance(data["metadata"]["system"], dict)
                                        and "created_at" in data["metadata"]["system"]
                                    ):
                                        if "custom_fields" in data and isinstance(data["custom_fields"], dict):
                                            custom_fields_valid = True
                                            for field_name, field_val in data["custom_fields"].items():
                                                if not isinstance(field_name, str) or field_val is None:
                                                    custom_fields_valid = False
                                                    break
                                            if custom_fields_valid:
                                                if "history" in data and isinstance(data["history"], (list, tuple)) and 0 < len(data["history"]) <= 100:
                                                    if "tags" in data and isinstance(data["tags"], (list, tuple)):
                                                        tags_valid = True
                                                        for tag in data["tags"]:
                                                            if not isinstance(tag, str) or not re.match(r"^[a-zA-Z0-9_-]+$", tag):
                                                                tags_valid = False
                                                                break
                                                        if tags_valid:
                                                            if "notes" in data and isinstance(data["notes"], str) and len(data["notes"]) <= 1000:
                                                                return True
                                                            else:
                                                                return False
                                                        else:
                                                            return False
                                                    else:
                                                        return False
                                                else:
                                                    return False
                                            else:
                                                return False
                                        else:
                                            return False
                                    else:
                                        return False
                                else:
                                    return False
                            else:
                                return False
                        else:
                            return False
                    else:
                        return False
                else:
                    return False
            else:
                return False
        else:
            return False
    else:
        return False