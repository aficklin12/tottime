import json
import re
import unicodedata

SOURCE_FILE = "ingredients_by_recipe.json"
OUTPUT_FILE = "unique_ingredients.json"


def clean_text(text):
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("ﬂ", "fl")
    text = re.sub(r"\bfl\s+our\b", "flour", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def normalize_ingredient(text):
    text = clean_text(text)
    if not text:
        return []
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("*", " ").replace("+", " ")
    text = text.replace("\\", " ")
    text = text.strip("`\"' ")
    text = text.replace(":", " ")
    text = re.sub(r"\b(usda recipe.*)$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\brecipe for\b.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\(.*$", "", text)
    text = re.sub(r"^[-_\s]+", "", text)
    text = re.sub(r"\b(see|variation|or)\b.*$", "", text, flags=re.IGNORECASE)
    tokens = text.split()
    unit_tokens = {
        "lb", "lbs", "oz", "cup", "cups", "tbsp", "tbs", "tablespoon", "tablespoons",
        "tsp", "teaspoon", "teaspoons", "g", "kg", "mg", "ml", "l", "clove", "cloves",
        "can", "cans", "pkg", "package", "packages", "pinch", "qt", "quart", "quarts",
        "pt", "pint", "pints", "gal", "gallon", "gallons", "fl", "fluid", "each",
    }
    descriptor_tokens = {
        "fresh", "frozen", "canned", "raw", "cooked", "dried", "ground", "minced", "chopped",
        "diced", "shredded", "sliced", "julienned", "grated", "peeled", "unpeeled",
        "skinless", "boneless", "seedless", "trimmed", "rinsed", "drained", "thawed",
        "reduced", "low", "fat", "unsweetened", "sweetened", "lean", "low-sodium",
        "table", "packed", "optional", "finely", "coarsely", "about", "sprays",
        "spray", "pieces", "piece", "slices", "slice", "liquid", "enriched", "fortified",
        "whole", "whole-grain", "wholegrain", "whole-wheat", "wholewheat", "low-fat",
        "nonfat", "fat-free", "reduced-fat", "salt-free", "no-salt-added", "no-salt",
        "added", "usda",
    }
    form_tokens = {
        "floret", "florets", "crown", "crowns", "kernel", "kernels", "flake", "flakes",
        "seed", "seeds", "blend", "mix", "style",
    }
    fraction_pattern = re.compile(r"[\u00BC-\u00BE\u2150-\u215E]")
    while tokens:
        tok = tokens[0].lower().strip(",;()")
        if re.search(r"\d", tok) or fraction_pattern.search(tok) or re.fullmatch(r"[\d/\.\-]+", tok) or tok in {"-", "--"}:
            tokens.pop(0)
            continue
        if tok in unit_tokens:
            tokens.pop(0)
            continue
        break
    cleaned = " ".join(tokens).strip(" ,;.")
    if "," in cleaned:
        cleaned = cleaned.split(",", 1)[0]
    cleaned = re.split(r"\bwith\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
    cleaned = re.sub(r"\b\d+\s*(in|inch|inches|\")\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+/\d+\s*(in|inch|inches|\")\b", "", cleaned, flags=re.IGNORECASE)
    cleaned_tokens = []
    for tok in cleaned.split():
        tok_clean = tok.lower().strip(",;()")
        if tok_clean in descriptor_tokens:
            continue
        if tok_clean in unit_tokens:
            continue
        if tok_clean in form_tokens:
            continue
        if re.search(r"\d", tok_clean) or fraction_pattern.search(tok_clean) or re.fullmatch(r"[\d/\.\-]+", tok_clean):
            continue
        if tok_clean in {"and", "or"}:
            continue
        cleaned_tokens.append(tok)
    if not cleaned_tokens:
        return []
    last = cleaned_tokens[-1]
    if len(last) > 3:
        if last.lower().endswith("ies"):
            last = last[:-3] + "y"
        elif last.lower().endswith("es") and last.lower()[-3:-2] in {"s", "x", "z", "c", "h"}:
            last = last[:-2]
        elif last.lower().endswith("s") and not last.lower().endswith("ss"):
            last = last[:-1]
        cleaned_tokens[-1] = last
    if cleaned_tokens[:2] == ["liquid", "egg"] or cleaned_tokens[:2] == ["liquid", "eggs"]:
        cleaned_tokens = ["egg"]
    if cleaned_tokens[:2] == ["egg", "white"]:
        cleaned_tokens = ["egg"]
    cleaned = " ".join(cleaned_tokens).strip(" ,;.")
    if cleaned.lower() in descriptor_tokens:
        return []
    if not cleaned:
        return []
    if not re.search(r"[A-Za-z]", cleaned):
        return []

    normalized = cleaned.lower()
    normalized = normalized.replace("edamame:", "edamame").strip()

    if normalized.startswith("\""):
        normalized = normalized.lstrip("\"").strip()
    normalized = normalized.replace("jalapeño", "jalapeno")
    normalized = normalized.replace("pepper. black", "black pepper")
    normalized = normalized.replace("chile", "chili")
    normalized = normalized.replace("bread crumb", "breadcrumb")
    normalized = normalized.replace("breadcrumbs", "breadcrumb")
    normalized = normalized.replace("couscou", "couscous")
    normalized = normalized.replace("canola oi", "canola oil")
    normalized = normalized.replace("canola oill", "canola oil")
    normalized = normalized.replace("green chily", "green chili")
    normalized = normalized.replace("great norther bean", "great northern bean")
    normalized = normalized.replace("whole-whet flour", "whole-wheat flour")
    normalized = normalized.replace("tomatoe", "tomato")
    normalized = normalized.replace("potatoe", "potato")
    normalized = normalized.replace("bay leave", "bay leaf")
    normalized = normalized.replace("basil leave", "basil leaf")
    normalized = normalized.replace("eggs.thawed", "egg")
    normalized = normalized.replace("eggs egg", "egg")
    normalized = normalized.replace("eggs", "egg")
    normalized = normalized.replace("half half", "half-and-half")
    normalized = normalized.replace("cream half half", "half-and-half")
    normalized = normalized.replace("tomato past", "tomato paste")
    normalized = normalized.replace("tomato paste paste", "tomato paste")
    normalized = normalized.replace("tomato pastee", "tomato paste")
    normalized = normalized.replace("tomato pastee paste", "tomato paste")
    normalized = normalized.replace("tomato purée", "tomato puree")
    normalized = normalized.replace("ts[ black pepper", "black pepper")
    normalized = normalized.replace("nonstick cooking spry", "nonstick cooking spray")
    normalized = normalized.replace("nonstick cooking", "nonstick cooking spray")
    normalized = normalized.replace("dill week", "dill weed")
    normalized = normalized.replace("vegetable ase", "vegetable base")
    normalized = normalized.replace("tomato paste paste", "tomato paste")
    normalized = normalized.replace("mint leave", "mint")
    normalized = normalized.replace("basil leaf", "basil")
    normalized = normalized.replace("zest juice lemon", "lemon")
    normalized = normalized.replace("to lime juice", "lime")
    normalized = normalized.replace("wedges lime", "lime")
    normalized = normalized.replace("mozzarella cheese", "mozzarella")
    normalized = normalized.replace("lasagna sheet", "lasagna noodle")
    normalized = normalized.replace("italian salad dressing", "italian dressing")
    normalized = normalized.replace("green bell pepper", "green pepper")
    normalized = normalized.replace("green chili enchilada sauce", "green chili")
    normalized = normalized.replace("catsup", "ketchup")
    normalized = normalized.replace("ole bay seasoning", "old bay seasoning")
    normalized = normalized.replace("onion powder-purpose flour", "onion powder")
    normalized = normalized.replace("oz. white cornmeal", "white cornmeal")
    normalized = normalized.replace("flour tortilla", "tortilla")
    normalized = normalized.replace("stir-fry/chinese egg noodle", "egg noodle")
    normalized = normalized.replace("waffles", "waffle")
    normalized = normalized.replace("all-purpose flour", "flour")
    normalized = normalized.replace("bread flour", "flour")
    normalized = normalized.replace("whole-wheat flour", "flour")

    if "jalapeno" in normalized:
        return ["jalapeno"]
    if "jerk seasoning" in normalized:
        return ["jerk seasoning"]
    if "mayonnaise" in normalized:
        return ["mayonnaise"]
    if "beef" in normalized:
        return ["beef"]
    if "cheddar" in normalized or normalized == "cheese":
        return ["cheese"]
    if "crumbled cornbread" in normalized:
        return ["cornbread"]
    if "cumin" in normalized:
        return ["cumin"]
    if "deli ham" in normalized or "extra-lean turkey ham" in normalized:
        return ["ham"]
    if "deli turkey" in normalized:
        return ["turkey"]
    if "garlic" in normalized:
        return ["garlic"]
    if "ginger" in normalized:
        return ["ginger"]
    if "granulated parsley" in normalized:
        return ["parsley"]
    if "granulated sugar" in normalized:
        return ["sugar"]
    if "ketchup" in normalized:
        return ["ketchup"]
    if "old bay seasoning" in normalized:
        return ["old bay seasoning"]
    if "onion" in normalized and "onion powder" in normalized:
        return ["onion"]
    if "pork" in normalized:
        return ["pork"]
    if "red chili" in normalized:
        return ["red chili"]
    if "reduce-fat cheddar cheese" in normalized:
        return ["cheese"]
    if "salmon" in normalized:
        return ["salmon"]
    if "sugar" == normalized:
        return ["sugar"]
    if "sweet potato" in normalized:
        return ["sweet potato"]
    if normalized.startswith("tomato paste"):
        return ["tomato paste"]
    if normalized.startswith("tomato puree"):
        return ["tomato puree"]
    if "tuna" in normalized:
        return ["tuna"]
    if "turkey" in normalized:
        return ["turkey"]
    if "vegetable base" in normalized or "vegetable broth" in normalized or "vegetable stock" in normalized:
        return ["vegetable base"]
    if normalized == "vegetable oil":
        return ["vegetable oil"]
    if "waffle" in normalized:
        return ["waffle"]
    if normalized.startswith("leaves romaine lettuce"):
        return ["romaine lettuce"]
    if normalized.startswith("lemon"):
        return ["lemon"]
    if normalized.startswith("lime") or "lime wedge" in normalized:
        return ["lime"]
    if "oregano" in normalized:
        return ["oregano"]
    if "pea" in normalized and "peanut" not in normalized:
        if "carrot" in normalized:
            return ["pea", "carrot"]
        return ["pea"]
    if "pico de gallo" in normalized:
        return ["pico de gallo"]
    if "pimento" in normalized or "pimiento" in normalized:
        return ["pimento"]
    if normalized.startswith("pineapple"):
        return ["pineapple"]
    if "crushed pineapple" in normalized:
        return ["pineapple"]
    if "crushed tomato" in normalized:
        return ["tomato"]
    if "whole-kernel corn" in normalized:
        return ["corn"]
    if "panko breadcrumb" in normalized:
        return ["breadcrumb"]
    if normalized.startswith("qts "):
        return []
    if "vegetable base" in normalized:
        return ["vegetable base"]
    if "half-and-half" in normalized or "cream half-and-half" in normalized:
        return ["half-and-half"]
    if "pepper black" in normalized or normalized == "pepper black":
        return ["black pepper"]
    if "chips tortilla chip" in normalized or "tortilla chip" in normalized:
        return ["tortilla chip"]
    if "cubs celery" in normalized:
        return ["celery"]
    if "nonstick cooking spray" in normalized:
        return ["nonstick cooking spray"]
    if normalized in {"white", "yellow"}:
        return []
    if normalized in {"black", "bland", "chunk", "juice", "seasoning", "smoke"}:
        return []

    if "broccoli" in normalized and "cauliflower" in normalized:
        return ["broccoli", "cauliflower"]
    if "bread cube" in normalized or "bread cubes" in normalized:
        return ["bread"]
    if "garbanzo" in normalized or "chickpea" in normalized:
        return ["garbanzo bean"]
    if "chicken" in normalized:
        return ["chicken"]

    return [normalized]


def main():
    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    unique_map = {}
    for recipe_ings in data.values():
        for ing in recipe_ings or []:
            normalized_list = normalize_ingredient(ing)
            for normalized in normalized_list:
                if not normalized:
                    continue
                key = normalized.lower()
                if key not in unique_map:
                    unique_map[key] = normalized

    unique_ingredients = sorted(unique_map.values(), key=lambda s: s.lower())

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(unique_ingredients, f, ensure_ascii=False, indent=2)

    print(f"Saved {OUTPUT_FILE} with {len(unique_ingredients)} items")


if __name__ == "__main__":
    main()
