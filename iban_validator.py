"""
IBAN Validator — Full country registry + ISO 13616 mod-97 checksum.
Supports 80+ countries with per-country length and BBAN format validation.
"""

import re

# IBAN country registry: country_code -> (total_length, bban_regex_pattern)
# Source: SWIFT IBAN Registry
# n = digits, a = uppercase letters, c = alphanumeric
COUNTRY_REGISTRY = {
    "AD": (24, r"\d{8}[A-Z0-9]{12}"),               # Andorra
    "AE": (23, r"\d{19}"),                            # UAE
    "AL": (28, r"\d{8}[A-Z0-9]{16}"),                # Albania
    "AO": (25, r"\d{21}"),                            # Angola
    "AT": (20, r"\d{16}"),                            # Austria
    "AZ": (28, r"[A-Z]{4}[A-Z0-9]{20}"),             # Azerbaijan
    "BA": (20, r"\d{16}"),                            # Bosnia
    "BF": (28, r"[A-Z]{2}\d{22}"),                   # Burkina Faso
    "BE": (16, r"\d{12}"),                            # Belgium
    "BJ": (28, r"[A-Z]{2}\d{22}"),                   # Benin
    "BG": (22, r"[A-Z]{4}\d{6}[A-Z0-9]{8}"),         # Bulgaria
    "BH": (22, r"[A-Z]{4}[A-Z0-9]{14}"),             # Bahrain
    "BI": (27, r"\d{23}"),                            # Burundi
    "BR": (29, r"\d{23}[A-Z]{1}[A-Z0-9]{1}"),        # Brazil
    "BY": (28, r"[A-Z0-9]{4}\d{20}"),                # Belarus
    "CH": (21, r"\d{17}"),                            # Switzerland
    "CI": (28, r"[A-Z]{2}\d{22}"),                   # Côte d'Ivoire
    "CM": (27, r"\d{23}"),                            # Cameroon
    "CR": (22, r"0\d{17}"),                           # Costa Rica
    "CV": (25, r"\d{21}"),                            # Cape Verde
    "CF": (27, r"\d{23}"),                            # Central African Republic
    "CG": (27, r"\d{23}"),                            # Congo
    "CY": (28, r"\d{8}[A-Z0-9]{16}"),                # Cyprus
    "CZ": (24, r"\d{20}"),                            # Czech Republic
    "DE": (22, r"\d{18}"),                            # Germany
    "DJ": (27, r"\d{23}"),                            # Djibouti
    "DK": (18, r"\d{14}"),                            # Denmark
    "DO": (28, r"[A-Z0-9]{4}\d{20}"),                # Dominican Republic
    "DZ": (26, r"\d{22}"),                            # Algeria
    "EE": (20, r"\d{16}"),                            # Estonia
    "EG": (29, r"\d{25}"),                            # Egypt
    "ES": (24, r"\d{20}"),                            # Spain
    "FI": (18, r"\d{14}"),                            # Finland
    "FK": (18, r"[A-Z]{2}\d{12}"),                    # Falkland Islands
    "FO": (18, r"\d{14}"),                            # Faroe Islands
    "FR": (27, r"\d{10}[A-Z0-9]{11}\d{2}"),          # France
    "GB": (22, r"[A-Z]{4}\d{14}"),                    # United Kingdom
    "GE": (22, r"[A-Z]{2}\d{16}"),                    # Georgia
    "GA": (27, r"\d{23}"),                            # Gabon
    "GI": (23, r"[A-Z]{4}[A-Z0-9]{15}"),             # Gibraltar
    "GL": (18, r"\d{14}"),                            # Greenland
    "GN": (28, r"[A-Z]{2}\d{22}"),                   # Guinea
    "GQ": (27, r"\d{23}"),                            # Equatorial Guinea
    "GR": (27, r"\d{7}[A-Z0-9]{16}"),                # Greece
    "GT": (28, r"[A-Z0-9]{24}"),                      # Guatemala
    "GW": (25, r"[A-Z]{2}\d{19}"),                   # Guinea-Bissau
    "HR": (21, r"\d{17}"),                            # Croatia
    "HU": (28, r"\d{24}"),                            # Hungary
    "IE": (22, r"[A-Z]{4}\d{14}"),                    # Ireland
    "IL": (23, r"\d{19}"),                            # Israel
    "IQ": (23, r"[A-Z]{4}\d{15}"),                    # Iraq
    "IS": (26, r"\d{22}"),                            # Iceland
    "IT": (27, r"[A-Z]{1}\d{10}[A-Z0-9]{12}"),       # Italy
    "JO": (30, r"[A-Z]{4}\d{4}[A-Z0-9]{18}"),        # Jordan
    "KW": (30, r"[A-Z]{4}[A-Z0-9]{22}"),             # Kuwait
    "KZ": (20, r"\d{3}[A-Z0-9]{13}"),                # Kazakhstan
    "LB": (28, r"\d{4}[A-Z0-9]{20}"),                # Lebanon
    "LC": (32, r"[A-Z]{4}[A-Z0-9]{24}"),             # Saint Lucia
    "LI": (21, r"\d{17}"),                            # Liechtenstein
    "LT": (20, r"\d{16}"),                            # Lithuania
    "LU": (20, r"\d{3}[A-Z0-9]{13}"),                # Luxembourg
    "LV": (21, r"[A-Z]{4}[A-Z0-9]{13}"),             # Latvia
    "LY": (25, r"\d{21}"),                            # Libya
    "KM": (27, r"\d{23}"),                            # Comoros
    "MA": (28, r"\d{24}"),                            # Morocco
    "MC": (27, r"\d{10}[A-Z0-9]{11}\d{2}"),          # Monaco
    "MD": (24, r"[A-Z0-9]{20}"),                      # Moldova
    "ME": (22, r"\d{18}"),                            # Montenegro
    "MK": (19, r"\d{3}[A-Z0-9]{10}\d{2}"),           # North Macedonia
    "MG": (27, r"\d{23}"),                            # Madagascar
    "ML": (28, r"[A-Z]{2}\d{22}"),                   # Mali
    "MN": (20, r"\d{16}"),                            # Mongolia
    "MR": (27, r"\d{23}"),                            # Mauritania
    "MT": (31, r"[A-Z]{4}\d{5}[A-Z0-9]{18}"),        # Malta
    "MU": (30, r"[A-Z]{4}\d{19}[A-Z]{3}"),           # Mauritius
    "MZ": (25, r"\d{21}"),                            # Mozambique
    "NE": (28, r"[A-Z]{2}\d{22}"),                   # Niger
    "NI": (28, r"[A-Z]{4}\d{20}"),                    # Nicaragua
    "NL": (18, r"[A-Z]{4}\d{10}"),                    # Netherlands
    "NO": (15, r"\d{11}"),                            # Norway
    "OM": (23, r"\d{3}[A-Z0-9]{16}"),                # Oman
    "PK": (24, r"[A-Z]{4}[A-Z0-9]{16}"),             # Pakistan
    "PL": (28, r"\d{24}"),                            # Poland
    "PS": (29, r"[A-Z]{4}[A-Z0-9]{21}"),             # Palestine
    "PT": (25, r"\d{21}"),                            # Portugal
    "QA": (29, r"[A-Z]{4}[A-Z0-9]{21}"),             # Qatar
    "RO": (24, r"[A-Z]{4}[A-Z0-9]{16}"),             # Romania
    "RS": (22, r"\d{18}"),                            # Serbia
    "RU": (33, r"\d{14}[A-Z0-9]{15}"),               # Russia
    "SA": (24, r"\d{2}[A-Z0-9]{18}"),                # Saudi Arabia
    "SC": (31, r"[A-Z]{4}\d{20}[A-Z]{3}"),           # Seychelles
    "SD": (18, r"\d{14}"),                            # Sudan
    "SE": (24, r"\d{20}"),                            # Sweden
    "SI": (19, r"\d{15}"),                            # Slovenia
    "SN": (28, r"[A-Z]{2}\d{22}"),                   # Senegal
    "SK": (24, r"\d{20}"),                            # Slovakia
    "SM": (27, r"[A-Z]{1}\d{10}[A-Z0-9]{12}"),       # San Marino
    "SO": (23, r"\d{19}"),                            # Somalia
    "ST": (25, r"\d{21}"),                            # São Tomé
    "SV": (28, r"[A-Z]{4}\d{20}"),                    # El Salvador
    "TG": (28, r"[A-Z]{2}\d{22}"),                   # Togo
    "TD": (27, r"\d{23}"),                            # Chad
    "TL": (23, r"\d{19}"),                            # Timor-Leste
    "TN": (24, r"\d{20}"),                            # Tunisia
    "TR": (26, r"\d{6}[A-Z0-9]{16}"),                # Turkey
    "UA": (29, r"\d{6}[A-Z0-9]{19}"),                # Ukraine
    "VA": (22, r"\d{18}"),                            # Vatican
    "VG": (24, r"[A-Z]{4}\d{16}"),                    # British Virgin Islands
    "XK": (20, r"\d{16}"),                            # Kosovo
}

