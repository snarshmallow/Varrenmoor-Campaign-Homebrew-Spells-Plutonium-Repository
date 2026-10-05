"""The six haunted skeleton portraits as combat NPCs (dnd5e 5.x). Run:  python foundry-json/painting_npcs.py
Tuned for four level-4 characters (2014 thresholds per party of 4: easy 500, medium 1000, hard 1500, deadly 2000 XP before the
multi-monster multiplier). CR 2 = 450 XP, CR 3 = 700, CR 4 = 1100. Proficiency bonus is +2 at these CRs.
"""
from fvtt import feat, npc, p, save, save_feat, utility, weapon

ICON = "assets/varrenmoor-3d/Act 2 Road to Bridgehollow/Ossuary Exchange/Tokens/portraits"
COMMON = dict(ctype="construct", subtype="painting", ci=("charmed", "exhaustion", "poisoned"), di=("poison",),
              senses={"darkvision": 60}, languages=("common",))


def portrait(n):
    return f"{ICON}/painting_{n}.jpg"


def guide(lines):
    return p("<strong>GM notes.</strong> " + lines)


ACTORS = []

# 1 ---------------------------------------------------------------- Mona Lisa -------------------------------------------
A = "Unsmiling Matron"
ACTORS.append(("monalisa", npc(
    "The Unsmiling Matron (Mona Lisa)", 3, "med", COMMON["ctype"], COMMON["subtype"], 58, 14, (16, 12, 14, 10, 16, 18), {"walk": 30},
    hp_formula="9d8+18", senses=COMMON["senses"], di=COMMON["di"], dr=("psychic",), dv=("acid",), ci=COMMON["ci"], languages=(),
    img=portrait("monalisa"), token_img=portrait("monalisa"), model="token_painting_monalisa.glb", tok_size="med",
    bio=p("<strong>Mona Lisa, as a skeleton.</strong> A walking portrait whose smile cannot be read. She never speaks; she raises one "
          "eyebrow. Creatures that stare too long start wondering whether she is amused, threatened or merely bored, and lose the fight "
          "to that question.") + guide("Play her calm. Open with <em>False Appearance</em> on a wall. Use <strong>The Smile</strong> when "
          "three or more are bunched. <strong>Soft Focus</strong> makes her hard to snipe, so ranged characters should close in. "
          "Vulnerable to acid (paint thinner). 700 XP. Pair with the Blue Boy (450 XP, x1.5 = 1725, a Hard fight)."),
    items=[
        feat(A, "False Appearance", p("While she remains motionless on a wall she is indistinguishable from an ordinary painting."), 100000, "icons/svg/mystery-man.svg"),
        feat(A, "Soft Focus (Sfumato)", p("Her edges blur. Ranged attacks against her from more than 30 feet away have disadvantage."), 200000, "icons/svg/aura.svg"),
        utility(A, "Multiattack", p("The Matron makes two attacks: one <strong>Frame Slam</strong> and one <strong>Skeletal Grab</strong>."), 300000),
        weapon(A, "Frame Slam", p("<em>Melee Weapon Attack:</em> reach 5 ft., one target. <em>Hit:</em> 2d8 + 3 bludgeoning damage."), 400000, "str", 2, 8, "bludgeoning"),
        weapon(A, "Skeletal Grab", p("<em>Melee Weapon Attack:</em> reach 5 ft., one target. <em>Hit:</em> 1d6 + 3 bludgeoning damage and the target is "
                                      "<strong>grappled</strong> (escape DC 13). Until the grapple ends the Matron cannot grab another creature."), 500000, "str", 1, 6, "bludgeoning"),
        save_feat(A, "The Smile (Recharge 5-6)", p("Each creature in a 30-foot cone that can see her must make a <strong>DC 14 Wisdom saving throw</strong>. On a failure it takes "
                                                   "2d8 psychic damage and is <strong>Puzzled</strong>: it spends its next turn deciding whether she is smiling. Until the end of its "
                                                   "next turn it has disadvantage on attack rolls and ability checks and cannot take reactions. On a success it takes half damage."),
                  600000, "wis", 14, dmg=(2, 8, "psychic"), on_save="half", target=("cone", 30), recharge="5"),
        utility(A, "Raised Eyebrow (Reaction)", p("When a creature within 30 feet makes an attack against her and misses, that creature has disadvantage on its next attack roll "
                                                  "before the end of its turn. She is simply unimpressed."), 700000, activation="reaction"),
    ])))

