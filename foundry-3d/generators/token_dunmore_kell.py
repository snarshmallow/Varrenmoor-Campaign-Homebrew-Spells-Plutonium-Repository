"""Token: Dunmore Kell, tired night porter."""
from _tokens import humanoid

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange/Tokens"
KEEP_XY = True      # origin = middle of the feet, authored not guessed


def build(k):
    humanoid(k, height=1.72, coat="brown", trousers="grey", hat="cap", apron="cream", held="lamp")