# Extract just lengths for quick lookup
COUNTRY_LENGTHS = {code: length for code, (length, _) in COUNTRY_REGISTRY.items()}


def clean_iban(raw: str) -> str:
    """Remove spaces, dashes, dots and normalize to uppercase."""
    return re.sub(r"[\s\-\.]", "", raw).upper()


def validate_iban(iban: str) -> dict:
    """
    Validate a single IBAN. Returns a dict with:
      - iban: cleaned IBAN string
      - valid: bool
      - country: 2-letter country code
      - errors: list of error messages (empty if valid)
    """
    iban = clean_iban(iban)
    errors = []

    # Basic format
    if len(iban) < 5:
        return {"iban": iban, "valid": False, "country": None, "errors": ["IBAN too short"]}

    country_code = iban[:2]
    check_digits = iban[2:4]
    bban = iban[4:]

    # Country check
    if country_code not in COUNTRY_REGISTRY:
        errors.append(f"Unknown country code: {country_code}")
        return {"iban": iban, "valid": False, "country": country_code, "errors": errors}

    expected_length, bban_pattern = COUNTRY_REGISTRY[country_code]

    # Length check
    if len(iban) != expected_length:
        errors.append(
            f"Invalid length for {country_code}: expected {expected_length}, got {len(iban)}"
        )

    # Check digits must be numeric
    if not check_digits.isdigit():
        errors.append(f"Check digits are not numeric: {check_digits}")

    # BBAN format check
    if not re.fullmatch(bban_pattern, bban):
        errors.append(f"BBAN format invalid for {country_code}")

    # Mod-97 checksum (ISO 13616)
    if not errors or (len(errors) == 0):
        rearranged = iban[4:] + iban[:4]
        numeric_str = ""
        for char in rearranged:
            if char.isdigit():
                numeric_str += char
            elif char.isalpha():
                numeric_str += str(ord(char) - 55)  # A=10, B=11, ..., Z=35
            else:
                errors.append(f"Invalid character in IBAN: '{char}'")
                break

        if not errors:
            if int(numeric_str) % 97 != 1:
                errors.append("Mod-97 checksum failed — possible transcription error")

    return {
        "iban": iban,
        "valid": len(errors) == 0,
        "country": country_code,
        "errors": errors,
    }