# 2 ---------------------------------------------------------------- Pearl Earring --------------------------------------
A = "Girl with the Pearl"
ACTORS.append(("pearl", npc(
    "The Girl with the Pearl Earring", 3, "med", COMMON["ctype"], COMMON["subtype"], 52, 15, (10, 18, 14, 10, 14, 16), {"walk": 30},
    hp_formula="8d8+16", senses=COMMON["senses"], di=COMMON["di"], dv=("fire",), ci=COMMON["ci"], languages=(),
    skills={"ste": 1}, img=portrait("pearl"), token_img=portrait("pearl"), model="token_painting_pearl.glb", tok_size="med",
    bio=p("<strong>Vermeer's sitter, long since decomposed.</strong> She turns her head over her shoulder at all times, so you only ever see her "
          "in profile, and she hates to be looked at directly.") + guide("A slippery controller. She lives in shadow and in profile. Flaming "
          "attacks hurt (oil on varnish). Her <strong>Pearl Roll</strong> reaction punishes melee-only parties by tipping them prone. 700 XP. "
          "Napoleon + Pearl is 1800 XP x1.5 = 2700, deadly. Use the Blue Boy for a Hard fight instead."),
    items=[
        feat(A, "Chiaroscuro", p("While she is in dim light or darkness she has advantage on Dexterity (Stealth) checks, and attacks against her from more than 10 feet "
                                 "away have disadvantage. She loses this in bright light."), 100000),
        utility(A, "Side Profile (Bonus Action)", p("She turns sideways. Until the start of her next turn she has +2 AC against melee attacks, but she cannot make melee attacks "
                                                    "(she has no other side to present)."), 200000, activation="bonus"),
        utility(A, "Multiattack", p("She makes two <strong>Earring Flick</strong> attacks."), 300000),
        weapon(A, "Earring Flick", p("<em>Ranged Weapon Attack:</em> range 40/120 ft., one target. <em>Hit:</em> 1d8 + 4 bludgeoning damage as a pearl rebounds off the target "
                                     "and back into her ear."), 400000, "dex", 1, 8, "bludgeoning", melee=False, rng=(40, 120)),
        save_feat(A, "Turban Unwind (Recharge 5-6)", p("Yards of blue and yellow cloth lash out in a 20-foot cone. Each creature in the area must succeed on a "
                                                       "<strong>DC 13 Dexterity saving throw</strong> or be <strong>restrained</strong>. A restrained creature can use its action to make a "
                                                       "DC 13 Strength or Dexterity check, freeing itself on a success."),
                  500000, "dex", 13, target=("cone", 20), recharge="5"),
        save_feat(A, "Pearl Roll (Reaction)", p("When a creature hits her with a melee attack, loose pearls scatter around her. The attacker must succeed on a <strong>DC 14 Dexterity "
                                                "saving throw</strong> or fall <strong>prone</strong>."), 600000, "dex", 14, activation="reaction", rng=5),
    ])))

# 3 ---------------------------------------------------------------- Napoleon ------------------------------------------
A = "Napoleon Study"
ACTORS.append(("napoleon", npc(
    "Napoleon in His Study", 4, "lg", COMMON["ctype"], COMMON["subtype"], 78, 16, (16, 12, 14, 14, 12, 16), {"walk": 30},
    hp_formula="12d10+12", senses=COMMON["senses"], di=COMMON["di"], ci=COMMON["ci"], languages=("common",),
    img=portrait("napoleon"), token_img=portrait("napoleon"), model="token_painting_napoleon.glb", tok_size="lg",
    bio=p("<strong>A skeletal general at his writing desk.</strong> He is Large because the frame is large; he has opinions about this. One hand is always "
          "inside his waistcoat. He gives orders to people who are not there.") + guide("The commander. Use <strong>Imperial Dispatch</strong> when he has allies "
          "(other paintings, a Clerk, Lil). <strong>Cannon Salvo</strong> is the big moment. Short jokes make him dive at the joker. 1100 XP alone (a "
          "Medium fight). Napoleon + Blue Boy = 1550 x1.5 = 2325, deadly: great climax."),
    items=[
        feat(A, "Hand in Waistcoat", p("One hand is always tucked away. He cannot be disarmed and has advantage on saving throws against being grappled or having an object "
                                       "knocked from his grasp."), 100000),
        feat(A, "Napoleon Complex", p("Any creature that makes a joke about his height within his hearing becomes his priority target: he has advantage on his next attack roll against "
                                      "that creature, and it has disadvantage on its next saving throw against his abilities."), 200000),
        utility(A, "Multiattack", p("He makes two <strong>Saber</strong> attacks, or one Saber attack and one <strong>Pistol</strong> attack."), 300000),
        weapon(A, "Saber", p("<em>Melee Weapon Attack:</em> reach 5 ft., one target. <em>Hit:</em> 2d6 + 3 slashing damage."), 400000, "str", 2, 6, "slashing", reach=5),
        weapon(A, "Pistol", p("<em>Ranged Weapon Attack:</em> range 30/90 ft., one target. <em>Hit:</em> 1d10 + 1 piercing damage."), 500000, "dex", 1, 10, "piercing",
               melee=False, rng=(30, 90)),
        save_feat(A, "Cannon Salvo (Recharge 5-6)", p("A cannon rolls in from the background of the portrait and fires at a point within 120 feet. Each creature in a 10-foot-radius "
                                                      "sphere must make a <strong>DC 14 Dexterity saving throw</strong>, taking 4d8 thunder damage on a failure (half on a success). "
                                                      "A creature that fails is also <strong>deafened</strong> until the end of its next turn."),
                  600000, "dex", 14, dmg=(4, 8, "thunder"), on_save="half", target=("radius", 10), rng=120, recharge="5"),
        utility(A, "Imperial Dispatch (Bonus Action, Recharge 5-6)", p("He reads out orders. He and each ally of his within 60 feet that can hear him add 1d4 to attack rolls and "
                                                                         "saving throws until the end of his next turn."), 700000, activation="bonus", recharge="5"),
        utility(A, "Strategic Withdrawal (Reaction, 1/Day)", p("When he is reduced to 25 hit points or fewer he retreats: he moves up to 30 feet without provoking opportunity attacks and regains "
                                                                 "10 hit points. He calls it a 'redeployment'."), 800000, activation="reaction", uses=(1, "day")),
    ])))

