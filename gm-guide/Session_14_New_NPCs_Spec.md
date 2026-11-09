# SESSION 14: NEW OSSUARY NPCs (BUILD SPEC)
*Companion to `Session_14_Cladis_Return_Conspiracy.md` (Part 7). Six new NPCs: four members of the Thaw (Quill, already built, is its driving cause), one pressure NPC, one ally. All are NEW. Venfyura (the woman at the camp's fire, SETTLED) is an existing NPC and is not rebuilt here; see the end of this file. Foundry fields are in `Session_14_Foundry_Build_Checklist.md`.*

**Schema these follow.** The native Ossuary JSONs (Quill, Brokka, Pimm, Mottle on the Vega share) are dnd5e `npc` actors whose non-combat content lives in **feat items with no activities**, named by kind:
- `GM Reference: <Name>, Voice and <Place>` (appearance, voice, sample dialogue)
- `Lore Reference: <topic>` (what they know, with tags)
- `Side Quest: <title>` (hook, objectives, reward)
- `Training Reference: <topic>` (only if they teach; never extra charges)
- `Merchant Reference: <Name>'s Stock` (stock list and refusals)
- `GM Reference: Lil' Apostrophe at <Place>` (Lil's bit, optional)

Then a small number of real traits/actions (feat, utility, weapon). Biography holds a short summary plus GM notes. Native names use an em dash in feature names ("Quill Scratch — Voice & Shop"); this spec uses a comma so the Google Doc headings stay clean. Either is fine for Foundry.

**Stat conventions.** 2024 rules, proficiency bonus +2 for CR 0 to 4. Mostly non-combatants. The Exchange's wards suppress deliberate violence inside the thresholds, so fights here are rare and short.

---

## 1. SABELINE NOCK, Night Custody Clerk (runs the Thaw day to day)
*"Three records must agree. One of mine never has."*

**Species / body.** Sentient skeleton, contracted Exchange staff (a person under contract, not property). Small and upright; reading spectacles wired to her skull; a clerk's sleeve-garters on bare arm bones. Very neat.
**Role in the Exchange.** Keeps the night copy of the custody ledger: reconciles the day's entries, copies forward open claims when a volume fills.
**Secret role.** Runs the Thaw day to day; Quill is its cause. She found Cladis's open claim while copying it forward for the fourth time and brought it to Quill, who recognized it as one mark of Cladis's trail. Keeps the custody page and the meeting times.
**Motivation.** Duty first: a claim that never closes offends her. Second, plain politics: Nior wanted authority over every settlement and road, and the Niorghast means to resurrect him; that would not leave a neutral house neutral, and her contract only exists because the Exchange is neutral.
**Relationship to Quill.** Old colleagues. She brought Quill the custody line because it reads like an unfinished instruction. They argue about commas.
**Knows.** The open claim, the method, every member, the cold door's timetable, Tallis's interest. **Doesn't know.** Who banished Cladis, what happened in Nior's fortress, who cut the sentence, whether it will work. She knows of the Goddess's name but has never heard it said.
**Where.** Night custody office (new scene) from the tenth hour; Table Seven at Mottle's after the evening rush.
**Voice and mannerisms.** Quiet, exact, faintly amused. Taps four slow with her pen when thinking (the Bell knock). Calls Cladis "the claimant" in public. Never raises her voice; she lowers it.

**Sample dialogue**
- [COMMON] "Night desk. If it isn't in the ledger, it hasn't happened yet."
- [COMMON] "I don't sell anything. I write down who did."
- [ASK] "There is an open claim in my ledger. It's been open for three hundred years. I'd like to close it properly."
- [ASK] *(showing the page)* "Named. Held. Tag outstanding. Two out of three. Pringus would call it a rumor. I call it a job."
- [EARN] "She isn't dead. She was put outside, and she tied herself off out there. A thread tied in the wrong place can be tied again. That's all we're doing. Knots."
- [EARN] "Why now? Because you walked a piece of the place she's in through my intake hall. And because of the news from Bridgehollow."
- [EARN] "No, I don't know what happened in the fortress. Nobody does. I am not going to guess at you."
- *(to Tallis)* "Inspector. You're early. Sit. The kettle's honest."
- *(to Lil)* "Please don't write on my ledger." *(Lil: "I wasn't gonna. ...What's it say if I did?")*

**Quest hook.** *The Outstanding Tag*: find the physical tag for the open claim and get the three records to agree (Part 7, T5).

**Stat block (CR 1/4, 50 XP)**
- Medium undead (sentient skeleton), lawful neutral. **AC** 12 (clerk's coat). **HP** 13 (3d8). **Speed** 30 ft.
- **STR** 8 (−1) **DEX** 12 (+1) **CON** 10 (+0) **INT** 16 (+3) **WIS** 14 (+2) **CHA** 11 (+0)
- **Saves** Int +5, Wis +4. **Skills** History +5, Insight +4, Investigation +5.
- **Damage vulnerabilities** bludgeoning. **Damage immunities** poison. **Condition immunities** exhaustion, poisoned.
- **Senses** darkvision 60 ft, passive Perception 12. **Languages** Common, plus any two (old Eirwyn script reading only). **PB** +2.
- **Trait: Copied Forward.** She has advantage on checks to recall or find any entry in the custody ledger she has copied.
- **Trait: Contracted Staff.** She cannot be bought, sold or claimed. Exchange wards treat harm to her as an offense against the house.
- **Tool feature: Ledger Hand (calligrapher's supplies, proficient).** In 10 minutes she can make an exact, certified copy of any Exchange page she has access to.
- **Action: Pen Jab.** *Melee:* +3 to hit, reach 5 ft. *Hit:* 1 piercing. (She will not.)
- **Action: Call the Desk (1/day).** She rings the night desk bell; two Exchange custodians arrive in 1d4 rounds. Only inside the thresholds.

**Inventory / stock.** Night custody ledger volume (copy), the copied open-claim page, steel-nib pens, a brass knock-block, spectacles, a tin of tea, a key to the night office (not to the vaults).

**Token / appearance (AI art prompt).** Small neat skeleton clerk in a dark green clerk's coat with sleeve-garters, wire spectacles hooked over the skull's nasal cavity, holding a steel pen and a thick ledger. Warm lamp light, calm posture. Stylized fantasy, painterly.

**NPC Features (feat items, no activities)**
- `GM Reference: Sabeline Nock, Voice and Night Desk`: snapshot, voice, the dialogue above.
- `Lore Reference: The Open Claim`: the custody line, why two out of three is a "rumor", what she knows and does not.
- `Side Quest: The Outstanding Tag`: hook, objectives (find the tag, present it, Pringus audits), warning that the audit is public.
- `GM Reference: Lil' Apostrophe at the Night Desk`: Lil asks if the ledger is "a book that's awake at night"; Sabeline: "Yes." Lil: "Same."

---

## 2. YSOLDE HARROWGATE, Licensed Restorer (the vessel)
*"Nobody was ever in it. I checked three times. That's the law, and it's also manners."*

**Species / body.** A woman in her third leased body (a sturdy, middle-aged human body; the lease is up in spring and she pays rent on it monthly). She is fond of it and complains about the knees.
**Role in the Exchange.** Runs **Harrowgate Restorations**, an independent licensed restoration house in the Lower market. Restoration under contract, no guarantees (canon).
**Secret role.** Prepares the vessel: a lawful construct frame with no identity, grown with tissue from a seed of life, kept in her back room. Keeps Violet's mycelium culture in a glass case.
**Motivation.** She restores people for a living, and she thinks one person is owed a body more than most. Also, privately, she would like to restore someone who will remember it was done well.
**Relationship to Quill.** Customer and friend; Quill writes her boundary runes.
**Knows.** The vessel, the restoration materials, what cold does to tissue, that it is Cladis. **Doesn't know.** The cold door's timetable, the courier, the Bridgehollow news beyond rumor.
**Where.** Harrowgate Restorations (new scene). **[SUGGESTED]** It is the house named on Tobias Wren's referral card (Part 6, Quest 3).
**Voice and mannerisms.** Brisk, warm, practical, a nurse's humor. Rubs her borrowed knees. Says "properly" a lot. Washes her hands before and after every sentence that matters.

**Sample dialogue**
- [COMMON] "Restoration's a contract, not a miracle. Sit down, you look like a claim form."
- [COMMON] "No, I can't do it today. Nobody does it today. Today is for paperwork."
- [ASK] "This body? Leased. Third one. Lovely, apart from the knees. Lease is up in spring."
- [ASK] *(the vessel)* "Construct material without identity. Bought, receipted, three records. Nobody was ever in it."
- [ASK] *(to Betsy)* "It'll arrive cold from the inside. Pick me a body that warms from the middle, not one that just survives by stopping. She's done enough stopping."
- [EARN] "Yes, I know whose it's for. No, I won't say it out here."
- [EARN] *(Bones)* "Bring me the name, the skull if you can get it, and the toe if you can't. After this is done, I'll take him at cost. No promises. There never are."
- *(to Lil)* "Hands where I can see them, love." *(Lil: "They're always where you can see them. That's the problem with hands.")*

**Quest hook.** *A Body That Warms From the Middle* (Part 7, T3 and T4).

**Stat block (CR 1/2, 100 XP)**
- Medium humanoid (human, leased body), neutral good. **AC** 11. **HP** 22 (4d8 + 4). **Speed** 30 ft.
- **STR** 11 (+0) **DEX** 12 (+1) **CON** 12 (+1) **INT** 15 (+2) **WIS** 15 (+2) **CHA** 12 (+1)
- **Saves** Wis +4. **Skills** Medicine +6 (expertise), Nature +4, Insight +4.
- **Senses** passive Perception 12. **Languages** Common, plus one. **PB** +2.
- **Trait: Leased Body.** If reduced to 0 HP she drops unconscious as normal; if killed, her lease contract lets the Exchange recover her name (she would be furious).
- **Trait: Licensed Restorer.** She knows the restoration materials list and can tell at a glance whether a vessel or a set of remains is Stable, Strained or unusable.
- **Tool feature: Restorer's Kit (herbalism kit and healer's kit, proficient).** As an action, she stabilizes a creature and restores 1d4 + 2 HP (3/day).
- **Action: Scalpel.** *Melee:* +3 to hit, reach 5 ft. *Hit:* 1d4 + 1 slashing.
- **Reaction: Steady Hands.** When a creature within 5 ft fails a Medicine or Splicing check on a body she is supervising, she can let it reroll once (1/day).

**Inventory / stock (Merchant Reference).** Clean burial linen (5 sp per yard), distilled water (2 sp per flask), joining needles and bone-thread (1 gp), identity tag blanks (1 sp), preserving salts (5 sp), restoration consultations (5 gp, written), restoration contracts (by quote, no guarantees). She does not sell bodies over the counter and does not sell anything that "was ever someone".

**Token / appearance.** Sturdy middle-aged woman in a long linen apron over a plain grey dress, sleeves rolled, a lease tag on a cord at her wrist, reading glasses pushed up into greying hair, holding a roll of white linen. Clinical lamp light, kind tired face.

**NPC Features**
- `GM Reference: Ysolde Harrowgate, Voice and Restoration House`
- `Lore Reference: The Vessel` (lawful category, materials, why cold-from-inside matters)
- `Training Reference: Choosing a Continuation` (supports Betsy's T4 choice; Pimm's rule; no extra charges or actions)
- `Side Quest: A Body That Warms From the Middle`
- `Merchant Reference: Harrowgate's Counter`
- `Lore Reference: Bones's Restoration` (at cost after the operation, no guarantee; claim and restoration stay separate)

---

## 3. HADDO ROOK, Trolley Ropewright (the line)
*"Rope goes where it's tied. I tie it. That's the end of my curiosity."*

**Species / body.** A big man whose two arms came from two different lawful donors: the left is older, darker and scarred; the right is younger and freckled. Both are excellent at rope. He talks to them separately when they disagree.
**Role in the Exchange.** Ropewright and line-splicer for the overhead bone trolleys and carriers in the Lower market.
**Secret role.** Braids the line. Supplies iron stock (including the Hunger-tainted bars by mistake, see T2).
**Motivation.** Money and craft pride. He is in it as a paid specialist and deliberately knows only his part.
**Relationship to Quill.** Business. Quill once corrected the spelling on his shop sign and Haddo has never forgiven the comma.
**Knows.** How to braid strands of different stiffness so they share load; that the line is for "a long drop in the cold". **Doesn't know.** Who or what it is for, the cold door, Cladis. If told, he is impressed and wants a raise.
**Where.** The Ropewalk and Signal Loft (new scene), under the trolley rails.
**Voice and mannerisms.** Slow, big, cheerful, very literal. Measures everything in arm-lengths (and specifies which arm).

**Sample dialogue**
- [COMMON] "Mind the rail. It doesn't mind you."
- [COMMON] "Left arm's forty years older than the right. Left arm does the knots."
- [ASK] "Three strands that fail different ways. That's all good rope is. Each one covers for the other two."
- [ASK] "Linen holds shape, carries nothing. Wire carries, but cold snaps it. The fuzzy one's alive, so it rots. Braid them right and none of that matters."
- [ASK] *(the bars)* "Bought those off a salvage cart. Old fittings. Iron's iron, isn't it?" *(It isn't. See T2.)*
- [EARN] "I don't ask where rope goes. ...Where's it going?"
- *(to Lil)* "Don't write on the rope." *(Lil: "I was gonna write ROPE. So it knows." Haddo: "It knows.")*

**Quest hook.** The braid (Part 7, T6). Optional side job: a trolley cable is fraying above the market; he pays 10 gp for a hand.

**Stat block (CR 1/2, 100 XP)**
- Medium humanoid (human, spliced arms), neutral. **AC** 12 (leather apron). **HP** 32 (5d8 + 10). **Speed** 30 ft, climb 20 ft.
- **STR** 16 (+3) **DEX** 13 (+1) **CON** 14 (+2) **INT** 10 (+0) **WIS** 11 (+0) **CHA** 10 (+0)
- **Skills** Athletics +5, Sleight of Hand +3. **Senses** passive Perception 10. **Languages** Common. **PB** +2.
- **Trait: Two Arms, Two Opinions.** Advantage on Athletics checks to climb rope or hold a load.
- **Tool feature: Ropewright (weaver's tools, proficient).** In 1 hour he braids up to 60 ft of three-strand line; a creature helping him holds tension (see T6).
- **Action: Multiattack.** Two Rope Hook attacks.
- **Action: Rope Hook.** *Melee:* +5 to hit, reach 5 ft. *Hit:* 1d6 + 3 bludgeoning.
- **Action: Lasso.** *Ranged:* +3 to hit, range 15 ft. *Hit:* the target is restrained (escape DC 13).

**Inventory / stock.** Hemp rope (50 ft, 1 gp), silk cord (50 ft, 10 gp), trolley cable offcuts, iron bar stock (5 sp each; two are Hunger-tainted), splicing fids, pulleys (1 gp), harness (2 gp).

**Token / appearance.** Huge friendly man in a rope-scarred leather apron, mismatched arms (left arm older, darker and scarred, right arm younger and freckled), coils of rope over one shoulder, a big wooden fid behind his ear. Workshop light, overhead rails.

**NPC Features**
- `GM Reference: Haddo Rook, Voice and Ropewalk`
- `Lore Reference: Three Strands` (the braid's plain engineering)
- `Side Quest: The Fraying Cable` (optional, 10 gp, Athletics DC 12 aloft)
- `Merchant Reference: Haddo's Stock`

---

## 4. PELL OSTRY, Keeper of the Dusty Terminal (the door and the courier post)
*"Usual time. Single clunk. Never early."*

**Species / body.** A sentient skeleton missing both legs below the knee, who rides a counterweighted chair along a short rail in the terminal room. Very fast on the rail, very slow on the floor.
**Role in the Exchange.** Nominal keeper of a pneumatic terminal the Exchange lists as being on no active route. Nobody remembers giving him the job; nobody has taken it away.
**Secret role.** Keeps the cold door's timetable. Receives and sends the Thaw's capsules at the usual time. Lets the courier (Europa's brother **[SUGGESTED]**) through.
**Motivation.** Old loyalty to the woman at the fire on the other side of the door. **SETTLED:** she is Venfyura. Pell calls her "V." in writing and never names her aloud; he won't confirm who she is this session.
**Relationship to Quill.** Quill keeps his door's anchor running. He calls Quill "the grammarian" and means it fondly.
**Knows.** The schedule, the capsules, the Bridgehollow news, who carried Europa in, that the gorge frost never melts (he has a jar). **Doesn't know.** The vessel, the records, the method beyond "line and bell".
**Where.** The Dusty Terminal and the Cold Door (new scene). Sometimes at Table Seven.
**Voice and mannerisms.** Short sentences, railway-clerk precise, dry. Checks a pocket watch with no hands (he says he knows the time; the watch is for company).
**Note lead (Part 6).** Pell is who sends "Drop off at the usual time." The notes are the Thaw's capsules. If you want that lead kept separate, have him use knocks instead.

**Sample dialogue**
- [COMMON] "No route. No logging. No visitors. You're visiting."
- [ASK] "Usual time is when the last trolley passes. One minute. Not two."
- [ASK] *(the frost jar)* "From the gorge. Doesn't melt. Not all the way. That's how you know the edge is close."
- [EARN] "Capsules come through with news. Lately it's bailiffs, black wagons, and a quiet Reave."
- [EARN, Europa only] "The man who carried you in came through my door. Said you'd be angry. Said to tell you the time is right, and he's at the fire."
- [EARN] "Someone's been counting my minutes. Tall fellow. Measuring chain."
- *(to Lil)* "Don't touch the lever." *(Lil: "What lever?" Pell: "Exactly.")*

**Quest hook.** *The Usual Time*: be at the cold door at the usual time for the test pull (Part 7, Scene 7).

**Stat block (CR 1/8, 25 XP)**
- Medium undead (sentient skeleton), neutral. **AC** 11. **HP** 9 (2d8). **Speed** 10 ft (floor), 40 ft along his rail.
- **STR** 8 (−1) **DEX** 13 (+1) **CON** 10 (+0) **INT** 12 (+1) **WIS** 14 (+2) **CHA** 9 (−1)
- **Skills** Perception +4, Stealth +3. **Damage vulnerabilities** bludgeoning. **Damage immunities** poison. **Condition immunities** exhaustion, poisoned.
- **Senses** darkvision 60 ft, passive Perception 14. **Languages** Common. **PB** +2.
- **Trait: Knows the Time.** He always knows the exact hour and when the next trolley passes.
- **Trait: Contracted Staff.** As Sabeline.
- **Tool feature: Tube Keeper (tinker's tools, proficient).** He can send or receive a capsule through any working terminal and knows which terminals are listed and which are not.
- **Action: Lever Swing.** *Melee:* +3 to hit, reach 5 ft. *Hit:* 1d4 + 1 bludgeoning.

**Inventory.** The jar of gorge frost (yields 1 Rime dose, then empty), a pocket watch with no hands, capsule shells, bone-style tags, old letters from the far side (EARN to read).

**Token / appearance.** Wiry skeleton in a stained brass-buttoned porter's coat, legs ending below the knees, seated in a counterweighted iron chair on a short rail, holding a handless pocket watch. Dusty brass pipes, cold blue draft from a door behind him.

**NPC Features**
- `GM Reference: Pell Ostry, Voice and Terminal`
- `Lore Reference: The Cold Door` (one minute at the usual time; recorded as sealed; where it opens)
- `Lore Reference: News From Bridgehollow` (capsule contents, EARN)
- `Side Quest: The Usual Time`

---

## 5. INSPECTOR CORVIN TALLIS, Inspector of Thresholds (pressure, not a villain)
*"Is the door sealed? The ledger says it is. My book says it opens. One of these is wrong."*

**Species / body.** One of the few breathing staff: a tall, thin, living human in his fifties, grey uniform coat, a brass measuring chain looped at his belt. Writes in a small black book of door openings.
**Role in the Exchange.** Inspects thresholds: that every door does what the ledger says it does. Posts notices of irregularity on the public boards.
**Secret role.** None. He suspects irregular traffic at a door recorded as sealed. He has counted forty-one openings.
**Motivation.** The Exchange is neutral because its doors are honest. A door that lies is how neutrality ends. (He and Sabeline want the same thing, for opposite reasons.)
**Relationship to Quill.** Has hired Quill twice to repair doors. Respects the work. Has started to wonder why Quill's repairs are so good on doors that are "sealed".
**Knows.** The door opens at the same hour; someone keeps its rune working; a bell rang where none should. **Doesn't know.** Cladis, the claim, the method, the Thaw.
**Where.** Rides the tenth-hour trolley; appears in Scene 5 (night custody office) and possibly at the cold door in Scene 7.
**Voice and mannerisms.** Polite, precise, slightly too close. Asks questions that each have exactly one answer. Measures doorways with his chain while talking.

**Sample dialogue**
- [COMMON] "Good evening. Which door did you come in by? There is only one correct answer."
- [COMMON] "I don't arrest anyone. I close doors. It's usually enough."
- [ASK] "A sealed door that opens is a lie with hinges."
- [ASK] "Forty-one openings. One minute each. Same hour. That is not a draft."
- [EARN] *(after the audit, talked to a delay)* "One more minute, then it's closed, and it's in my book that I waited."
- [EARN] *(lawful permit)* "If the three records agree, then what passes is a lawful transfer, and it's my job to let it. I hate that you've made this my job."
- *(lied to)* "Thank you. I'll be posting at noon regardless."
- *(to Lil)* "And which door did you come in by?" *(Lil: "The front one. It was the front when I came in.")*

**Quest hook.** *Forty-One Minutes*: delay him, persuade him, or outrun him (Part 7, Scene 5).

**Stat block (CR 1, 200 XP)**
- Medium humanoid (human), lawful neutral. **AC** 13 (uniform coat, Dex). **HP** 27 (5d8 + 5). **Speed** 30 ft.
- **STR** 10 (+0) **DEX** 14 (+2) **CON** 12 (+1) **INT** 14 (+2) **WIS** 16 (+3) **CHA** 12 (+1)
- **Saves** Wis +5, Int +4. **Skills** Insight +7 (expertise), Investigation +4, Perception +5.
- **Senses** passive Perception 15. **Languages** Common, plus two. **PB** +2.
- **Trait: Reads Doors.** He has advantage on checks to tell whether a door, hatch or threshold has been opened recently.
- **Trait: Hard to Lie To.** Deception against him is at DC 16 (wards don't stop lies; he does).
- **Tool feature: Measuring Chain (cartographer's tools, proficient).** He can measure and record any doorway; his notes count as a record for a Reconciliation Audit.
- **Action: Notice of Irregularity (charter procedure, 1/day).** He posts a notice; after the stated time, the named threshold is sealed by Exchange order and any account linked to it is suspended pending review. Not a spell.
- **Action: Measuring Chain.** *Melee:* +4 to hit, reach 10 ft. *Hit:* 1d4 + 2 bludgeoning, and the target's speed drops by 10 ft until his next turn. (Last resort; the wards inside will usually stop it anyway.)

**Inventory.** Black book of door openings, brass measuring chain, a pad of notice forms, Exchange seal, a thermos of very weak tea.

**Token / appearance.** Tall thin man in his fifties in a long grey uniform coat with brass buttons, brass measuring chain looped at his belt, small black notebook in hand, neat grey moustache, alert eyes. Cool corridor light.

**NPC Features**
- `GM Reference: Corvin Tallis, Voice and Rounds` (his schedule: the tenth-hour trolley)
- `Lore Reference: What Tallis Knows` (forty-one openings; not the claim)
- `Side Quest: Forty-One Minutes` (delay DC 15, permit DC 17 with the audit, lie DC 16, Nan's help)
- `GM Reference: If Tallis Posts` (consequences, Part 7.6)

---

## 6. NAN GRISTLE, Trolley Signalwoman (ally, not in on it)
*"Four slow means stop and wait. Everybody knows that. Well. Everybody up here."*

**Species / body.** A broad old half-orc woman with a brass speaking-trumpet on a strap, signal flags in her apron, and a bell on a post beside her chair in the signal loft. Fully her own body, and proud of it.
**Role in the Exchange.** Signals the overhead bone trolleys through the Lower market interchange from a loft above the rails.
**Secret role.** None. She doesn't know about the Thaw. She helps because she likes the party, enjoys Lil (the ducks rode her trolleys for an afternoon and she thought it was the best day in years), and dislikes Tallis's habit of riding her tenth-hour trolley and timing it.
**Motivation.** Her trolleys on time, her loft respected, a bit of gossip.
**Relationship to Quill.** Barely knows Quill. "The skinny one with the chalk."
**Knows.** Every trolley time, every regular rider, Tallis's rounds, which corridors carry sound. **Doesn't know.** Anything about the Thaw, Cladis or the cold door (she thinks the dusty terminal is "Pell's hobby").
**Where.** The Ropewalk and Signal Loft (new scene), above Haddo's workshop.
**Voice and mannerisms.** Loud, cheerful, nosy, talks through the trumpet even when you're next to her. Taps the bell rope when nervous.

**Sample dialogue**
- [COMMON] *(through the trumpet)* "MIND THE BASKETS. Oh, you're right there. Mind the baskets."
- [COMMON] "Four slow on my bell means stop and wait. Two fast means go. Easy."
- [ASK] "Inspector Tallis rides the tenth-hour trolley every night now. Times it with his watch. Rude."
- [ASK] "Want to borrow the bell? Bring it back with its tongue in. People keep stealing tongues lately."
- [ASK] "I can hold the tenth-hour a few minutes. Signal fault. Happens all the time. Happens when I say it happens."
- [EARN] "I don't want to know what you're doing. I want to know if it's going to be funny."
- *(to Lil)* "THE DUCK BOY." *(Lil: "Hi! Was I supposed to be here?" Nan: "You're always supposed to be here.")*

**Quest hook.** Lends the signal bell for the test (T6). Can delay Tallis (Scene 5).

**Stat block (CR 0, 10 XP)**
- Medium humanoid (half-orc), chaotic good. **AC** 10. **HP** 11 (2d8 + 2). **Speed** 25 ft.
- **STR** 13 (+1) **DEX** 9 (−1) **CON** 12 (+1) **INT** 10 (+0) **WIS** 13 (+1) **CHA** 12 (+1)
- **Skills** Perception +3, Persuasion +3. **Senses** darkvision 60 ft, passive Perception 13. **Languages** Common, Orc. **PB** +2.
- **Trait: Signalwoman.** She knows where every trolley in the Lower market is, and when.
- **Tool feature: Signal Bell and Trumpet.** Her voice through the trumpet carries 300 ft; she can halt or delay a trolley for up to 10 minutes once a night.
- **Action: Signal Flag Swat.** *Melee:* +3 to hit, reach 5 ft. *Hit:* 1 bludgeoning, and she is very loud about it.

**Inventory.** Brass speaking-trumpet, signal flags, the signal bell (lendable), a tin of mint humbugs, a trolley timetable (handwritten, accurate).

**Token / appearance.** Broad grey-haired old half-orc woman in a patched signaller's coat, brass speaking-trumpet on a strap, signal flags tucked in her apron, sitting beside a bell on a post, grinning with one tusk chipped. Warm light, overhead rails.

**NPC Features**
- `GM Reference: Nan Gristle, Voice and Signal Loft`
- `Lore Reference: Trolley Times and Tallis's Rounds`
- `GM Reference: Lil' Apostrophe at the Signal Loft` (the duck afternoon)

---

## ROSTER AT A GLANCE
| NPC | One line | CR | Thaw? |
|---|---|---|---|
| Sabeline Nock | Skeletal night custody clerk who found Cladis's open claim and runs the Thaw day to day | 1/4 | Organizer |
| Ysolde Harrowgate | Licensed restorer in a leased body; prepares the lawful vessel | 1/2 | Member |
| Haddo Rook | Ropewright with two donors' arms; braids the line, knows nothing else | 1/2 | Paid specialist |
| Pell Ostry | Legless skeleton keeper of the dusty terminal; the cold door's timetable and courier post | 1/8 | Member |
| Corvin Tallis | Living Inspector of Thresholds; has counted forty-one openings of a sealed door | 1 | No (pressure) |
| Nan Gristle | Loud, kind trolley signalwoman; lends the bell and can delay Tallis | 0 | No (ally) |
| *(Quill Scratch)* | *Existing; the Thaw's cause: wants Cladis back to enlist the Rhime Goddess; keeps the cold door's anchor rune* | *1/2* | *Driving member* |
| *(Venfyura)* | *Existing; the woman at the camp's fire, Violet's grandmother; the far end's partner (off stage)* | *existing* | *Partner* |

---

## QUILL AND VENFYURA (EXISTING NPCs: ADD, DON'T REBUILD)

**Quill Scratch (existing actor).** Add one feature to the existing actor, no stat changes:
- `Lore Reference: Cladis's Trail` (GM only). Quill has collected Cladis's trail marks for years: Threshold-family wayfinding marks, the open claim, an outstanding tag. Quill's aim (SETTLED): bring Cladis back so she can enlist the Rhime Goddess, who needs her name carried back into the Wyrd to fight the Niorghast and stop him resurrecting Nior. Quill knows the name from the trail but will not say it aloud; the Goddess writes it on the Stolen Shard in Scene 7.
- Sample lines: [EARN] *"She left marks for whoever came after. A trail. Your map is one. We follow it."* [EARN] *"There is a name. It isn't ours to say in a tavern."* [EARN] *"A thread tied in the wrong place can be tied again. Two knots and a good line. That's all."* *(On the anchor's Hunger trace)* *"Hunger. Her name has that word in it. I don't like that either."*

**Venfyura (existing NPC; SETTLED as the woman at the Eirwitch camp).** Do not build a new actor. Use her canon voice from the GM Reference ("little one", "Slowly. Truths keep.", choosing which truth to say today). Session 14 role: off stage. She keeps the fire and the bell at the camp, sends word through Pell ("V."), grew the fungal culture Violet works with, and (suggested) is the voice Europa remembers: "Not yet, little one." Her withdrawal/desertion reason stays [UNSETTLED]. **Foundry note:** no Venfyura actor JSON was found on the Vega share or in the repo; check the live world, and if she is missing, raise it with the GM rather than inventing a stat block.