def format_iban(iban: str) -> str:
    """Format IBAN in standard groups of 4 characters."""
    iban = clean_iban(iban)
    return " ".join(iban[i:i+4] for i in range(0, len(iban), 4))


def get_country_name(code: str) -> str:
    """Return a human-readable country name from the 2-letter code."""
    names = {
        "AD": "Andorra", "AE": "United Arab Emirates", "AL": "Albania",
        "AO": "Angola", "AT": "Austria", "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina",
        "BF": "Burkina Faso", "BE": "Belgium", "BJ": "Benin", "BG": "Bulgaria",
        "BH": "Bahrain", "BI": "Burundi",
        "BR": "Brazil", "BY": "Belarus", "CH": "Switzerland", "CR": "Costa Rica",
        "CF": "Central African Republic", "CG": "Congo", "CI": "Côte d'Ivoire",
        "CM": "Cameroon", "CV": "Cape Verde", "CY": "Cyprus",
        "CZ": "Czech Republic", "DE": "Germany", "DJ": "Djibouti", "DK": "Denmark",
        "DO": "Dominican Republic", "DZ": "Algeria", "EE": "Estonia", "EG": "Egypt",
        "ES": "Spain", "FI": "Finland", "FK": "Falkland Islands", "FO": "Faroe Islands",
        "FR": "France", "GA": "Gabon", "GB": "United Kingdom", "GE": "Georgia",
        "GI": "Gibraltar", "GL": "Greenland", "GN": "Guinea", "GQ": "Equatorial Guinea",
        "GR": "Greece", "GT": "Guatemala", "GW": "Guinea-Bissau", "HR": "Croatia",
        "HU": "Hungary", "IE": "Ireland", "IL": "Israel", "IQ": "Iraq",
        "IS": "Iceland", "IT": "Italy", "JO": "Jordan", "KW": "Kuwait",
        "KM": "Comoros", "KZ": "Kazakhstan", "LB": "Lebanon", "LC": "Saint Lucia",
        "LI": "Liechtenstein", "LT": "Lithuania", "LU": "Luxembourg",
        "LV": "Latvia", "LY": "Libya", "MA": "Morocco", "MC": "Monaco",
        "MD": "Moldova", "ME": "Montenegro", "MG": "Madagascar", "MK": "North Macedonia",
        "ML": "Mali", "MN": "Mongolia", "MR": "Mauritania", "MT": "Malta",
        "MU": "Mauritius", "MZ": "Mozambique", "NE": "Niger", "NI": "Nicaragua",
        "NL": "Netherlands", "NO": "Norway", "OM": "Oman",
        "PK": "Pakistan", "PL": "Poland", "PS": "Palestine", "PT": "Portugal",
        "QA": "Qatar", "RO": "Romania", "RS": "Serbia", "RU": "Russia",
        "SA": "Saudi Arabia", "SC": "Seychelles", "SD": "Sudan", "SE": "Sweden",
        "SI": "Slovenia", "SK": "Slovakia", "SM": "San Marino", "SN": "Senegal",
        "SO": "Somalia", "ST": "São Tomé and Príncipe", "SV": "El Salvador",
        "TD": "Chad", "TG": "Togo", "TL": "Timor-Leste", "TN": "Tunisia",
        "TR": "Turkey", "UA": "Ukraine", "VA": "Vatican City",
        "VG": "British Virgin Islands", "XK": "Kosovo",
    }
    return names.get(code, code)