# 4 ---------------------------------------------------------------- Van Gogh -----------------------------------------
A = "Van Gogh Portrait"
ACTORS.append(("vangogh", npc(
    "Self-Portrait with Bandaged Ear (Van Gogh)", 3, "med", COMMON["ctype"], COMMON["subtype"], 55, 13, (10, 14, 12, 12, 12, 18), {"walk": 30},
    hp_formula="10d8+10", senses=COMMON["senses"], di=COMMON["di"], dr=("slashing",), dv=("fire",), ci=COMMON["ci"], languages=("common",),
    img=portrait("vangogh"), token_img=portrait("vangogh"), model="token_painting_vangogh.glb", tok_size="med",
    bio=p("<strong>A very thick portrait.</strong> The paint stands a finger deep, the sky behind him will not stop swirling, and he is missing an ear on purpose.")
    + guide("An area-control caster. <strong>Starry Night</strong> centred on him punishes clumping; the thrown ear is a joke the party will repeat for weeks. "
            "Thick paint resists slashing, but oil burns (vulnerable to fire). 700 XP; pair with the Blue Boy for a Hard fight (1725)."),
    items=[
        feat(A, "Thick Impasto", p("The paint is built up in ridges. He is resistant to slashing damage, but vulnerable to fire damage."), 100000),
        utility(A, "Multiattack", p("He makes two <strong>Sunflower Seed Barrage</strong> attacks, or uses Starry Night."), 200000),
        weapon(A, "Sunflower Seed Barrage", p("<em>Ranged Weapon Attack:</em> range 30/90 ft., one target. <em>Hit:</em> 1d6 + 2 piercing damage."), 300000, "dex", 1, 6, "piercing",
               melee=False, rng=(30, 90)),
        save_feat(A, "Starry Night (Recharge 5-6)", p("A spiral of blue and yellow brushstrokes erupts in a 20-foot radius centred on him. Each creature in the area must make a "
                                                      "<strong>DC 14 Dexterity saving throw</strong>. On a failure it takes 3d6 psychic damage, is pushed 10 feet in a clockwise spiral and "
                                                      "has disadvantage on its next attack roll. On a success it takes half damage."),
                  400000, "dex", 14, dmg=(3, 6, "psychic"), on_save="half", target=("radius", 20), recharge="5"),
        save_feat(A, "Detachable Ear (Bonus Action, 3/Day)", p("He throws his ear at a creature within 30 feet. The target must succeed on a <strong>DC 14 Constitution saving throw</strong> "
                                                               "or be <strong>deafened</strong> until the end of its next turn. The ear returns to him. 'Hear that?'"),
                  500000, "con", 14, activation="bonus", rng=30, uses=(3, "day")),
    ])))

