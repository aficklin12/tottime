import json
import re
import requests
from bs4 import BeautifulSoup

API_URL = "https://theicn.org/cnrb/wp-json/wp-ultimate-post-grid/v1/items"

HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Expires": "0",
    "Origin": "https://theicn.org",
    "Pragma": "no-cache",
    "Referer": "https://theicn.org/cnrb/recipes-cacfp-centers/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "X-WP-Nonce": "2f6380fc2b",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

# If you get 403, refresh the nonce and cookie from DevTools (Copy as cURL).
COOKIES_HEADER = "_gid=GA1.2.2096235166.1771519526; _ga_CY0EN3HPFD=GS2.1.s1771521915$o17$g1$t1771521915$j60$l0$h0; _ga=GA1.2.1305685482.1767721549; _gat_gtag_UA_63546838_8=1"

PAYLOAD = {
    "id": "162987",
    "args": {
        "type": "load_all",
        "filters": [
            {
                "type": "terms",
                "terms": {"wprm_program_meal_type": ["lunch"]},
                "terms_inverse": False,
                "terms_relation": "OR",
            }
        ],
        "loaded_ids": [149454,149869,135654,1190,796,112020,69,903,124414,914,149831,149461,124695,124718,960,146817,146963,147164,146831,1194,1197,146844,147179,1371],
        "dynamic_rules": [],
    },
}

OUTPUT_FILE = "recipes_reference.json"
UNIQUE_INGREDIENTS_PATH = r"C:\Users\afick\OneDrive\Python Scripts\unique_ingredients.json"


def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


def is_or_marker(text):
    if not text:
        return False
    cleaned = clean_text(text)
    cleaned = cleaned.strip("-* ").upper()
    return cleaned == "OR"


