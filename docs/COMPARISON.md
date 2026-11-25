# Before and after

You asked to see the difference between the earlier vibe-coded attempts and this rebuild. The original prototype is
kept untouched in [`legacy/`](../legacy) so you can run both side by side:

```bash
cd legacy && python main.py
```

```bash
python main.py
```

## At a glance

| | Prototype (`legacy/`) | This rebuild (`warlord/`) |
|---|---|---|
| Code | ~2 000 lines of gameplay in one file, plus a second diverging copy of it (`main.py` and `warlord/game.py` are two different 1 941-line versions) | ~18 800 lines in 64 modules (round 3), no duplication |
| Structure | one `Game` class handling input, physics, AI, drawing, menus and the world | 9 packages with one-way dependencies: world, gfx, entities, combat, society, items, modes, ui, core |
| World | a 2 600 px sine-wave line with hand-placed anchors | a 48 000 × 256 tile world (about a 1-hour ride), procedurally generated in ~4 s |
| Terrain | not editable | dig, build, cave in; liquids, fire, falling sand, structural collapse |
| Places | a farm patch, a tent, a market, a wall, two house interiors | 30 settlements in 7 realms: villages, towns, a free city, capitals with castles, a monastery, a mine, ports, a robber castle |
| Characters | one rigid-body fighter type, hand-animated with per-state `if` branches | a skeletal rig with layered locomotion and action poses, plus modular clothing, armour, helmets, heraldry and weapons |
| Combat | sword states, block/parry, bow | the same idea taken further: a 3-hit combo, charge, low sweep, plunge, riposte, parry, posture, crouch-dodge; 15 weapons with their own mechanics; armour per damage type; wind and rain on missiles; bracing; hooking riders down |
| Battles | up to ~8 enemies, individually simulated | *Haufen* formations: hundreds of soldiers with depth ranks, front rotation, push of pike, volleys, cavalry charges, morale and routs, siege damage, 13 German orders, a zoomed-out commander view |
| NPCs | enemies with a vision cone | hundreds of named people with homes, trades, daily schedules, real work on the world, fire-fighting, fleeing, bilingual speech |
| Society | gold for wheat | a 9-rank social ladder with reasons, fiefs with daily dues, fealty, citizenship; supply-and-demand markets per settlement; wars, peace, marching armies, sieges, outlawry |
| Environment | none | day/night, seasons, wind, rain, storms with lightning fires, fog, snow, sailing, swimming and breath |
| German | none | 120 bilingual lines, 13 orders, every tile and item named in German, a Wörterbuch with a quiz, *du*/*Ihr* by rank |
| Modes | one play state | a 7-chapter story, a sandbox in 3 sizes, 4 set-piece battles, save/load |
| Audio | none | a procedural sound bank, no asset files |
| Tests | none | a headless harness that drives the real game with scripted input and saves screenshots |

## How it was built

The difference isn't only in the amount of code. It's in the order the work was done:

1. **Architecture first.** The module boundaries were fixed before any gameplay code: an `Intent` object between
   controllers and bodies, data registries for content, the session as the only way systems talk to each other,
   and numpy layers plus chunk caching for a world this size. The prototype grew the other way, one feature at a
   time inside a single class, until it forked into two copies.
2. **Scale decided up front.** "An hour's ride" became a number: 215 px/s gallop × 3 600 s ≈ 48 000 tiles. That
   number forced vectorised generation, a level-of-detail simulation for people, and cached rendering — rather
   than discovering the limits later.
3. **Verified by running it.** Every system was exercised headless through the real main loop, with scripted
   keys and mouse, and the screenshots were inspected. That process caught real bugs, for example:
   - a stale fall-height value that killed the player on spawn (a "520 damage" fall);
   - houses walling off the street, which in a side view blocks the whole village; every building now has doors
     on both sides that open as you walk into them;
   - NPCs reacting to attacks within one frame and parrying everything; they now have skill-based reaction times;
   - braced pikemen who never attacked, because blocking suppressed their thrusts;
   - infantry battles that would take ten minutes, because only the front duels killed anyone; push-of-pike
     attrition fixed that;
   - the background mountains sitting below the ground line, and a negative-index bug that erased the battle
     arenas' backgrounds;
   - the player taking ordinary fall damage on top of the sky-drop damage after falling through the Abyss;
   - a chunk-cache eviction bug that re-rendered about 8 screen chunks every frame in busy towns (27 ms → 11 ms
     per frame once fixed), found by a day-long soak test in the capital;
   - ridden horses being simulated twice per frame, which would have made the "one-hour ride" about 45 minutes;
   - guards hopping up the floors of a keep whenever a wall blocked them, then walking off the top;
   - formations walking over a breached gate's arch instead of through the opening;
   - an event-name clash that would have crashed story chapter IV the moment your watchtower was finished.

## Honest limitations, and what I'd do next

- **Art** is procedural shapes, as you asked for simple graphics. The rig and tile-art modules are the place to
  swap in pixel art later, without touching gameplay code.
- **NPC pathfinding is horizontal.** NPCs walk, jump, swim and open doors, but don't plan routes up ladders to
  second floors or into caves.
- **Balance** was tuned through automated simulation runs, not human playtesting. Expect to adjust numbers in
  `combat/weapons.py`, `combat/units.py` and `combat/formation.py`.
- **Distant armies** are abstract until they get close. Siege ladders and battering rams as separate units would
  be the next step for sieges.
- **Performance** is about 8–11 ms per frame normally (including a capital with 55 people) and about 16 ms in
  the zoomed battle view on the test machine. Python sets a ceiling: thousands of individually simulated fighters would need numpy-batched AI or a
  compiled core.
- The **story** is complete and playable end to end, but its longer journeys use cut-scene travel, and its
  dialogue is linear rather than branching.

## Round 2

The second round added sieges, low-poly modular bodies with ragdolls, hit locations with armour hardness and
wounds, progressive German, realm-specific architecture, realistic farming and seasons. The same
build-and-run-it loop caught bugs in that round too:

- The siege tower couldn't roll up a 2-tile step, and every formation queued behind it forever. Formations now
  only queue behind a block that is actually fighting or stuck at a wall.
- The defenders only reacted when the player stood close by, so the drawbridge never rose.
- The trebuchet and the guns were placed out of range and never fired. Once fixed, they battered the gatehouse
  from 36 bricks down to 2.
- After their first breach, sappers couldn't start on the next wall.
- A farmer without a field crashed the game, and the ambient-life system failed after loading a save.

The sapping test is a good example of the physics doing the work. Sappers dig 37 tiles of tunnel, swap 6
foundation tiles for timber props and set them alight. Fire spreads through the props, and when 3 or more
adjacent props are gone, the span rule brings 21 bricks of tower wall down.

## Round 3: from tiles to polygons

You asked for no blocks at all: a world of polygons with physics, a bag instead of a slot grid, and crafting by
shaping wood. The tile version is archived in [`legacy/tile_v2/`](../legacy/tile_v2) so both can be run side by
side.

| | Round 2 (`legacy/tile_v2/`) | Round 3 (`warlord/`) |
|---|---|---|
| Ground | 16 px tiles with rounded corners | a smooth surface line over a rock crust; caves cut out as polygons |
| Physics | AABB against a tile grid, auto step-up | pymunk rigid bodies: capsules for people and animals, polygons for everything else |
| Buildings | tiles, a span rule for collapse | pieces (posts, panels, ashlar blocks, roof slabs, doors) in a support graph; unsupported pieces fall as rigid bodies |
| Trees | trunk and leaf tiles, removed at once | painted trees (branching limbs, leaf-dab crowns, bark) that sway and rustle; the trunk topples on a hinge at the stump and lands as a log |
| Interaction | mine and place any tile | fell, buck, carry, break, place, go underground |
| Crafting | recipe list | shaping: axe strokes along guide lines in the field, or saw/chisel/drill/rasp at a workbench, matched against 16 forms with a quality score |
| Inventory | 40 slots + hotbar | a Rucksack limited by weight, a 4-slot belt, bulky things carried in your arms |
| Animals | ellipses with stick legs | quadruped skeletons with IK legs and real walk, trot and gallop footfall patterns |
| Ragdolls | verlet points against tiles | rigid bones joined with rotation limits |
| Drawbridge | swapping tiles | a kinematic plank rotating on its hinge, wound up on chains |

How the switch was made without throwing away rounds 1 and 2: the character body kept its old interface.
Controllers still set `vx`/`vy` and read `on_ground`, `in_water`, `blocked`; underneath, `physics()` hands the
wanted velocity to pymunk and `post_step()` reads the result back. So combat, the injury model, NPC brains,
formations, society, the German weave and the story needed only their world-touching parts rewritten.

Bugs this round's test runs caught:
- characters walked through closed doors: setting the velocity every frame pushed the capsule through the thin
  door piece. The controller now projects the wanted velocity along last step's contact normals, so walls stop
  you and slopes guide you;
- doorways were 40 px high and people 42 px, so everyone snagged on the lintel even with the door open;
- palisades and the windmill's post blocked the whole road — in a side view anything across the path is a wall;
  palisades got a wicket gate, the mill post no longer collides;
- a ramp meeting a raised walkway's deck left a 6 px edge that stopped walkers; ramps now run flush onto the
  deck;
- the castle moat was dug under the outer tower instead of in front of it;
- drawbridges never moved: the gatehouses were never attached to the physics space after generation;
- a numpy `float32` from an ore position reached the camera and crashed the parallax drawing;
- a full bag made dropped items spam "too heavy" every frame; the start kit (60 planks) was over the weight
  limit, and seeds weighed 2 kg each.

Limits: physics runs only within about 2 700 px of the player; farther away the world is data. NPCs walk,
jump small obstacles and open doors, but don't plan routes up ladders. Shaping matches against a fixed
library of forms; anything else is a Rohling you can place but not use as a tool.

### Round 3, after the first play

- **The world felt inert** because the hands only worked when you held the exact right tool and pointed at the
  exact trunk pixel within 92 px. Now you point anywhere on a tree while standing next to it, hold the mouse,
  and the right tool comes out of the bag by itself; a line above the belt says what the click will do. You can
  **dig** — a shovel for earth, a pick for rock — straight down if you like; the earth goes into the bag and
  can fill a hole again, and walls lose their footing when you dig under them.
- **Riding:** the rider sat inside the new, taller horse. The seat now comes from the horse's skeleton; the rider
  sits astride with legs to the stirrups and both hands on the reins when empty-handed.
- **Bow:** the bow stayed upright whatever you aimed at. It now tilts across the line of the shot, the archer
  turns to the mouse, and a dotted arc shows the flight. Keyboard archery: hold J, W/S raise or lower the bow
  (Shift for fine aim), A/D turn, release to shoot.
- **Planks:** the workbench rips a straight log into boards: about six planks per felled oak.