# 5 ---------------------------------------------------------------- Henry VIII ---------------------------------------
A = "Henry VIII Portrait"
ACTORS.append(("henry", npc(
    "Henry VIII, Defender of the Faith", 4, "lg", COMMON["ctype"], COMMON["subtype"], 95, 15, (18, 10, 18, 12, 14, 18), {"walk": 30},
    hp_formula="10d10+40", senses=COMMON["senses"], di=COMMON["di"], ci=("charmed", "exhaustion", "frightened", "poisoned"), languages=("common",),
    img=portrait("henry"), token_img=portrait("henry"), model="token_painting_henry.glb", tok_size="lg",
    bio=p("<strong>Holbein's king, long past his appetite.</strong> He has a turkey leg up one sleeve and an opinion about everyone's marital status.")
    + guide("The boss painting. He soaks damage, heals with the turkey leg, and ends fights with <strong>Off With Their Heads</strong>. "
            "Annulment lets him dodge one bad save, so save your control for later rounds. 1100 XP alone (Medium). Henry + any CR 2 painting = a Deadly finale."),
    items=[
        feat(A, "Divine Right", p("He is immune to being charmed or frightened; the Pope has no jurisdiction."), 100000),
        utility(A, "Annulment (Reaction, 1/Day)", p("When he fails a saving throw he can choose to succeed instead. The party must file the correct form to contest it."), 200000,
                activation="reaction", uses=(1, "day")),
        utility(A, "Multiattack", p("He makes two <strong>Royal Mace</strong> attacks."), 300000),
        weapon(A, "Royal Mace", p("<em>Melee Weapon Attack:</em> reach 5 ft., one target. <em>Hit:</em> 2d8 + 4 bludgeoning damage."), 400000, "str", 2, 8, "bludgeoning", reach=5),
        save_feat(A, "Off With Their Heads (Recharge 5-6)", p("He points at one creature he can see within 30 feet. The target must make a <strong>DC 14 Wisdom saving throw</strong>, taking 4d8 "
                                                              "necrotic damage and becoming <strong>frightened</strong> of him until the end of its next turn on a failure, or half damage and no "
                                                              "other effect on a success."), 500000, "wis", 14, dmg=(4, 8, "necrotic"), on_save="half", rng=30, recharge="5"),
        utility(A, "Turkey Leg (Bonus Action, 2/Day)", p("He pulls a turkey leg from his sleeve and gnaws it. He regains 2d8 + 4 hit points."), 600000, activation="bonus", uses=(2, "day")),
    ])))

# 6 ---------------------------------------------------------------- Blue Boy ----------------------------------------
A = "Blue Boy Portrait"
ACTORS.append(("blueboy", npc(
    "The Blue Boy (Gainsborough)", 2, "med", COMMON["ctype"], COMMON["subtype"], 40, 15, (10, 18, 10, 12, 12, 16), {"walk": 40},
    hp_formula="9d8", senses=COMMON["senses"], di=COMMON["di"], ci=COMMON["ci"], languages=("common",),
    img=portrait("blueboy"), token_img=portrait("blueboy"), model="token_painting_blueboy.glb", tok_size="med",
    bio=p("<strong>A skeleton in blue satin who will not stop posing.</strong> He is fast, vain and very hard to pin down.")
    + guide("A skirmisher. His satin lets him slip past everyone; he wants to be looked at. <strong>Strike a Pose</strong> forces enemies to deal with him instead of the "
            "controllers. 450 XP; the standard add for any CR 3 painting (Hard fight at x1.5)."),
    items=[
        feat(A, "Satin Slide", p("His movement does not provoke opportunity attacks."), 100000),
        utility(A, "Windblown Plume (Bonus Action)", p("He takes the Dash or Disengage action as a bonus action; the plume trails dramatically."), 200000, activation="bonus"),
        utility(A, "Multiattack", p("He makes two <strong>Rapier</strong> attacks."), 300000),
        weapon(A, "Rapier", p("<em>Melee Weapon Attack:</em> reach 5 ft., one target. <em>Hit:</em> 1d8 + 4 piercing damage."), 400000, "dex", 1, 8, "piercing", reach=5, props=["fin"]),
        save_feat(A, "Strike a Pose (Action)", p("He takes the Dodge action and strikes a magnificent pose. Each enemy within 30 feet that can see him must succeed on a <strong>DC 13 Wisdom "
                                                  "saving throw</strong> or, on its next attack, target him if it is able to."), 500000, "wis", 13, target=("radius", 30)),
        save_feat(A, "Posh Disdain (Reaction)", p("When an attack misses him, the attacker must succeed on a <strong>DC 13 Wisdom saving throw</strong> or be too embarrassed to make "
                                                  "opportunity attacks until the start of its next turn."), 600000, "wis", 13, activation="reaction", rng=30),
    ])))


if __name__ == "__main__":
    for key, a in ACTORS:
        save(a, "actors", f"Painting_{key}_FoundryVTT.json")
        print("wrote", key, "items:", [i["name"] for i in a["items"]])
