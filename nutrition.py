import re


def items(raw):
    for item in re.split(r"[;,\n]+", raw):
        if not item.strip():
            continue
        m = re.match(r"^(.+?)\s+(\d+(?:[.,]\d+)?)\s*(?:г|гр|g)?$", item.strip(), re.I)
        if not m:
            raise ValueError(f"Не понял запись: {item}")
        yield m.group(1), float(m.group(2).replace(",", "."))


def fmt(x): return f"{x:.0f}"
