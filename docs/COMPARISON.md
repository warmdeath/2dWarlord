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
| Code | ~2 000 lines of gameplay in one file, plus a second diverging copy of it (`main.py` and `warlord/game.py` are two different 1 941-line versions) | ~12 600 lines in 52 modules, no duplication |
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
   - the player taking ordinary fall damage on top of the sky-drop damage after falling through the Abyss.

## Honest limitations, and what I'd do next

- **Art** is procedural shapes, as you asked for simple graphics. The rig and tile-art modules are the place to
  swap in pixel art later, without touching gameplay code.
- **NPC pathfinding is horizontal.** NPCs walk, jump, swim and open doors, but don't plan routes up ladders to
  second floors or into caves.
- **Balance** was tuned through automated simulation runs, not human playtesting. Expect to adjust numbers in
  `combat/weapons.py`, `combat/units.py` and `combat/formation.py`.
- **Distant armies** are abstract until they get close. Siege ladders and battering rams as separate units would
  be the next step for sieges.
- **Performance** is about 8–10 ms per frame normally and about 16 ms in the zoomed battle view on the test
  machine. Python sets a ceiling: thousands of individually simulated fighters would need numpy-batched AI or a
  compiled core.
- The **story** is complete and playable end to end, but its longer journeys use cut-scene travel, and its
  dialogue is linear rather than branching.
