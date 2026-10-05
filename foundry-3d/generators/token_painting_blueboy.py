"""Token: the blueboy painting as a walking creature (see _tokens.painting_creature)."""
from _tokens import painting_creature

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange/Tokens"
KEEP_XY = True      # origin = middle of the feet, authored not guessed


def build(k):
    painting_creature(k, "blueboy", 0.75, 1.10, "plume")
