"""Token: the henry painting as a walking creature (see _tokens.painting_creature)."""
from _tokens import painting_creature

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange/Tokens"
KEEP_XY = True      # origin = middle of the feet, authored not guessed


def build(k):
    painting_creature(k, "henry", 1.25, 1.83, "crown")
