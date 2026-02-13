def normalize_uzbek_phone(phone: str) -> str:
    text = str(phone or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        raise ValueError("phone must contain digits")

    # Accept already-prefixed Uzbek numbers: 998 + 9 local digits.
    if digits.startswith("998"):
        if len(digits) != 12:
            raise ValueError("phone must be in format +998XXXXXXXXX")
        return f"+{digits}"

    # Accept local number without country prefix: 9 digits.
    if len(digits) == 9:
        return f"+998{digits}"

    raise ValueError("phone must be in format +998XXXXXXXXX")
