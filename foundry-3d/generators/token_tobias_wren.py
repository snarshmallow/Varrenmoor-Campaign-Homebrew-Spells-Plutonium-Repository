"""Token: Tobias Wren, gentle old former gravewright."""
from _tokens import humanoid

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange/Tokens"
KEEP_XY = True      # origin = middle of the feet, authored not guessed


def build(k):
    humanoid(k, height=1.78, coat="black", trousers="grey", hair="white", stoop=0.08, long_coat=True, held="shovel")