def normalize_ingredient_name(text):
    cleaned = clean_text(text).lower()
    cleaned = re.sub(r"\([^)]*\)", "", cleaned)
    cleaned = cleaned.replace("*", "")
    cleaned = re.sub(r"[^a-z0-9\s-]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned:
        cleaned = apply_aliases(cleaned)
    return cleaned


def load_normalized_map(path):
    with open(path, "r", encoding="utf-8") as f:
        items = json.load(f)
    mapping = {}
    for item in items:
        key = normalize_ingredient_name(str(item))
        if key and key not in mapping:
            mapping[key] = item
    return mapping


ALIASES = {
    "catsup": "ketchup",
}


def apply_aliases(text):
    updated = text
    for src, dest in ALIASES.items():
        updated = re.sub(rf"\b{re.escape(src)}\b", dest, updated)
    return updated


def map_to_normalized(raw, normalized_map, normalized_keys):
    key = normalize_ingredient_name(raw)
    if key in normalized_map:
        return normalized_map[key]
    for norm_key in normalized_keys:
        if norm_key and norm_key in key:
            return normalized_map[norm_key]
    return raw


def extract_urls(payload):
    urls = []
    if isinstance(payload, dict):
        if payload.get("@type") == "ListItem" and "url" in payload:
            urls.append(payload["url"])
        for value in payload.values():
            urls.extend(extract_urls(value))
    elif isinstance(payload, list):
        for item in payload:
            urls.extend(extract_urls(item))
    return urls


def extract_recipe_name(soup):
    h1 = soup.find("h1")
    if h1:
        return clean_text(h1.get_text())
    title = soup.find("title")
    if title:
        return clean_text(title.get_text())
    return ""


def is_heading_tag(tag):
    return bool(tag and tag.name and re.fullmatch(r"h[1-6]", tag.name))


def get_content_root(soup):
    selectors = [
        "article .entry-content",
        "article",
        ".entry-content",
        "main",
        "body",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            return node
    return soup


def heading_matches(text, keyword):
    upper = clean_text(text).upper()
    keyword = keyword.upper()
    return upper == keyword or upper.startswith(f"{keyword} ")


def find_section_start(container, keywords):
    for tag in container.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = clean_text(tag.get_text(" ", strip=True))
        if not text:
            continue
        if any(heading_matches(text, keyword) for keyword in keywords):
            return tag
    for tag in container.find_all(["strong", "b"]):
        text = clean_text(tag.get_text(" ", strip=True))
        if not text:
            continue
        if any(heading_matches(text, keyword) for keyword in keywords):
            return tag
    return None


def is_boilerplate_line(line):
    upper = line.upper()
    if upper in {"GO TO TOP", "PAGE LOAD LINK", "CNRB - SPANISH"}:
        return True
    if "ANNOUNCEMENT" in upper and "ICN" in upper:
        return True
    if "ADD TO COOKBOOK" in upper:
        return True
    return False


def dedupe_lines(lines):
    seen = set()
    cleaned = []
    for line in lines:
        key = line.strip()
        if not key or key in seen or is_boilerplate_line(key):
            continue
        seen.add(key)
        cleaned.append(line)
    return cleaned


def extract_section_lines(start_tag, stop_keywords):
    if not start_tag:
        return []
    stop_upper = {keyword.upper() for keyword in stop_keywords}
    lines = []
    for sibling in start_tag.next_siblings:
        if not hasattr(sibling, "name"):
            text = clean_text(str(sibling))
            if text:
                lines.append(text)
            continue
        if hasattr(sibling, "name"):
            if is_heading_tag(sibling):
                heading_text = clean_text(sibling.get_text(" ", strip=True)).upper()
                if any(heading_matches(heading_text, keyword) for keyword in stop_upper):
                    break
            if sibling.name in {"script", "style", "nav", "footer"}:
                continue
            if hasattr(sibling, "find_all"):
                inner_heading = None
                for candidate in sibling.find_all(True):
                    if is_heading_tag(candidate):
                        inner_heading = candidate
                        break
                if inner_heading:
                    heading_text = clean_text(inner_heading.get_text(" ", strip=True)).upper()
                    if any(heading_matches(heading_text, keyword) for keyword in stop_upper):
                        break
            if sibling.name in {"ul", "ol"}:
                for li in sibling.find_all("li"):
                    text = clean_text(li.get_text(" ", strip=True))
                    if text:
                        lines.append(text)
                continue
            if sibling.name == "table":
                for tr in sibling.find_all("tr"):
                    cells = [clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["td", "th"])]
                    cells = [cell for cell in cells if cell]
                    if cells:
                        lines.append(" ".join(cells))
                continue
            text = clean_text(sibling.get_text(" ", strip=True))
            if text:
                lines.append(text)
    return dedupe_lines(lines)


def extract_instructions(soup):
    container = get_content_root(soup)
    wprm_instructions = container.select(".wprm-recipe-instructions-container .wprm-recipe-instruction-text")
    if wprm_instructions:
        lines = []
        for item in wprm_instructions:
            text = clean_text(item.get_text(" ", strip=True))
            if text:
                lines.append(text)
        return dedupe_lines(lines)
    start_tag = find_section_start(container, ["INSTRUCTIONS", "DIRECTIONS", "METHOD"])
    return extract_section_lines(start_tag, ["NUTRITION", "INGREDIENTS", "CACFP CREDITING INFORMATION", "CREDITING INFORMATION"])


def extract_nutrition(soup):
    container = get_content_root(soup)
    nutrition_container = container.select_one(".wprm-nutrition-label-container")
    if nutrition_container:
        lines = []
        for block in nutrition_container.select(".wprmp-nutrition-label-block-text, .wprmp-nutrition-label-block-serving, .wprmp-nutrition-label-block-nutrient, .wprmp-nutrition-label-block-text-disclaimer"):
            text = clean_text(block.get_text(" ", strip=True))
            if text:
                lines.append(text)
        return dedupe_lines(lines)
    start_tag = find_section_start(container, ["NUTRITION"])
    return extract_section_lines(start_tag, ["INGREDIENTS", "INSTRUCTIONS", "DIRECTIONS", "METHOD"])


def table_headers(table):
    headers = [clean_text(th.get_text()) for th in table.find_all("th")]
    if headers:
        return headers
    first_row = table.find("tr")
    if not first_row:
        return []
    return [clean_text(cell.get_text()) for cell in first_row.find_all(["td", "th"])]


def is_ingredient_table(table):
    headers = table_headers(table)
    header_text = " ".join(headers).upper()
    if "NUTRITION" in header_text:
        return False
    if "INGREDIENT" in header_text:
        return True
    if "WEIGHT" in header_text or "MEA-SURE" in header_text or "MEASURE" in header_text:
        return True
    if "QUANTITY" in header_text:
        return True
    return False


def parse_ingredient_table(table):
    rows = []
    header_tokens = {"INGREDIENTS", "INGREDIENT", "QUANTITY", "WEIGHT", "MEA-SURE", "MEASURE"}
    skip_next = False
    for tr in table.find_all("tr"):
        cells = [clean_text(cell.get_text()) for cell in tr.find_all(["td", "th"])]
        if not cells:
            continue
        if all((not cell) or (cell.upper() in header_tokens) for cell in cells):
            continue
        ingredient = cells[0] if cells else ""
        if not ingredient:
            continue
        if skip_next:
            skip_next = False
            continue
        if is_or_marker(ingredient):
            skip_next = True
            continue
        if ingredient.upper() in {"CALORIES", "TOTAL FAT", "SATURATED FAT", "CHOLESTEROL", "SODIUM", "TOTAL CARBOHYDRATE", "DIETARY FIBER", "TOTAL SUGARS", "PROTEIN"}:
            continue
        if ingredient.strip("- ").upper() in {"- -", "--", "-"}:
            continue
        weight = cells[1] if len(cells) > 1 else ""
        measure = cells[2] if len(cells) > 2 else ""
        if weight in {"-", "--", "- -"}:
            weight = ""
        if measure in {"-", "--", "- -"}:
            measure = ""
        qty_parts = [part for part in [weight, measure] if part]
        quantity = " ".join(qty_parts).strip()
        if not quantity and len(cells) == 2:
            quantity = cells[1]
        rows.append({"ingredient": ingredient, "quantity": quantity})
    return rows


def iter_recipe_objects(data):
    if isinstance(data, dict):
        recipe_type = data.get("@type")
        if recipe_type == "Recipe" or (isinstance(recipe_type, list) and "Recipe" in recipe_type):
            yield data
        for value in data.values():
            yield from iter_recipe_objects(value)
    elif isinstance(data, list):
        for item in data:
            yield from iter_recipe_objects(item)


def extract_recipe_json_ld(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for recipe in iter_recipe_objects(data):
            return recipe
    return None


UNITS = {
    "lb", "lbs", "pound", "pounds", "oz", "ounce", "ounces", "g", "kg", "mg",
    "ml", "l", "liter", "liters", "cup", "cups", "tbsp", "tablespoon",
    "tablespoons", "tsp", "teaspoon", "teaspoons", "qt", "quart", "quarts",
    "pt", "pint", "pints", "gal", "gallon", "gallons", "fl", "#", "ea",
    "each", "dozen", "ct", "can", "cans", "pkg", "pkgs", "package",
    "packages", "bag", "bags", "bunch", "bunches", "head", "heads",
    "slice", "slices", "clove", "cloves", "stick", "sticks",
}

FRACTION_CHARS = set("¼½¾⅐⅑⅒⅓⅔⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞")

FRACTION_TO_VALUE = {
    "¼": 1 / 4,
    "½": 1 / 2,
    "¾": 3 / 4,
    "⅐": 1 / 7,
    "⅑": 1 / 9,
    "⅒": 1 / 10,
    "⅓": 1 / 3,
    "⅔": 2 / 3,
    "⅕": 1 / 5,
    "⅖": 2 / 5,
    "⅗": 3 / 5,
    "⅘": 4 / 5,
    "⅙": 1 / 6,
    "⅚": 5 / 6,
    "⅛": 1 / 8,
    "⅜": 3 / 8,
    "⅝": 5 / 8,
    "⅞": 7 / 8,
}

VALUE_TO_FRACTION = {
    1 / 2: "½",
    1 / 3: "⅓",
    2 / 3: "⅔",
    1 / 4: "¼",
    3 / 4: "¾",
    1 / 5: "⅕",
    2 / 5: "⅖",
    3 / 5: "⅗",
    4 / 5: "⅘",
    1 / 6: "⅙",
    5 / 6: "⅚",
    1 / 8: "⅛",
    3 / 8: "⅜",
    5 / 8: "⅝",
    7 / 8: "⅞",
    1 / 10: "⅒",
    1 / 9: "⅑",
    1 / 7: "⅐",
}

SUPERSCRIPT_MAP = str.maketrans({
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
})

VOLUME_UNITS = {
    "tsp": 1,
    "teaspoon": 1,
    "teaspoons": 1,
    "tbsp": 3,
    "tablespoon": 3,
    "tablespoons": 3,
    "cup": 48,
    "cups": 48,
    "pt": 96,
    "pint": 96,
    "pints": 96,
    "qt": 192,
    "quart": 192,
    "quarts": 192,
    "gal": 768,
    "gallon": 768,
    "gallons": 768,
    "floz": 6,
    "fl": 6,
}

WEIGHT_UNITS = {
    "oz": 1,
    "ounce": 1,
    "ounces": 1,
    "lb": 16,
    "lbs": 16,
    "pound": 16,
    "pounds": 16,
    "g": 1 / 28.349523125,
    "kg": 35.27396195,
    "mg": 1 / 28349.523125,
}

COUNT_UNITS = {"each", "ea", "ct", "count", "counts", "can", "cans", "pkg", "pkgs"}


def split_quantity_ingredient(text):
    if not text:
        return "", ""
    cleaned = clean_text(text)
    cleaned = re.sub(r"^-+\s*", "", cleaned)
    cleaned = re.sub(r"^\*+", "", cleaned).strip()
    if not cleaned:
        return "", ""
    tokens = cleaned.split()
    qty_tokens = []
    idx = 0
    for token in tokens:
        stripped = token.strip(",;")
        lower = stripped.lower().rstrip(".")
        has_fraction = any(ch in FRACTION_CHARS for ch in stripped) or "⁄" in stripped
        if re.fullmatch(r"\d+(?:[/-]\d+)?", lower) or re.fullmatch(r"\d+/\d+", lower) or lower in UNITS or has_fraction:
            qty_tokens.append(stripped)
            idx += 1
            continue
        break
    quantity = " ".join(qty_tokens).strip()
    ingredient = " ".join(tokens[idx:]).strip().lstrip("*").strip()
    return ingredient, quantity


def strip_parentheticals(text):
    return re.sub(r"\([^)]*\)", "", text).strip()


def parse_number_token(token):
    if not token:
        return None
    if token in FRACTION_TO_VALUE:
        return FRACTION_TO_VALUE[token]
    token = token.translate(SUPERSCRIPT_MAP).replace("⁄", "/")
    token = token.strip()
    if not token:
        return None
    if "-" in token and "/" in token:
        left, right = token.split("-", 1)
        if left.isdigit() and re.fullmatch(r"\d+/\d+", right):
            num, den = right.split("/")
            return int(left) + (int(num) / int(den))
    if re.fullmatch(r"\d+/\d+", token):
        num, den = token.split("/")
        return int(num) / int(den)
    match = re.fullmatch(r"(\d+)(\d+/\d+)", token)
    if match:
        whole = int(match.group(1))
        num, den = match.group(2).split("/")
        return whole + (int(num) / int(den))
    match = re.fullmatch(r"(\d+)([¼½¾⅐⅑⅒⅓⅔⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞])", token)
    if match:
        whole = int(match.group(1))
        return whole + FRACTION_TO_VALUE[match.group(2)]
    if token.isdigit():
        return float(token)
    return None


def format_number(value):
    if value is None:
        return ""
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    whole = int(value)
    frac = value - whole
    if frac < 0:
        frac = 0
    closest = None
    min_diff = None
    for frac_value in VALUE_TO_FRACTION:
        diff = abs(frac - frac_value)
        if min_diff is None or diff < min_diff:
            min_diff = diff
            closest = frac_value
    if closest is not None and min_diff is not None and min_diff < 0.02:
        if closest >= 1 - 1e-6:
            return str(whole + 1)
        fraction_char = VALUE_TO_FRACTION.get(closest)
        if fraction_char:
            if whole == 0:
                return fraction_char
            return f"{whole}{fraction_char}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def format_volume(total_tsp):
    if total_tsp <= 0:
        return ""
    total_tsp = round(total_tsp * 8) / 8
    cups = int(total_tsp // 48)
    remaining = total_tsp - (cups * 48)
    tbsp = int(remaining // 3)
    tsp = remaining - (tbsp * 3)
    parts = []
    if cups:
        value = format_number(cups)
        unit = "cup" if value == "1" else "cups"
        parts.append(f"{value} {unit}")
    if tbsp:
        value = format_number(tbsp)
        unit = "Tbsp" if value == "1" else "Tbsp"
        parts.append(f"{value} {unit}")
    if tsp:
        value = format_number(tsp)
        unit = "tsp" if value == "1" else "tsp"
        parts.append(f"{value} {unit}")
    return " ".join(parts)


def format_weight(total_oz):
    if total_oz <= 0:
        return ""
    total_oz = round(total_oz * 8) / 8
    value = format_number(total_oz)
    unit = "oz" if value == "1" else "oz"
    return f"{value} {unit}".strip()


def format_count(total_each):
    if total_each <= 0:
        return ""
    total_each = round(total_each * 8) / 8
    value = format_number(total_each)
    return f"{value} each".strip()


def scale_quantity(quantity, scale=0.2):
    if not quantity:
        return quantity
    cleaned = strip_parentheticals(quantity)
    cleaned = cleaned.replace(",", " ")
    tokens = [token for token in cleaned.split() if token]
    total_tsp = 0.0
    total_oz = 0.0
    total_each = 0.0
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        value = parse_number_token(token)
        if value is None:
            idx += 1
            continue
        if idx + 2 < len(tokens):
            next_value = parse_number_token(tokens[idx + 1])
            next_unit = tokens[idx + 2].lower().strip(".,;")
            if next_value is not None and next_value < 1 and next_unit in (set(VOLUME_UNITS) | set(WEIGHT_UNITS) | COUNT_UNITS):
                value = value + next_value
                unit_token = next_unit
                idx += 3
            else:
                if idx + 1 < len(tokens):
                    unit_token = tokens[idx + 1].lower().strip(".,;")
                    idx += 2
                else:
                    idx += 1
                    continue
        elif idx + 1 < len(tokens):
            unit_token = tokens[idx + 1].lower().strip(".,;")
            idx += 2
        else:
            idx += 1
            continue

        unit_token = unit_token.replace("-", "")
        unit_token = unit_token.replace("/", "")
        if unit_token in VOLUME_UNITS:
            total_tsp += value * VOLUME_UNITS[unit_token]
        elif unit_token in WEIGHT_UNITS:
            total_oz += value * WEIGHT_UNITS[unit_token]
        elif unit_token in COUNT_UNITS:
            total_each += value

    parts = []
    if total_oz:
        parts.append(format_weight(total_oz * scale))
    if total_tsp:
        parts.append(format_volume(total_tsp * scale))
    if total_each:
        parts.append(format_count(total_each * scale))

    if not parts:
        return quantity
    return " ".join(part for part in parts if part)


def extract_ingredient_rows_from_json_ld(soup):
    recipe = extract_recipe_json_ld(soup)
    if not recipe:
        return []
    ingredients = recipe.get("recipeIngredient") or []
    rows = []
    skip_next = False
    for entry in ingredients:
        if skip_next:
            skip_next = False
            continue
        if is_or_marker(entry):
            skip_next = True
            continue
        ingredient, quantity = split_quantity_ingredient(entry)
        if not ingredient:
            ingredient = clean_text(entry)
        rows.append({"ingredient": ingredient, "quantity": quantity})
    return rows


def extract_ingredient_rows_from_wprm(soup, preferred_servings="25"):
    measure_groups = []
    for container in soup.select(".wprm-recipe-ingredients-container"):
        current_servings = None
        for group in container.select(".wprm-recipe-ingredient-group"):
            heading = group.find(["h3", "h4", "h5", "strong"])
            heading_text = clean_text(heading.get_text()) if heading else ""
            heading_upper = heading_text.upper()
            if "SERVING" in heading_upper:
                current_servings = heading_text
                continue
            if heading_upper == "MEASURE":
                items = [clean_text(li.get_text()) for li in group.select(".wprm-recipe-ingredient")]
                if items:
                    measure_groups.append({"servings": current_servings, "items": items})
    if not measure_groups:
        return []

    chosen = None
    if preferred_servings:
        for group in measure_groups:
            if group["servings"] and preferred_servings in group["servings"]:
                chosen = group
                break
    if not chosen:
        chosen = measure_groups[0]

    rows = []
    skip_next = False
    for entry in chosen["items"]:
        if skip_next:
            skip_next = False
            continue
        if is_or_marker(entry):
            skip_next = True
            continue
        ingredient, quantity = split_quantity_ingredient(entry)
        if not ingredient:
            continue
        rows.append({"ingredient": ingredient, "quantity": quantity})
    return rows


def extract_ingredient_rows(soup):
    rows = extract_ingredient_rows_from_wprm(soup)
    if rows:
        return rows
    rows = extract_ingredient_rows_from_json_ld(soup)
    if rows:
        return rows
    rows = []
    for table in soup.find_all("table"):
        if not is_ingredient_table(table):
            continue
        rows.extend(parse_ingredient_table(table))
    return rows


def extract_pdf_link(soup):
    """Extract the PDF link from the page."""
    # Look for links containing "pdf" or "PDF" in href
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = clean_text(link.get_text()).lower()
        
        # Check if link text mentions PDF or print
        if 'pdf' in text or 'print' in text or 'view/print' in text:
            if href.endswith('.pdf') or 'pdf' in href.lower():
                return href
    
    # Alternative: Look for links in specific container classes
    for container in soup.select('.recipe-actions, .wprm-recipe-container, article'):
        for link in container.find_all('a', href=True):
            href = link.get('href', '')
            if href.endswith('.pdf') or 'pdf' in href.lower():
                return href
    
    return None


def main():
    session = requests.Session()
    session.headers.update(HEADERS)
    if COOKIES_HEADER:
        session.headers.update({"Cookie": COOKIES_HEADER})

    normalized_map = load_normalized_map(UNIQUE_INGREDIENTS_PATH)
    normalized_keys = sorted(normalized_map.keys(), key=len, reverse=True)

    resp = session.post(API_URL, json=PAYLOAD, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    
    # Debug: Print response structure
    print(f"API Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
    if isinstance(data, dict):
        print(f"Response type: {type(data)}")
        if "html" in data:
            print(f"HTML content length: {len(data.get('html', ''))}")
        if "items" in data:
            print(f"Items count: {len(data.get('items', []))}")
    
    recipe_urls = list(dict.fromkeys(extract_urls(data)))
    print(f"Extracted {len(recipe_urls)} recipe URLs")

    results = []
    for url in recipe_urls:
        page = session.get(url, timeout=30)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, "html.parser")

        recipe_name = extract_recipe_name(soup)
        rows = extract_ingredient_rows(soup)
        instructions = extract_instructions(soup)
        nutrition = extract_nutrition(soup)
        pdf_link = extract_pdf_link(soup)  # NEW: Extract PDF link

        items = []
        for row in rows:
            raw = row["ingredient"]
            quantity = row.get("quantity", "")
            quantity = scale_quantity(quantity, scale=0.2)
            normalized_name = map_to_normalized(raw, normalized_map, normalized_keys)
            items.append({
                "ingredient": normalized_name,
                "quantity": quantity,
            })

        results.append({
            "recipe": recipe_name,
            "url": url,
            "pdf_url": pdf_link,  # NEW: Include PDF URL
            "items": items,
            "instructions": instructions,
            "nutrition": nutrition,
        })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Saved {OUTPUT_FILE} with {len(results)} recipes")
    
    # Print summary of PDF links found
    pdf_count = sum(1 for r in results if r.get("pdf_url"))
    print(f"Found PDF links for {pdf_count}/{len(results)} recipes")


if __name__ == "__main__":
    main()
