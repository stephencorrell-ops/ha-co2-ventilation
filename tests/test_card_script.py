"""The card is loaded as a plain script next to every other custom card, in one shared namespace."""
from pathlib import Path

CARD = Path(__file__).parents[1] / "custom_components" / "co2_ventilation" / "www" / "co2-ventilation-card.js"


def test_card_keeps_its_names_private():
    lines = [l for l in CARD.read_text().splitlines() if l and not l.startswith(("/*", " *", "//"))]
    assert lines[0] == "(() => {", "wrap the card in a function so its names can't clash with another card's"
    top = [l for l in lines[1:] if l.startswith(("const ", "let ", "var ", "class ", "function "))]
    assert top, "expected the card's own declarations inside the wrapper"
