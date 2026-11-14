# Jezero Walk — five assignments

Read [plan.md](plan.md) first. It is the contract: the region, the two projections, the grid, the costs, the routes, and what the page is allowed to claim. If a sentence in this file disagrees with a number in the plan, the plan wins. Write the disagreement in your handoff. Do not rename a field on your own.

This file is one job for each person. The headings inside your section are there so you can find a paragraph. They are not a stack of tickets, and they are not an invitation to invent a second interface. If you want a personal checklist later, copy your section into its own file and break it up there.

Five people, five seats. The work is divided so each of you can finish a practice version on the shared fixture before the Jezero crop exists.

| Seat | Who | Section |
| --- | --- | --- |
| Route search | Ayush | below |
| Mission page | Dhani | below |
| Elevation grid | write your name on the first line of that section | below |
| 3D surface | write your name on the first line of that section | below |
| Shell, science, and submission | write your name on the first line of that section | below |

Shared rules, short, because each section repeats the parts that matter:

- New repository. Do not build this inside the robot-patrol repo. These documents are the specification you copy in.
- The route is A*, not a language model.
- Row 0 of every array is south. Row 0 of every JPEG is north.
- Negative elevation is real. Null is missing.
- Four-connected steps. No diagonals.
- One route object, drawn twice. The map and the mesh do not each invent a line.
- The practice grid is labeled as practice. Jezero is whatever `terrain.json` says, at the tier the data section shipped.
- Submission closes Sunday 15 November 2026 at 23:59 Europe/Rome.

# Ayush — the route search

You own the search. The page asks your function which way to walk, and it draws whatever you return.
Dhani does not reimplement the costs. The 3D view does not reimplement the costs. If the line is wrong,
it is this module until the grid itself is wrong.

Read [plan.md](plan.md) sections 9, 10, and 11 before writing code. Those sections are the contract.
This assignment tells you how to meet it. If a sentence here fights a number in the plan, the plan wins,
and you note the fight in `handoff/router.md`.

You can build and test the whole module on Saturday afternoon without the GeoTIFF, without React, and
without the rest of the team. The fixture in plan section 10.1 is your Mars until `terrain.json` exists.

## What you are making

One pure function:

```ts
planRoutes(terrain: Terrain, request: RouteRequest): RouteSet
```

It runs three four-connected A* searches on the grid in `terrain` and returns the three routes plus the
name of the recommended one. It does not fetch, does not read the clock, and does not mutate `terrain`.
Calling it twice with the same arguments returns deep-equal results.

The function lives at `app/src/router/planRoutes.ts` and is exported from `app/src/router/index.ts`.
Tests live in `app/src/router/planRoutes.test.ts` and run with Vitest. You do not edit `src/map`,
`src/view3d`, `src/briefing`, or `data/`. You may edit `src/contract.ts` only to fix a typo that the
integration seat agrees is a typo. Until that file exists, paste the types below into
`src/router/types.ts` and switch the import when `contract.ts` lands. Do not let the two copies drift.
Diff them.

You know Python. The module is TypeScript because Dhani's page has to recompute when a person flips a
toggle, on a static host, with no Python process. Write the search in TypeScript. A Python notebook is
fine as scratch paper. The notebook is not the submission, and it is not imported by the page.

If TypeScript itself is the thing blocking you two hours in, stop and say so in the handoff. The
fallback, which is worse, is a small Python script that reads `terrain.json` and writes `routes.json`
for the three destinations and both travelers, six files, and Dhani displays those files without a live
toggle. Do not take the fallback while the fixture tests are still failing for ordinary reasons. Take it
only if the language, not the algorithm, is the blocker. The demo is much stronger if the toggle
recomputes.

## Files you own

```text
app/src/router/planRoutes.ts
app/src/router/index.ts
app/src/router/planRoutes.test.ts
app/public/fixtures/corridor.json
handoff/router.md
```

You create `corridor.json` from plan section 10.1 so Dhani and the 3D seat have the same file. It is
data, not a favor. Keep it valid `jezero-walk.terrain.v1`.

You do not commit `node_modules`. You do not add a pathfinding library. The search is short, and a
library would hide the tie-break that the tests are about.

## The terrain object you receive

`terrain.arrays` holds four row-major arrays of length `width * height`. Index `i = row * width + col`.
Row 0 is south. Column 0 is west. This is the opposite of a GeoTIFF and the opposite of most image
libraries. Do not flip anything inside the router. If the picture looks upside down, the data build or
the map flipped it. Your cells stay in this index.

`elevation_m[i]` is a number in meters, often near −2,500 in Jezero, or `null`. Negative elevation is
real ground. `null` is missing. `slope_deg[i]` and `roughness_m[i]` are numbers or `null`. `coverage[i]`
is 0, 1, or 2.

A cell is outside the grid when `col` or `row` is not an integer in range. A cell is impassable for a
traveler when any of these is true:

- The column or row is outside.
- `slope_deg` is `null`.
- `coverage` is 0.
- `coverage` is 1 and `request.avoidUncertain` is true and the mode is `uncertainty`. The other two
  modes still walk on coverage 1 when the flag is on. Read that again before you code it. The flag does
  not edit the terrain array. It changes the legality test inside the uncertainty search only.
- `slope_deg` is greater than or equal to the traveler's block threshold. Astronaut 20. Rover 25. Equal
  to the threshold is blocked. 19.999 is allowed for an astronaut. Do not round the slope to an integer
  before the comparison.

The start cell is not required to be passable in order to return a result object. If the start is
impassable, every mode is `unreachable` and `blocked_reason` is the first reason in this list that
applies: `outside`, `nodata` (slope null or coverage 0), `uncertain` (only if this mode treats coverage
1 as blocked), `slope`. If the goal is impassable, same shape, the search never starts. If start and
goal are the same in-range cell, return `unreachable` with reason `outside`. A zero-length path is not a
successful walk. Plan section 18 locks that.

Do not throw for a bad start or goal. Throw, once, if `arrays` are not the same length as `width *
height`, or if `cell_size_m` is not a positive number. That is a broken file, not a user action.

## Costs

Constants, copied from the plan so you do not have to keep the plan open while typing:

| | astronaut | rover |
| --- | --- | --- |
| block degrees | 20 | 25 |
| caution degrees | 12 | 15 |
| planning speed | 1000 m/h | 110 m/h |

Caution does not enter the cost and does not block. It is for the sheet, which Dhani colors. You still
return `max_slope_deg` so the sheet can see it. You do not return a caution flag. The sheet can compare
`max_slope_deg` to 12 or 15 itself. Putting the threshold in two places is how they drift, so export the
thresholds from `src/router/profiles.ts` as `TRAVELERS` and let Dhani import that object. One
definition.

Weights:

| mode | alpha | beta | gamma |
| --- | --- | --- | --- |
| shortest | 0 | 0 | 0 |
| terrain | 4 | 2 | 0 |
| uncertainty | 4 | 2 | 6 |

For a legal step into a cell:

```text
S = slope_deg / block_deg
U = 0 if coverage is 2, 1 if coverage is 1
R = min(roughness_m / 1, 1) when roughness is a number, else 0
cost = cell_size_m * (1 + alpha * S + beta * R + gamma * U)
```

S is strictly less than 1 on a legal cell because the block test already removed slopes at or above the
threshold. R saturates at 1 meter of standard deviation. A roughness of 4 m does not multiply the cost
by four. U is 0 or 1, never 0.5. Coverage 0 never reaches this formula.

The cost is charged on the cell you enter. The start cell contributes to `max_slope_deg`,
`mean_slope_deg`, climb, and the poorly-observed fraction, because the walker is standing there. It does
not contribute a step cost.

`distance_m` is the number of steps times `cell_size_m`. Four-connected, so every step is exactly one
cell. Do not use the Euclidean length of the polyline. On this grid those two numbers match anyway. Keep
the step count so a later diagonal experiment cannot silently change the meaning.

`equivalent_cost_m` is the sum of step costs. It is not the distance, except in `shortest` mode where
the weights are zero and the two numbers match.

`time_h` is `distance_m / speed`. Not `equivalent_cost_m / speed`. The clock measures ground, not
penalty. Labeling is Dhani's job. The number is yours.

Climb and descent walk the cell centers in order. `climb_m` is the sum of positive elevation
differences. `descent_m` is the sum of the absolute negative differences. A `null` elevation on an `ok`
path is a bug in the legality test. If you see one, the path should have been unreachable.

`poorly_observed_fraction` is the number of cells on the path, including start and goal, whose coverage
is 1, divided by the number of cells on the path. Coverage 2 is well observed for this statistic.
Coverage 0 cannot appear. Use a real division. A path of eight cells with four coverage-1 cells is 0.5.

`mean_slope_deg` is the arithmetic mean of `slope_deg` over the path cells, including start and goal.
`max_slope_deg` is the maximum of those same cells.

`cells` is `[col, row]` from start to goal inclusive. Integers.

## The fixture, with the arithmetic written out

Build `corridor.json` exactly like this. Width 6, height 5, cell 10 m. Fill slope 2, roughness 0,
coverage 2, elevation 0, then overwrite:

- slope 40 at (2, 2) and (3, 2).
- slope 3 and coverage 1 at (1, 3), (2, 3), (3, 3), (4, 3).
- slope 18 and coverage 2 at (1, 1), (2, 1), (3, 1), (4, 1).

Request start `(0, 2)`, goal `(5, 2)`. Only columns 2 and 3 of row 2 are blocked, so `(1, 2)` and `(4,
2)` are ordinary ground. Row 0 is flat. The winning lines are the ones a correct search returns, not the
two detours a person draws first. A search that returns a cell with slope 40 has a broken legality test.

Neighbor order when you expand is north, south, east, west. The heap key is `(f, g, row, col, seq)` with
`seq` increasing on every push. You may repush a cell when you find a better `g`. You ignore a popped
entry whose `g` is worse than the best `g` you have stored, and you mark the cell closed when you pop a
current entry. Those rules plus this fixture produce the lists below. Do not accept a different list
that happens to have the same distance.

`shortest`, either traveler, flag on or off. Seven steps, distance 70, equivalent cost 70. It walks the
18° cells because shortest does not care:

```text
(0,2) (1,2) (1,1) (2,1) (3,1) (4,1) (5,1) (5,2)
```

Score those same cells with astronaut terrain weights and the equivalent cost is 226. Entering a 2° cell
costs 14. Entering an 18° cell costs 46. One 14 and four 46s and two more 14s: `14 + 184 + 28 = 226`.
Rover terrain weights on the same cells cost 194.8. Assert 226 > 194.8. That catches a rover profile
that secretly uses the astronaut threshold.

`terrain`, either traveler, flag on or off. Seven steps. Astronaut equivalent cost 106. Rover equivalent
cost 98.8. Four of the eight cells are coverage 1, so `poorly_observed_fraction` is 0.5. Max slope is
3. Mean slope is 2.5.

```text
(0,2) (1,2) (1,3) (2,3) (3,3) (4,3) (4,2) (5,2)
```

Astronaut arithmetic for that line: enter `(1,2)` at 14, four coverage-1 cells at slope 3° costing 16
each, then `(4,2)` and `(5,2)` at 14. `14 + 64 + 28 = 106`. The coverage penalty is not in the terrain
weights, which is why this line beats the flat south edge. The south edge is nine steps of 14, cost 126,
and 126 is worse than 106.

`uncertainty`, either traveler, flag on or off. Nine steps, distance 90. Astronaut equivalent cost 126.
Rover equivalent cost 118.8. Every cell is coverage 2 and slope 2, so the fraction is 0, max slope is 2,
and mean slope is
2. The long flat line beats the north line once coverage 1 costs an extra 60 per step.

```text
(0,2) (0,1) (0,0) (1,0) (2,0) (3,0) (4,0) (5,0) (5,1) (5,2)
```

The flag does not change these three lists. The north line is legal terrain even when coverage 1 is
forbidden to the uncertainty search, and the uncertainty line never entered coverage
1. The flag changes the recommendation. Off: 126 is about 19 percent above 106, which is outside the 15
   percent band, so recommend `terrain` while the sheet still shows that half of that line is poorly
   observed. On: recommend `uncertainty`. Assert both recommendations.

## The search

Implement one function `search(terrain, traveler, mode, avoidUncertain, start, goal)` and call it three
times from `planRoutes`. Do not copy the loop three times.

Four neighbors, in this order when you generate them: north `(col, row+1)`, south `(col, row-1)`, east
`(col+1, row)`, west `(col-1, row)`. The order is part of the tie-break story. Skipping a neighbor that
fails the legality test happens before the neighbor is pushed.

Heuristic: Manhattan distance in cells times `cell_size_m`.

```text
h = (abs(col - goalCol) + abs(row - goalRow)) * cell_size_m
```

This is admissible because every legal step costs at least `cell_size_m`. Do not add slope into `h`. Do
not use Euclidean distance. Do not scale `h` by 1.001 to "speed it up".

`g` is the sum of step costs from the start. `f = g + h`.

Open set: a binary heap of `(f, g, row, col, seq)` where `seq` increases by one every push. Pop the
lexicographically smallest tuple. That is the whole tie-break: smaller f, then smaller g, then smaller
row, then smaller column, then older insertion. Several legal lines on the fixture share a cost. The
cell list is the test, not the distance. A shortest path of 70 m that is not the listed cells is still a
wrong function. If your language's heap compares arrays the same way, use it. If it does not, write the
five comparisons yourself.

Parent pointers: a `Map` from `"col,row"` to the previous cell, or a flat `Int32Array` of length `width
* height` storing the parent index, with −1 for none. The flat array is faster and harder to get wrong
at 400 by 400. Use it if you are comfortable, otherwise use the map. 160,000 cells is a small search
either way. It must finish in well under a second on a laptop for one mode. If a single search takes
longer than a second, you are reopening cells incorrectly or you have built a quadratic scan instead of
a heap.

Closed set: once a cell is popped, do not push it again. Because the heuristic is consistent (Manhattan
on a grid with non-negative added costs still consistent when the heuristic ignores those costs —
actually wait: consistency requires `h(a) <= cost(a,b) + h(b)`. Manhattan satisfies this when every step
costs at least the heuristic's step. Extra positive cost only increases the right-hand side. So yes, the
first time you pop a cell, `g` is optimal). Do not decrease-key. The simple "skip if already popped"
version is correct. The bug to avoid is the other one: marking a cell closed when you push it, which can
freeze a worse `g`. Mark closed on pop.

If the open set empties, return unreachable. `blocked_reason` is `slope` if any impassable cell you
considered failed the slope test and you never saw a nodata or uncertain rejection that you want to
prefer. You cannot see why the goal was cut off without extra bookkeeping. Use a simpler rule, which the
tests can check:

- If the goal cell itself is impassable, use the goal's reason, from the list in the legality section.
- If the goal cell is passable but no path reaches it, use `slope` when the grid contains any blocking
  slope and the start is passable, unless `avoidUncertain` is true and the mode is uncertainty and a
  coverage-1 barrier is what remains. On the fixture, goal `(2, 2)` is slope 40, so the reason is
  `slope` without any search. Add one more fixture case: set the entire middle column's coverage to 0
  except the start and goal on an otherwise open row, and expect `nodata`. Put that case in the test
  file as a second terrain built in memory, not by editing `corridor.json`. `corridor.json` stays the
  shared picture.

Path reconstruction: from the goal, follow parents to the start, then reverse. Confirm the first cell is
the start and the last is the goal. Confirm each step is an orthogonal neighbor. A test should check the
neighbor property on every returned `ok` path, not only the fixture's known list. That test catches a
parent-pointer bug that happens to pass on the tiny grid and fail on the real one.

Numbers: compute costs in ordinary JavaScript numbers. The fixture expectations use one decimal at most
(194.8). Compare costs with `toBeCloseTo(expected, 5)` so a `46.0000001` does not fail the suite and a
completely wrong 70 does. Compare cell lists with deep equality, not with a close-to.

## Recommendation

After the three searches:

- If every status is `unreachable`, `recommendation` is `null`.
- If `avoidUncertain` is true and the uncertainty route is `ok`, `recommendation` is `uncertainty`.
- If `avoidUncertain` is true and uncertainty is unreachable, `recommendation` is `terrain` if that
  route is `ok`, otherwise `shortest` if that is `ok`, otherwise `null`. Turning the flag on should not
  blank the map when a steeper well-observed route does not exist and a short route does. The flag
  expresses a preference, and the fallback order is uncertainty, then terrain, then shortest, skipping
  unreachable modes.
- If `avoidUncertain` is false, let `Ct` be the terrain equivalent cost and `Cu` the uncertainty
  equivalent cost. If both are `ok`, and `Cu <= 1.15 * Ct`, and the uncertainty path's
  `poorly_observed_fraction` is strictly lower than the terrain path's, recommend `uncertainty`.
  Otherwise recommend `terrain` if it is `ok`, else `shortest` if it is `ok`, else `null`.

On the fixture with the flag off, `Cu` is 126 and `Ct` is 106. 126 is greater than 1.15 times 106. Recommend
`terrain` even though the uncertainty path is better observed. That is the point of the 15% rule. A longer
flat line is not automatically the recommendation. The person can still select the uncertainty line. Dhani
draws all three. You only name the default.

Do not break ties between modes by distance. The rule above is the whole policy. Write it as code
without extra conditions. A comment above the block should quote the 15% rule in one sentence so the
next edit does not "simplify" it.

## Tests

Vitest. No snapshot of the whole `RouteSet` that you update with `-u` the first time it runs. Type the
expected cells by hand from this document. A snapshot would bless a wrong south-versus-north result.

Cases, all of them:

1. Fixture, astronaut, flag off. Shortest, terrain, and uncertainty cell lists are the three lists in
   the fixture section, in that order. Equivalent costs 70, 106, and 126. Distances 70, 70, and 90.
   Recommendation `terrain`. Terrain `poorly_observed_fraction` 0.5. The other two fractions are 0.
   Terrain mean slope 2.5. Shortest max slope 18.
2. Fixture, rover, flag off. Same three cell lists. Terrain equivalent cost close to 98.8. Uncertainty
   equivalent cost close to 118.8. Astronaut terrain-weights on the shortest cells, 226, greater than
   rover terrain-weights on those cells, 194.8.
3. Fixture, astronaut, flag on. The three cell lists are unchanged. Recommendation `uncertainty`.
4. Goal `(2, 2)`, astronaut. All three unreachable, reason `slope`, recommendation `null`. `cells` is an
   empty array, not a partial path.
5. Start equal to goal `(0, 2)`. Unreachable, reason `outside`.
6. Elevation −2500, slope 1, coverage 2, on a 3 by 3 open grid, start `(0, 1)`, goal `(2, 1)`. Status
   `ok`. The negative elevation did not block.
7. In-memory column of coverage 0 between start and goal. Reason `nodata`.
8. `planRoutes` called twice. Deep-equal results, and the terrain arrays are unchanged (hold a copy of
   `slope_deg[0]` and compare).
9. A terrain with `width * height` not equal to the array length throws.
10. Every `ok` path in the tests has orthogonal steps, starts at the request start, and ends at the
    request goal.

Run `npx vitest run src/router` from `app/` and paste the summary into the handoff. Ten tests, or fewer
if you group assertions, but every numbered case is present. Do not skip case
6. The real Jezero grid is negative and case 6 is how we avoid a Sunday-morning panic.

## When the real grid arrives

You do not parse the GeoTIFF. You write a tiny script, `app/src/router/devCheck.ts`, or a test that is
skipped unless `public/terrain.json` exists, which loads the JSON and checks:

- `planRoutes` returns in under a second for a corner-to-corner astronaut terrain search.
- No `ok` path contains a null slope or a coverage 0.
- No `ok` path contains a slope at or above 20 for the astronaut.
- The three modes can be different. If all three cell lists on a real destination are identical, say so
  in the handoff. It may be an honest result on a flat patch. It may mean the data seat marked every
  cell coverage 2 and the slopes never reach the weights. Look at the slope histogram before you change
  weights. Do not change weights to force three pretty lines.

Pick the outpost and the destinations only from `pois.json` cell coordinates once the integration seat
has written them. Until then, run corner-to-corner and one search from the center to a corner, and
record max slope and poorly-observed fraction in the handoff.

If the real search returns `unreachable` for two points you can see are on the same side of a cliff, the
cliff may actually separate them at 5 m. Look at the slope JPEG before you weaken the threshold. The
threshold is a product decision. Weakening it is a plan change, not a bugfix.

## How this meets Dhani and the mesh

Export types from the router only as re-exports of the contract types. Dhani needs `planRoutes`,
`TRAVELERS`, and the `RouteSet` type. Give a one-file example in the handoff:

```ts
import corridor from "../public/fixtures/corridor.json";
import { planRoutes } from "./router";

const routes = planRoutes(corridor as Terrain, {
  traveler: "astronaut",
  avoidUncertain: false,
  start: { id: "outpost", col: 0, row: 2 },
  goal: { id: "east", col: 5, row: 2 },
});
```

If `corridor.json` does not satisfy the type because JSON imports widen numbers, validate the four array
lengths at the start of `planRoutes` and trust the fields. Do not build a schema library for this. A
length check and a `cell_size_m > 0` check are the validation.

The mesh will ask for `cells`. Do not also return a list of lon/lat. You do not own the projection.
Dhani converts `[col, row]` to meters with the formula in plan section 8.2. If you return both and they
disagree, the bug will be yours by default. Return cells only.

## The grid, written out so the index cannot be flipped

Row 4 is the north edge. Row 0 is the south edge. Each cell is `slope/coverage`. A dash is the default
2° and coverage 2, which is what you fill first.

```text
row 4:  -    -    -    -    -    -
row 3:  -   3/1  3/1  3/1  3/1   -
row 2:  S    -   40   40    -    G
row 1:  -   18   18   18   18    -
row 0:  -    -    -    -    -    -
```

S is the start, column 0. G is the goal, column
5. Both are ordinary 2° coverage-2 cells. The 40s are impassable. `3/1` means slope 3 and coverage
1. `18` means slope 18 and coverage 2.

Index check you should assert while building the JSON: `slope[2 * 6 + 2] === 40`, `coverage[3 * 6 + 1]
=== 1`, `slope[1 * 6 + 4] === 18`, `slope[0] === 2`. If the 40s show up on row 3, you stored the array
north-up and every expected cell list will look insane. Fix the file. Do not "fix" the search by
swapping row with `height - 1 - row`.

Elevation stays 0 everywhere in this file. Roughness stays 0. `cell_size_m` is
10. `width`
6. `height`
5. `origin` can be 77.35° E, 18.42° N. The search does not read the origin. Put it in anyway so the file
   validates as the same schema as the real grid.

## What the first pops of the shortest search look like

This trace is the shortest mode, astronaut, start `(0, 2)`, goal `(5, 2)`. Heuristic at the start is `5
* 10 = 50`. Rejected neighbors are the ones with slope 40 or off the board. They never enter the heap.

The first pop is the start, `g = 0`, `f = 50`. From it you push north `(0, 3)` and south `(0, 1)` at `f
= 70`, and east `(1, 2)` at `f = 50`. West is off the board. The next pop is `(1, 2)`, because 50 beats
70. That is the search stepping toward the goal before it explores the detours.

From `(1, 2)`, east is `(2, 2)`, slope 40, and it is not pushed. North `(1, 3)` and south `(1, 1)` are
pushed at `g = 20`, `f = 70`.

The following pops, while everything sits at `f = 70`, go to the smaller row first when `g` ties: `(0,
1)` before `(0, 3)`, then `(1, 1)` before `(1, 3)`, then `(2, 1)`, `(2, 3)`, `(3, 1)`, `(3, 3)`, `(4,
1)`, `(4, 3)`. The goal is reached by continuing east along row 1 and stepping north at the end. You do
not need to memorize this list. You need your instrumented run to match it. Print each pop while the
test is failing. When the pops match and the cell list does not, the parent pointer is the bug, not the
heap.

A useful temporary log line is `pop col,row g f` and nothing else. Delete it before you call the module
done. The tests are the log that stays.

## A roughness case, so beta is not dead code

The fixture has roughness 0, so beta never changes a result. Add an in-memory terrain, not a second
public JSON, with width 4, height 1, cell size 10, slope 1 everywhere, coverage 2, elevation 0. That row
is a straight line. Then set roughness to 5 on cells `(1, 0)` and `(2, 0)` only... wait, a single row
has no alternate path, so both modes must take it and the cost must show the penalty. Start `(0, 0)`,
goal `(3, 0)`, terrain mode, astronaut.

R saturates at 1, so roughness 5 is R = 1, not
5. Entering `(1, 0)` and `(2, 0)` costs `10 * (1 + 4 * 1/20 + 2 * 1) = 10 * (1 + 0.2 + 2) = 32`.
   Entering `(3, 0)` has roughness 0, slope 1, cost `10 * (1 + 4 * 1/20) = 12`. Equivalent cost `32 + 32
   + 12 = 76`. Shortest mode on the same grid ignores R and costs 30. If your terrain cost comes back
   30, beta is not in the formula. If it comes back `10 * (1 + 0.2 + 2 * 5)` you forgot the saturation
   and treated roughness as unbounded.

Then build a second in-memory grid, width 4, height
2. Row 1 has roughness 0. Row 0 has roughness
5. Slope 1, coverage 2, everywhere. Block nothing. Start `(0, 1)`, goal `(3, 1)`. Shortest may stay on
   row 1, cost 30, three steps. Terrain must also stay on row 1, because dipping into row 0 adds a
   saturated roughness penalty and a longer path. Assert the terrain cells are `(0,1) (1,1) (2,1)
   (3,1)`. This is the test that says a rough patch is avoided when a smooth patch is the same slope.
   One assertion. Do not skip it because the fixture already passes.

## Python habits that will fail this file

You are writing TypeScript after writing Python. The failures that show up in this module are small.

JSON `null` is `null`, not `None`, and it is not `undefined`. The arrays in the file use `null` for
missing elevation. A check `slope === undefined` will not catch a missing value that was written as
`null`, and the cell will then fail when you divide. Check `slope == null` if you want both, and write
`null` in the fixture.

There is no integer division. `4 / 8` is `0.5`. The poorly-observed fraction wants that. `Math.floor`
would make it `0` and the test that expects `0.5` is how you notice.

Equality on objects is not deep. `cells` compared with `===` against another array is always false. Use
Vitest's `toEqual` on the cell list and `toBeCloseTo` on costs.

`heapq` is not in the language. A binary heap is about forty lines: push onto an array, sift up, sift
down, pop the root. Compare the tuples with an explicit function. Do not `sort()` the open set on every
expansion. It will pass the fixture and feel bad at 400 by 400, and it is easy to sort by the wrong key.
Write the heap once, in `heap.ts`, and test it with ten numbers before you connect it to the search. The
heap test pushes `(2, 0)`, `(1, 5)`, `(1, 4)` and expects pop order `(1, 4)`, `(1, 5)`, `(2, 0)`. That
is the row-and-column tie-break in miniature if you store `(f, g, row, col)`.

Do not use a `for...in` loop on an array. It visits keys as strings. Use an index.

A `Map` keyed by an array `[col, row]` does not work. Arrays are compared by identity. Key it by the
flat index `row * width + col`, which is a number.

Do not update the caller's arrays. The test that snapshots `slope_deg[0]` exists because a sort-in-place
or a "fill nulls with zero" cleanup will break the data seat's file for everyone else in the same
session.

## Reading a RouteSet the way the page will

Dhani will render your object without calling you to interpret it. Walk one fixture result as if you
were the sheet.

Astronaut, flag off, recommendation `terrain`. The terrain route is `ok`, distance 70, equivalent cost
106, time `70 / 1000 = 0.07` hours, which is 4.2 minutes. The sheet may show minutes. You return hours.
Agree that in the handoff so Dhani does not multiply twice. Max slope 3, which is under the astronaut
caution of 12, so this line is not a caution line even though it is poorly observed. Poorly observed is
not the same thing as steep. The uncertainty route is also `ok`, distance 90, time 0.09 hours,
equivalent cost 126, max slope 2, fraction 0. Shortest is `ok`, distance 70, max slope 18, which is over
the caution threshold of 12 and under the block of 20. The sheet should be able to say "steep" from
`max_slope_deg` alone. You do not add a string `warning: "steep"`. Strings in the route object are the
mode name, the status, and the blocked reason. Everything else is a number, an id, or the cell list.

When status is `unreachable`, `cells` is `[]`, distance is 0, climb is 0, descent is 0, time is 0,
equivalent cost is 0, fractions are 0, and `max_slope_deg` is `null`. `null` rather than 0, because 0
would mean a flat path. Dhani must handle `null` on those fields for an unreachable route. Say that in
the handoff in one sentence. The reachable fixture never produces a null max slope, so this rule is easy
to forget. Add it as an assertion on the blocked-goal test.

`blocked_reason` for an unreachable goal on slope 40 is `slope`. For the same-cell request it is
`outside`. For the coverage-0 wall it is `nodata`. Do not invent `blocked` as a reason. The plan's list
is `slope`, `nodata`, `uncertain`, `outside`.

## The real grid, what you measure

When `public/terrain.json` appears, do not retune weights in the same hour. Run four searches and write
the four lines into the handoff:

- South-west cell to north-east cell, astronaut, terrain, flag off. Distance, max slope, fraction,
  status.
- The same search, rover.
- The same search, astronaut, flag on.
- A search whose start is the center cell, goal the north-east cell, all three modes. Say whether the
  cell lists differ.

If the corner-to-corner terrain search is unreachable, record the reason and the fraction of cells with
slope at or above 20. You can count that with a five-line loop. If more than half the crop is blocked
for an astronaut, tell the data seat. The rectangle may be a cliff face. That is their move, not a
reason to set the block to 40°.

Time the corner-to-corner search with `performance.now` or `Date.now` around the call, not inside it.
Budget is one second for one mode on a 400 by 400 grid. A binary heap does this easily. A linear scan of
the open set may not. If you miss the budget, replace the open-set structure before you touch the cost.

## Types to paste if contract.ts is not there yet

Paste this into `src/router/types.ts` and delete it when the import from `contract.ts` typechecks. Do
not improve the names.

```ts
export type Traveler = "astronaut" | "rover";
export type Mode = "shortest" | "terrain" | "uncertainty";
export type BlockReason = "slope" | "nodata" | "uncertain" | "outside";

export type Terrain = {
  schema: "jezero-walk.terrain.v1";
  cell_size_m: number;
  width: number;
  height: number;
  arrays: {
    elevation_m: Array<number | null>;
    slope_deg: Array<number | null>;
    roughness_m: Array<number | null>;
    coverage: number[];
  };
};

export type RouteRequest = {
  traveler: Traveler;
  avoidUncertain: boolean;
  start: { id: string; col: number; row: number };
  goal: { id: string; col: number; row: number };
};

export type Route = {
  mode: Mode;
  status: "ok" | "unreachable";
  cells: Array<[number, number]>;
  distance_m: number;
  climb_m: number;
  descent_m: number;
  max_slope_deg: number | null;
  mean_slope_deg: number | null;
  poorly_observed_fraction: number;
  equivalent_cost_m: number;
  time_h: number;
  blocked_reason: BlockReason | null;
};

export type RouteSet = {
  schema: "jezero-walk.routes.v1";
  traveler: Traveler;
  avoid_uncertain: boolean;
  start: { id: string; col: number; row: number };
  goal: { id: string; col: number; row: number };
  recommendation: Mode | null;
  routes: [Route, Route, Route];
};
```

`routes` is a tuple of three, ordered shortest, terrain, uncertainty. Dhani indexes `[0]`, `[1]`, `[2]`
only if the mode field matches. Tell them to find a route by `mode`, not by position, and still keep
this order so a quick glance at the JSON is stable.

The request field is `avoidUncertain` in camelCase because it is a TypeScript argument. The result field
is `avoid_uncertain` in snake_case because it is JSON the briefing stores. That split is annoying and it
is intentional. Do not rename one to match the other tonight.

## Climb and descent on negative elevations

In-memory grid, one row, three columns, cell 10 m, slope 1, roughness 0, coverage
2. Elevations `-2500`, `-2490`, `-2505`. Start `(0, 0)`, goal `(2, 0)`, any mode.

The path has two steps. Distance 20. Climb is `(-2490) - (-2500) = 10`. Descent is `abs((-2505) -
(-2490)) = 15`. If you take the absolute value of the elevation itself, climb becomes thousands of
meters and the briefing is nonsense. This is the test that protects Jezero's real numbers, which sit
near −2,500 m. Assert climb 10 and descent 15. Assert status `ok`.

A descending-only path, elevations `-100`, `-110`, start to goal one step, has climb 0 and descent
10. Assert that too. A zero climb is legal. Do not treat it as missing data.

## Inputs that are not a route question

Coverage value 7, slope `NaN`, roughness negative, `cell_size_m` of 0, a non-integer column on the
request. Behavior:

- `cell_size_m <= 0`, or a non-integer width, or arrays of the wrong length: throw. The message can be a
  plain string. This is a bad file.
- Coverage other than 0, 1, or 2: treat the cell as impassable with reason `nodata`. Do not throw in the
  middle of a search because one cell is corrupt. Count how many such cells you saw only if you have
  time. The handoff can say "corrupt coverage is nodata."
- `NaN` slope: impassable, reason `nodata`. `NaN >= 20` is false in JavaScript, so a naive block test
  lets a NaN cell through and then poisons every cost. Test `Number.isFinite(slope)` before the block
  comparison.
- Negative roughness: treat as 0. A negative standard deviation is not a real output of the data build.
  Do not throw.
- Non-integer `col` or `row` on the request: all three routes unreachable, reason `outside`.

One test can cover NaN slope on the goal and expect `nodata`. One test can cover coverage 7 the same
way. You do not need a test for every bullet if the finite-slope check is the one that can fail
silently. That one is required.

## The 15 percent rule, in numbers

Astronaut fixture, flag off. Terrain equivalent cost 106. Uncertainty equivalent cost 126. The cutoff is
`1.15 * 106 = 121.9`. 126 is above 121.9, so uncertainty is not recommended even though its
poorly-observed fraction is 0 and terrain's is 0.5. The rule needs both the cost band and the better
fraction. Write it that way:

```text
if uncertainty is ok and terrain is ok
   and uncertainty.equivalent_cost_m <= 1.15 * terrain.equivalent_cost_m
   and uncertainty.poorly_observed_fraction < terrain.poorly_observed_fraction
then recommend uncertainty
else recommend the first ok mode in the order terrain, shortest
```

The flag-on branch comes before this comparison and recommends uncertainty whenever that route is ok. On
the fixture, flag on, uncertainty is ok, so you never reach the 15 percent test. A test that only
toggles the flag and checks the cell lists will miss a recommendation bug. Assert `recommendation` by
name.

Boundary case, in memory, so the comparison itself is tested. Build a grid where you do not care about
the geometry and instead call the recommendation helper with fake route objects if you split that helper
out. Terrain cost 100, fraction 0.4. Uncertainty cost 115, fraction 0.1. `115 <= 115`, fraction is
lower, recommend uncertainty. Change uncertainty cost to 115.01 and recommend terrain. This is the one
place `toBeCloseTo` can lie to you. Compare the recommendation, and use costs that are not almost-equal
unless you mean the boundary. 115 and 115.01 are different sides of `1.15 * 100` if you multiply
exactly. Check what JavaScript does: `1.15 * 100` is 114.99999999999999 in IEEE, not 115. So `115 <=
1.15 * 100` is false. Do not use 1.15 and 100 and 115 as the boundary test without printing the product.
Use `1.15 * 100` stored in a variable and set the uncertainty cost to that variable, then to that
variable plus
1. Expect uncertainty, then terrain. That test survives the float.

## When the symptom is the path

The cell list is wrong and the cost is the fixture's cost. You reconstructed a different optimal path.
Check neighbor order and whether you mark closed on push. Marking closed on push freezes the first time
you see a cell, which on this fixture often still looks plausible.

The cell list is the north line for every mode, including shortest. Shortest weights are not zero. Log
alpha at the start of the search.

The cell list crosses `(2, 2)`. The slope test uses `>` instead of `>=`, or the slope in the JSON is 39
because a comma slipped, or you read elevation and called it slope.

Every mode is unreachable on the fixture. Start or goal failed the passable test. Print `slope[2 * width
+ 0]` and the start row. A north-up array puts the start on a 40° cell that you thought was row 2.

Costs are 10 times too big. You charged `cell_size_m` and also multiplied by a second cell size inside
S. S is a ratio of degrees, not meters.

Time is 70 hours. You divided speed by distance. Astronaut speed is 1000 m per hour. 70 m is 0.07 hours.

The real grid's route is a straight line through a cliff. Coverage and slope are the constant fill
values from a failed data build, or you are still loading `corridor.json`. Print `terrain.width`. The
fixture is
6. The crop is hundreds.

Two calls return different cell lists. Something in the search reads `Math.random`, the clock, or a
module-level open set you forgot to reset. The open set, the closed set, the parent table, and the
sequence counter are local variables of one search. Not module globals.

## The order to write it in

Write the heap and its three-number test. Then write `isPassable` and a table-driven test for slope 20
blocked, slope 19.9 allowed, coverage 0 blocked, coverage 1 blocked only for uncertainty with the flag,
elevation −2500 allowed. Then write one search in shortest mode and assert the fixture cell list. Then
turn on terrain weights and assert cost 106. Then uncertainty and assert the nine-cell list and cost
126. Then the recommendation function with the flag off and on. Then the rover numbers. Then climb. Then
the throw on a bad length.

Do not write the React binding. Do not open Leaflet. When the fixture tests are green, send Dhani the
import example and go look at a real grid if it exists. If it does not exist, help the data seat only by
reading a slope histogram they already wrote. Do not start cropping GeoTIFFs. That is how the search
ends up half-tested at midnight.

## Handoff

`handoff/router.md` is short and specific. Use these headings and fill them. Do not write a diary.

```text
Command: cd app && npx vitest run src/router
Node: (what node -v printed)
Result: (pass count, or the first failing test name)
Fixture cells: shortest, terrain, and uncertainty lists copied from the test output
Real grid: not tried, or the four measurements from the section above
Fallback: TypeScript function is the demo path, or Python files were written because ...
Nulls: unreachable routes use null max_slope_deg and empty cells
Known gap: (one sentence, or "none")
```

The integration seat should be able to run the command and trust the fixture without asking you what
"mostly works" means.

## devCheck, the only script besides the tests

`app/src/router/devCheck.ts` is a Node script, run with `npx tsx src/router/devCheck.ts` from `app/`. It
reads `public/terrain.json` if that file exists and prints the four measurements. If the file does not
exist it prints `no terrain.json` and exits 0. It must not fail the Vitest run. It is not imported by
the page.

The script uses `planRoutes`. It does not contain a second search. Pick the south-west cell as column 0,
row 0, and the north-east cell as column `width - 1`, row `height - 1`. If either cell is impassable,
walk inward along the row until you find a passable cell, up to twenty steps, and print the cell you
actually used. If you cannot find one, print `edge blocked` and exit 0. Do not throw. A blocked edge is
a data fact.

Print one line per measurement: `traveler mode flag distance maxSlope fraction status milliseconds`.
That line is what you paste into the handoff. Do not pretty-print the whole RouteSet. It is hundreds of
cells.

## Saturday evening, before you touch the real crop

By the time the data seat has a file, your module is already importable. That means the fixture JSON is
committed, the ten cases pass on your machine, and the handoff command is the command you actually ran.
Send the import snippet to Dhani without waiting to be asked. They can draw the three fixture lines
while the GeoTIFF is still downloading.

If you want a manual picture before the map exists, dump the shortest cells as text in a terminal. Do
not learn a plotting library for this. The map is Dhani's. A wrong picture in a notebook that you then
"fix" by editing cells will not match the tests.

When the real `terrain.json` is valid, run the four measurements and stop changing the search unless a
test fails. A route that looks ugly and passes the legality checks is a result. A route that looks
pretty and steps on a null slope is the bug the whole weekend is trying to avoid.

Keep the weights, the block thresholds, and the 15 percent figure in one object at the top of
`profiles.ts`. The briefing quotes them. If they live as bare numbers inside the loop, the briefing will
drift the first time someone "just tries 5 instead of 4."

## Done

You are done when:

- The ten cases pass on a machine that does not have the GeoTIFF.
- `corridor.json` is in `public/fixtures` and matches the overwrite list. A test loads that file, not
  only an object built in the test, so a bad JSON file fails CI.
- `handoff/router.md` states the command, the Vitest result, the Node version, and whether a real
  `terrain.json` was tried.
- The recommendation on the fixture matches this document for both flag values.
- You have not edited the map or the mesh to make a path look right.

## Do not

- Do not call a model API.
- Do not add diagonal movement.
- Do not treat elevation below zero as missing.
- Do not smooth the path with Chaikin or a spline. The cells are the path. A spline can cross a blocked
  cell that the search refused.
- Do not change alpha, beta, or gamma to make the fixture "look nicer." The fixture was built to
  distinguish the modes. If the real map needs a different weight, write the proposed weight and the
  before/after cell counts in the handoff and wait for the team. Sunday evening is not the time.
- Do not precompute the six demo routes and delete the function. The toggle is the demo.
- Do not read `pois.json` inside `planRoutes`. The caller passes start and goal. The function stays
  pure.

# Dhani — the mission page

You own what a person sees and clicks, except the inside of the WebGL canvas. Ayush returns
routes. The data seat returns a grid and two images. The 3D seat returns a canvas that you
place in a panel. The integration seat writes the science sentences and deploys. You make
those pieces feel like one instrument.

Read plan sections 5, 12, and 14. The route object you draw is plan section 11, and the
cells you will actually see on Saturday afternoon are listed in Ayush's assignment. Draw
those. Do not invent a smoother line.

The page is Vite, React 18, and TypeScript. The map is Leaflet 1.9 with `CRS.Simple`. There
is no Mapbox token, no Google basemap, and no Mars Trek tile layer until the crop image
exists, and even then the Trek tiles are not the basemap. One image, in local meters. If you
have used Leaflet only with OpenStreetMap, the important change is that you must not add a
tile layer.

## What the judge does

Open the page. See the crop, the outpost, three destinations, and a traveler control that
says Astronaut. Click a destination. Three routes appear, or fewer if some modes agree, and
one is marked recommended. The sheet lists distance, climb, descent, maximum slope, planning
time, and the share of the line that is poorly observed. A sentence says why that line was
recommended. Switch to Rover. The lines may change. Turn on Avoid poorly observed ground.
The recommendation may change, or a sentence may say no well-observed route exists. Click a
line. The elevation profile and the 3D view, once it is mounted, follow that line. Click the
ground, not a marker. A readout shows elevation, slope, and coverage for that cell. Open the
briefing. The numbers on it match the sheet. Refresh. The page comes back on the default
destination and recomputes. It does not restore a stale route from a previous grid.

That is the test you run with your hand. A unit test of a pure formatter is useful. A
screenshot is not a test.

## Files you own

```text
app/src/map/**
app/src/sheet/**
app/src/format/**
app/src/App.css          layout and type, not the mesh
app/index.html           title only, if integration has not set it
```

You do not own `src/router/**`, `src/view3d/**`, `data/**`, or the text inside `pois.json`
beyond the fields you need to read. If a destination has no citation, render the name and
leave the science sentence out. Do not write a geology paragraph to fill the hole.

Suggested split, which you may collapse if you prefer fewer files:

```text
src/map/MetersMap.tsx       Leaflet lifecycle
src/map/cellToMeter.ts      the only place that converts cells
src/map/readout.ts          pixel to cell
src/sheet/RouteSheet.tsx
src/sheet/Profile.tsx       elevation sparkline
src/format/routeCopy.ts    sentences and units
src/format/routeCopy.test.ts
```

`App.tsx` is wired by the integration seat. Agree the props early so you are not both
editing it. The props you need are below. If `App.tsx` does not exist yet, build
`MapPage.tsx` that takes those props and let them drop it into the shell later.

## Props and state

```ts
type MapPageProps = {
  terrain: Terrain;
  region: { southWest: [number, number]; northEast: [number, number]; name: string };
  pois: Poi[];
  imageryUrl: string;
  slopeUrl: string;
  selectedRoute: Route | null;
  routeSet: RouteSet | null;
  onSelectGoal: (poi: Poi) => void;
  onSelectRoute: (mode: Mode) => void;
  onTraveler: (t: Traveler) => void;
  onAvoidUncertain: (v: boolean) => void;
};
```

You do not call `planRoutes` inside `MetersMap`. The parent calls it and passes `routeSet`.
That keeps the map testable with a fixed object. You may call `planRoutes` inside `MapPage`
if the parent is not ready. Call it in the parent once the shell exists, so the briefing and
the map share one object and cannot disagree.

Local state that is yours: which layer is showing (`imagery`, `slope`, or `coverage`),
whether the readout is open, and the cell under the cursor. Traveler, destination,
avoid-uncertain, and the selected mode are lifted. If you hide them in the map component,
the briefing will drift.

Default traveler is `astronaut`. Default avoid-uncertain is false. Default destination is
the first POI whose `id` is not `outpost`. Default selected mode is
`routeSet.recommendation` whenever the route set changes. If the user has clicked a
different line, keep their choice until the traveler, the destination, or the flag changes,
and then snap back to the new recommendation. Otherwise the toggle looks broken because the
thick line stays on the old mode.

## The meter plane

Leaflet `CRS.Simple` uses `[y, x]` in `latLng`, and y increases upward in the coordinate
system you define. Set the map so that local east meters are x and local north meters are y.
The image bounds are `[[0, 0], [height_m, width_m]]` in Leaflet's `[y, x]` order, which is
`[north meters, east meters]`. The south-west corner of the image is map point `[0, 0]`. The
north-east corner is `[height_m, width_m]`.

`width_m = terrain.width * terrain.cell_size_m`. `height_m` uses `terrain.height`. For the
fixture that is 60 m by 50 m. For a 400 by 400 grid at 5 m it is 2,000 m by 2,000 m. Fit the
bounds on load. Do not set a zoom that assumes Earth.

Cell center, from plan section 8.2:

```text
x_east = (col + 0.5) * cell_size_m
y_north = (row + 0.5) * cell_size_m
```

A polyline through the route is those points in order. Include every cell. Do not drop
points to "simplify" the line. Simplifying can skip the one cell that makes the detour
obvious.

The inverse, for the readout: a click at `(x_east, y_north)` is

```text
col = floor(x_east / cell_size_m)
row = floor(y_north / cell_size_m)
```

Clamp to the grid. If the click is outside the image, show nothing. Index `i = row * width +
col`. Read elevation, slope, and coverage from the arrays. This is the same index Ayush
uses. Put a test in `cellToMeter.test.ts` that the center of cell `(0, 0)` on the fixture is
`(5, 5)` meters when the cell is 10 m, and that a click at `(5, 5)` returns cell `(0, 0)`.
One off-by-half here shifts every route by half a cell and the 3D line will not match.

`region.southWest` and `region.northEast` are degrees for the briefing and for any label
that prints a coordinate. The map does not use them to place pixels. If you also project
degrees through Web Mercator, you will have two positions for one cell. Do not add a scale
bar in degrees.

## Layers

Three controls, mutually exclusive, named Imagery, Slope, and Coverage. They are buttons,
not a mystery icon. The active one is `aria-pressed`.

Imagery shows `imageryUrl`. Slope shows `slopeUrl`. Both are north-up JPEGs of the same
rectangle, placed on the same bounds. If a URL 404s, show the bounds as an empty pane and a
sentence: "The layer image is missing. The grid is still loaded." Do not remove the routes.

Coverage is not an image. Draw a canvas or an SVG of rectangles, one per cell, or one per
run of identical coverage if you need the speed. Colors, which are also patterned so they
survive a projector:

- Coverage 2: no extra paint. The imagery shows through.
- Coverage 1: diagonal hatch in a rust color, plus the word "coarser" in the legend.
- Coverage 0: a solid dark red at low opacity, legend "no elevation".

The legend is on the map, three rows, always visible when Coverage is selected, and a
one-line reminder when it is not: "Coarse elevation is hatched when the coverage layer is
on."

Slope JPEG coloring is the data seat's. Your legend for that layer says the color is slope,
from low to the astronaut block threshold and above, and that the rover threshold is
different. Do not recolor the JPEG in the browser unless the file they gave you is a
single-channel image you agreed to color. Prefer they export the colored JPEG. You show the
legend they describe in `region.json` if they include `slopeLegend: { min: 0, caution: 12,
block: 20 }`. If the field is absent, use those astronaut numbers and say so in the legend:
"Legend uses the astronaut thresholds."

## Routes

Colors, fixed:

| mode | color | also |
| --- | --- | --- |
| shortest | `#4b5563` slate | label "Shortest" |
| terrain | `#d97706` amber | label "Terrain" |
| uncertainty | `#0f766e` teal | label "Observed" |

The on-map word for the uncertainty mode is "Observed", because "uncertainty" sounds like
the line is the risky one. The sheet's heading can say "Prefers well-observed ground". The
mode key stays `uncertainty`. Do not rename the key.

The recommended line is 5 pixels wide. The others are
2. Selected, if the user clicked a non-recommended line, is 5 pixels and the recommended one
   drops to 3 and keeps a small "recommended" tag at its midpoint. Color is never the only
   signal. Each line has a text label at the middle cell.

If two modes return the same cell list, draw one line and stack the labels: "Shortest and
Terrain agree". Do not offset duplicate lines. The plan forbids the fake corridor.

An unreachable mode is absent from the map and present in the sheet as a row: "Shortest: no
route. The goal cell is at or above the slope limit." Use `blocked_reason`:

| reason | sentence |
| --- | --- |
| slope | The goal cell is at or above the slope limit for this traveler. |
| nodata | The goal cell has no usable elevation. |
| uncertain | The goal cell is only coarsely observed, and that ground is switched off. |
| outside | The start and the goal are not two different cells inside the grid. |

If the goal is fine and the reason is still `slope` or `nodata` or `uncertain`, use a second
sentence: "No path reaches it without crossing blocked ground." You cannot always tell those
apart from the reason code. The goal-impassable case is when the goal cell itself fails. You
can check that yourself with the same rules Ayush published: slope null, coverage 0, slope
at or above the threshold, or coverage 1 when the flag is on and you are explaining the
uncertainty row. Import `TRAVELERS` from the router for the thresholds. Do not copy 20 and
25 into the sheet as unmarked literals. Importing the profiles is allowed. Importing the
search into the formatter is not required.

## The sheet

One column beside the map on a wide screen, above the 3D panel on a narrow screen.
Breakpoint 900 pixels. The map keeps a height of at least 360 pixels. Do not let the sheet
push the map off the top of a laptop.

The sheet title is the destination name. Under it, the traveler and the flag state in plain
words: "Astronaut. Poorly observed ground is allowed." or "Rover. Poorly observed ground is
avoided."

Then three rows. The recommended row has the word Recommended. Each row shows:

- Distance in meters if under 1,000, otherwise kilometers with one decimal.
- Climb and descent in meters, one decimal if the value is not an integer. A climb of 10 is
  "10 m", not "10.0 m".
- Maximum slope in degrees, one decimal, or "not a route" when `max_slope_deg` is null.
- Time from `time_h`. Under one hour, show minutes rounded to the nearest minute, minimum
  "under 1 min" if the rounded value is 0 and the distance is positive. 0.07 hours is 4.2
  minutes, which rounds to 4 min. Say "at the planning speed, not counting stops" once under
  the rows, not in every row.
- Poorly observed share as a percent, integer. 0.5 becomes "50% of the cells are on coarser
  elevation." 0 becomes "All of these cells use the best elevation in the grid."

The comparison sentence is a function in `routeCopy.ts` with tests. Inputs are the route
set. Output is one or two sentences. Rules, in order:

- If the recommendation is null: "No traveler profile reaches this destination under the
  current switch."
- If all three ok routes have the same cell list: "The three modes agree on one line."
- If the recommendation is terrain and the uncertainty route is ok and more expensive: "The
  smoother line is recommended. The line that stays on better-observed ground is {percent}
  longer." Percent is the distance increase relative to the recommended distance, integer.
  On the fixture, terrain is 70 m and uncertainty is 90 m, so the observed line is 29%
  longer. `(90
- 70) / 70 = 0.2857`, which rounds to 29. Assert that.
- If the recommendation is uncertainty: "The recommended line stays on better-observed
  ground. It is the one the avoid switch prefers."
- If the recommendation is shortest because the other two are unreachable: "Only the
  shortest legal line reaches the destination. The other modes found no path."

Keep the function pure. Pass the route set in. No DOM.

Under the sentence, a button row: the three mode names. Clicking selects that route.
Disabled when that mode is unreachable.

## The profile

`Profile.tsx` takes the selected route and the terrain. It draws a sparkline of elevation at
each cell, in order. The horizontal axis is distance along the path, not cell index, even
though those match while steps are one cell. The vertical axis is MOLA elevation, not the
exaggerated 3D height. Label the minimum and maximum. Jezero values are negative. The axis
must show negatives. A library that clips at zero is the wrong library. An inline SVG
polyline is enough.

If the route is unreachable, the profile area says "No elevation profile."

Hovering the profile highlights that cell's dot and tells the map to draw a marker on that
cell. Pass the cell up with `onHoverCell`. This is the check that the sheet and the map
share an index. On the fixture, the steepest cell of the shortest route is one of the 18°
cells. You do not have to label it steep. The max-slope number already does.

## Readout

Clicking the image, and not dragging a route, sets the selected cell. The readout sits at
the bottom of the map:

```text
Cell 2, 1
Elevation -2,512.4 m
Slope 18.0°
Coverage: CTX 20 m, resampled
```

Coverage words:

| value | words |
| --- | --- |
| 2 | HiRISE elevation, resampled |
| 1 | CTX 20 m, resampled |
| 0 | No elevation |

On the fixture every elevation is 0. Show "0 m", not a blank. A null elevation shows "no
elevation" and no slope number.

Do not let this click create a destination. The meeting decided arbitrary goals are out. If
you want the click to feel like it did something, the readout is the something.

## Destination markers

`pois.json` entries have `id`, `name`, `col`, `row`, and optional `caption` and `citation`.
The outpost uses `id: "outpost"` and a square marker. Destinations use a circle. The
selected destination has a heavier stroke. Keyboard: the destination list in the sheet is a
list of buttons, so the map markers are not the only way in. A person who cannot hit a
12-pixel circle can still run the demo.

Names come from the file. If the data seat has not locked names, use the ids. Do not rename
`scarp` to a poem.

## The 3D panel and the briefing

Leave a panel under the sheet with `id="view3d"` and a minimum height of 320 pixels. The 3D
seat mounts into it. You style the frame: a one-line caption "Vertical scale is marked in
the view. Distances in the sheet are not exaggerated." Do not read their camera state. Pass
them the selected route's cells by whatever prop the integration seat connects. If their
canvas is empty, the panel shows "3D view is not mounted." The page is still a valid Level 1
demo if the sheet and the map work. Do not block the map on WebGL.

The briefing is a section you lay out and the integration seat fills. Give it a heading
"Briefing" and a print hint: the browser's print command should show the briefing and the
sheet and may hide the WebGL canvas. A `@media print` rule that hides `#view3d` is yours. Do
not add a PDF dependency.

## Words on the controls

Use these strings. They are boring on purpose. The demo is the line moving, not a mission
patch.

- Page title: `Jezero Walk`
- Traveler group label: `Traveler`
- Buttons: `Astronaut`, `Rover`
- Flag: `Avoid poorly observed ground`
- Layers: `Imagery`, `Slope`, `Coverage`
- Briefing heading: `Briefing`
- Missing grid: `The terrain file did not load. The practice grid is on.`
- Practice banner, when the loaded schema is the fixture or `width < 50`: `Practice grid.
  Not Jezero.`

The practice banner is important. The fixture's wall is a teaching tool. A judge must not
think a 40° bar on a 60 m map is the delta. Show the banner whenever `terrain.width < 50`.

## Loading

`terrain.json` can be a few megabytes. Fetch it once in the parent. While it is in flight,
show the banner "Loading the elevation grid." and do not draw a route from a previous fetch.
If the fetch fails, load `/fixtures/corridor.json` and show the practice banner plus "The
Jezero grid failed to load." Both sentences. A silent fallback is how a team demos the
fixture and calls it the crater.

Validate only what you need: `width`, `height`, and the four arrays' lengths. If they
disagree, do not draw. Show "The terrain file is the wrong shape." and the practice grid if
that one still loads.

## Tests you write

`routeCopy.test.ts`:

- Fixture-shaped route set, recommendation terrain, distances 70 and 90, sentence contains
  "29%" and does not contain "safe".
- All three cell lists equal, sentence contains "agree".
- Recommendation null, sentence contains "No traveler profile".
- Minutes: 0.07 hours formats as "4 min". 0.0001 hours with positive distance formats as
  "under 1 min".
- Distance 70 formats as "70 m". Distance 2,400 formats as "2.4 km".

`cellToMeter.test.ts` for the center and the inverse, including a click one millimeter
inside cell `(1, 0)` returning that cell and not `(0, 0)`.

Do not snapshot the Leaflet DOM. It will change under you and you will bless a blank map.

## Manual pass

Do this on the fixture before you ask for the real grid. Write the result, pass or the first
failure, in `handoff/ui.md`.

1. Load the page. The banner says practice grid. The map is a small rectangle, not a world
   map. There is no attribution tile from OpenStreetMap. If you see countries, `CRS.Simple`
   was not applied.
2. Click the east goal. Three labels appear: Shortest, Terrain, Observed. Shortest crosses
   the lower middle. Terrain crosses the upper middle. Observed runs along the south edge.
   If all three are the same straight line, you are not drawing `cells`, or the router was
   not called.
3. The sheet says Recommended on Terrain. The observed line is described as 29% longer.
4. Max slope on Shortest is 18°. Time is 4 min for a 70 m astronaut walk.
5. Turn the flag on. Recommended moves to Observed. The cell lists do not have to move on
   this fixture. The word Recommended must move.
6. Switch to Rover. The lines stay. The time becomes much longer, because 110 m/h over 70 m
   is about 38 minutes. `70 / 110 * 60 = 38.18`, so "38 min". If the rover time still says 4
   min, you used the astronaut speed.
7. Click Shortest. It becomes the thick line. Recommended tag remains on whichever mode the
   route set names.
8. Click a 40° cell if you can see it, or click the cell the readout says is column 2, row
2. Slope reads 40. Coverage words appear. No new destination appears.
9. Open Coverage. The four upper cells are hatched. The two 40° cells are not hatches unless
   their coverage is
1. On the fixture the 40° cells are coverage
2. They are steep, not coarse. If the hatch follows the wall, you colored slope and called
   it coverage.
10. Narrow the window under 900 pixels. The sheet is still reachable without horizontal
    scrolling the whole page. The map is still visible.
11. Refresh. The banner is back. The default traveler is Astronaut. The flag is off.

## The real grid, when it arrives

Replace the fetch URL. The practice banner must disappear because width will be hundreds.
Confirm one route's midpoint cell, printed from the selected route, is the same cell the 3D
seat prints. One number. If they differ, stop styling and fix the conversion. A beautiful
line in the wrong place is the failure this project is about.

Check that negative elevations print with a minus sign. Check that a route does not leave
the image. If it does, the polyline is in degrees or in pixel indices instead of meters.

Do not add a new layer the data seat did not export. A toggle that draws nothing is a broken
control, and broken controls are what judges click.

## Visual limits

Dark or light is your choice. Pick one and keep the route colors distinguishable on it.
Slate, amber, and teal were chosen because they survive both. If you change them, change the
legend in the same edit and check the pair in grayscale: the labels must still carry the
meaning.

No NASA insignia. No fake oxygen gauge. No ticking clock that implies a life-support model.
No "SAFE" stamp. The strongest word you are allowed on a route is "recommended", and the
sheet shows the number that earned it.

Type is a normal sans. 16 pixels or larger on the sheet numbers. The numbers are the
product.

## The sheet, written out for the fixture

This is the text a correct page shows for the astronaut, flag off, after the east goal is
selected. Use it as a visual diff. Wording may wrap. Numbers may not change.

```text
East
Astronaut. Poorly observed ground is allowed.

Terrain
Recommended
70 m
Climb 0 m, descent 0 m
Maximum slope 3.0°
4 min
50% of the cells are on coarser elevation.

Shortest
70 m
Climb 0 m, descent 0 m
Maximum slope 18.0°
4 min
All of these cells use the best elevation in the grid.

Observed
90 m
Climb 0 m, descent 0 m
Maximum slope 2.0°
5 min
All of these cells use the best elevation in the grid.

The smoother line is recommended. The line that stays on
better-observed ground is 29% longer.

At the planning speed, not counting stops.
```

0.09 hours times 60 is 5.4, which rounds to 5 min. If Observed says 5 min and Shortest says
4 min, the formatter is using `time_h` and not a constant. Rover on the same 70 m line: `70
/ 110 * 60 = 38.18`, shown as 38 min. The 90 m rover line: `90 / 110 * 60 = 49.09`, shown as
49 min. Assert both in `routeCopy.test.ts` so a later edit that special-cases the astronaut
does not survive.

Climb is 0 because the fixture is flat. When you try the negative-elevation scratch grid,
the profile's lowest label is the more negative number, and the sparkline goes down as the
elevation goes down. Flip that SVG and the demo lies about a hill. A one-cell check:
elevations −10 then −8 then −12, the middle vertex is the highest point on the screen even
though the number is still negative.

## Leaflet mistakes that look like a basemap

`CRS.Simple` still wants you to think about `LatLng`. If you write `L.latLng(lat_deg,
lon_deg)` you have put degrees into a meter map. The image will sit in a corner or vanish.
The only `latLng` you create is `L.latLng(y_north, x_east)`.

`fitBounds` on a 60 by 50 map wants a padding of about 16 pixels. A max zoom of 2 will make
the fixture a speck. Set `minZoom` negative, for example −2, or the small fixture cannot be
framed. The real 2 km grid needs to zoom in until one cell is visible as a few pixels, so
`maxZoom` around 2 in CRS.Simple units is usually enough. Tune it on the fixture first: you
should be able to read the route labels without the image becoming a single color.

Image overlay: `L.imageOverlay(url, bounds)`. The bounds are the outer edges, not the
centers of the corner cells. Using cell centers insets the image by half a cell and the
route no longer sits on the pixels you think it does. Half a cell on the fixture is 5 m,
which is obvious. Half a cell on a 5 m grid is 2.5 m, which you will not see until the 3D
line disagrees.

Do not add `L.tileLayer`. If a tutorial paste brought one in, delete it. The attribution
control can stay and should say the dataset name from `terrain.sources[0].title` once that
field exists. On the fixture, attribute "Practice grid".

A route polyline with `smoothFactor` above 0 will move vertices. Set `smoothFactor: 0`.

## Keyboard and the eleven clicks

The traveler control is a radiogroup. The flag is a checkbox. The layer control is a
radiogroup. Destination picks are buttons. A judge who tabs through the page reaches a
destination without aiming at the marker. You do not need a custom focus ring design. You do
need the browser's focus ring not removed by a CSS reset. If `outline: none` is in the
stylesheet, take it out.

The manual pass in the previous section is the script. Add two keyboard steps at the end and
record them in the handoff: tab to Rover and press it, and the time on the 70 m line becomes
38 min; tab to the flag and press it, and Recommended moves to Observed. If those fail, the
controls are click-only and the demo will fail the moment the trackpad does.

## Narrow screen and print

At 390 pixels wide, which is a phone and also a snapped laptop window, the order top to
bottom is: title and practice banner, traveler and flag, destination buttons, map, sheet, 3D
frame, briefing. A person can complete steps 2 through 5 of the manual pass without dragging
horizontally. If the map is 200 pixels tall it is too small. 360 is the floor.

Print preview hides `#view3d` and the layer radio can stay. The sheet numbers must be black
on white in print even if the screen is dark. A `@media print` rule that sets the sheet
color to black is enough. Do not maintain two themes beyond that.

## What you ask the others for

You are allowed to ask for four things, and you should ask for them on Saturday rather than
discovering them in the demo.

From Ayush: the exported `planRoutes`, `TRAVELERS`, and a fixture `RouteSet` you can import.
If the cells do not match the three lists in the plan, you draw them anyway and you say so.
Do not hand-correct a polyline.

From the data seat: `imagery.jpg`, `slope.jpg`, and a `terrain.json` whose width matches the
image aspect. If the image is 800 by 600 and the grid is 400 by 400, stop and make them fix
the export. Do not stretch a wrong image and hope.

From the 3D seat: a component `TerrainView` that accepts `terrain`, `routes`, and
`selectedMode`, or a mount function. Agree the name in `handoff/ui.md` so the integration
seat is not inventing a third wrapper.

From the integration seat: `pois.json` with `outpost` and at least one goal that has `col`
and `row`. You can ship the fixture goals as two buttons, West wall and East side, with ids
`wall` and `east`, pointing at `(2, 2)` and `(5, 2)`. `(2, 2)` is the blocked cell and is
the unreachable demo. Keep that button even after the real POIs arrive, behind the practice
banner only. On the real grid, unreachable has to be a real cliff or you drop the button. Do
not keep a fake "blocked demo" button on the Jezero page.

## Handoff

`handoff/ui.md` headings:

```text
Command: cd app && npm test
Result: (formatter and cell tests)
Manual: eleven steps, pass or the first failure
Keyboard: rover time 38 min, flag moves Recommended
Practice banner: shown under width 50, hidden otherwise
3D frame: present, mounted or not
Known gap:
```

## Done

You are done when the manual pass is green on the fixture, the formatter tests pass, the
practice banner cannot show on a wide grid, unreachable routes produce a sentence rather
than an exception, and `handoff/ui.md` records the command `npm test` plus the eleven manual
steps. The 3D panel may still say it is not mounted. That is not your bug unless the frame
itself is missing.

## Do not

- Do not run a second A* in the click handler.
- Do not smooth the polyline.
- Do not place the image with latitude and longitude inside a default Leaflet map.
- Do not fetch the 1.7 GB TIFF from the browser.
- Do not hide the uncertainty line because it is longer. The longer line is the demo.
- Do not wait for the final rectangle to build the sheet. The fixture has every state you
  need, including agreement, disagreement, a flag that changes the recommendation, a blocked
  cell, and a negative-elevation case you can fake by editing a local copy that you do not
  commit.

# Data — the Jezero grid

You own the elevation. Everyone else's picture is a view of a file you write. If the file
is wrong, the route is wrong and the mesh is wrong, and no amount of interface work will
save the demo. You do not write React and you do not write A*.

Read plan sections 6, 7, and 8 before you download anything. The headers in those sections
were read from the GeoTIFFs on 14 November 2026. Your first job is to recompute the
north-west corner of each file and match those numbers. If they do not match, stop and
find out why. Do not average them away.

The team is on Eduroam and the HiRISE mosaic is 1.71 GB. Start a small CTX crop first so
Ayush has real slopes the same day. Start the HiRISE window after the CTX path works, not
before.

## Files you own

```text
data/build_grid.py
data/check_headers.py
data/README.md
data/raw/                  gitignored
app/public/terrain.json
app/public/region.json
app/public/layers/imagery.jpg
app/public/layers/slope.jpg
handoff/data.md
```

You may read `app/public/fixtures/corridor.json` and you may not edit it. That file is
Ayush's. Your `terrain.json` must use the same schema so his function accepts it without a
branch.

Do not commit anything under `data/raw/`. Do not commit a `.tif`. The JPEGs and the JSON
are the artifacts the site ships. If `terrain.json` is larger than about 8 MB, store the
arrays as base64 float32 in a `.bin` only after you have talked to Dhani. Until then, keep
the crop at 5 m or 20 m so the JSON stays a few megabytes. 400 by 400 floats, four arrays,
as decimal text, is on the order of a few megabytes. That is acceptable.

## The two elevation files

CTX, the one you can finish even if nothing else downloads:

```text
https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif
```

It redirects to the USGS S3 bucket. Size 90,345,300 bytes. 4,456 by 5,067. Float32.
Uncompressed. One row per strip. Pixel 20 m in the projected system. No-data text in the
header `-3.4028234663852886e+38`. Treat any elevation below −1e30 as missing. Do not
compare to that string at runtime.

HiRISE, the one you want:

```text
https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif
```

Size 1,839,545,409 bytes. 21,400 by 21,488. Float32. Uncompressed. One row per strip.
Pixel 1 m in a different projected system. No-data text `-3.40282265508890445e+38`. Same
threshold, −1e30. The strings differ. A shared constant copied from the CTX file will not
match the HiRISE tag, and you do not need it to.

Optional texture, only after elevation works:

```text
https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXortho_mosaic_5m.tif
```

Size 359,599,280 bytes. Its projection was not decoded when the plan was written. Decode
it with the same script before you drape it. If you cannot align it, export a gray JPEG
and say so. A misaligned photo under a correct route is worse than a gray rectangle under
a correct route.

## Prove you understand the headers

`data/check_headers.py` prints the north-west and south-east corners in degrees. It may
use rasterio if rasterio's CRS agrees with the formula. It must also compute the formula
itself and print both. If they differ by more than 0.0001°, trust the formula and write
that in the handoff. Rasterio and PROJ often do not know this user-defined Mars CRS and
will hand you projected meters labeled as if they were degrees.

CTX formula. Radius R = 3,396,190 m. Latitude of true scale φ_ts = 18.4663°. Upper-left
corner, the outer corner of pixel (0, 0), is x = 4,328,999.999999998 m, y =
1,143,420.0000000028 m. Pixel size 20 m. Width 4,456. Height 5,067. Pixel-is-area, so that
corner is the north-west edge, not the center.

```text
lon = x / (R * cos(φ_ts)) in degrees
lat = y / R in degrees
```

Expected north-west: 76.997437° E, 19.290187° N. Expected south-east, after adding width
times 20 m to x and subtracting height times 20 m from y: 78.582563° E, 17.580520° N. The
HTML page swaps the latitude labels. Ignore the HTML if it disagrees.

HiRISE formula. Same radius. φ_ts = 0, so cos is
1. Upper-left x = 4,577,366 m, y = 1,106,618 m. Pixel 1 m. Width 21,400. Height 21,488.

Expected north-west: 77.222933° E, 18.669315° N. Expected south-east: 77.583964° E,
18.306799° N.

Landing check, 18.44° N, 77.45° E, HiRISE pixel-is-area, row 0 at the north:

```text
x = R * lon_radians          because φ_ts is 0
y = R * lat_radians
col = (x - 4577366) / 1
row = (1106618 - y) / 1
```

Expect column about 13,459 and row about 13,593. If you are off by more than two pixels,
the radius or the tiepoint is wrong. Do not proceed to a crop you cannot place the landing
in.

These two x values are not in the same system. CTX uses cos(18.4663°). HiRISE does not.
Overlaying the rasters by their file coordinates shifts the crater. Convert both to
degrees with their own φ_ts, then resample both onto one new grid that is square in ground
meters.

## The rectangle

Provisional, from the plan, to be accepted or moved after you look at a hillshade:

- South-west 77.35° E, 18.42° N.
- North-east 77.39° E, 18.46° N.

It sits inside the HiRISE footprint. It is west of the landing longitude. It is a
candidate. Open the hillshade. If the square is a flat floor with no blocked cells and no
gentle cells, move it so an astronaut threshold of 20° blocks something and also leaves a
corridor. If it is entirely above 20°, move it the other way. Write the final corners into
`region.json` and stop editing them. Tell the team the corners in the handoff. They should
not be in anyone's source code as literals except yours.

Keep the square inside the HiRISE footprint even if you are still on the CTX tier. Then
the upgrade is a resample, not a new map.

## Local metric grid

Pick φ_mid as the latitude halfway between the south and north edges. R = 3,396,190 m.

```text
meters east per degree = R * cos(φ_mid) * π/180
meters north per degree = R * π/180
```

Choose `cell_size_m` 20 while you are on CTX, and 5 when the HiRISE window is in. The
schema allows either. Ayush reads the field. Do not make him guess.

Width in cells is the east-west ground length divided by the cell size, rounded down to an
integer you store. Height the same for north-south. Origin is the south-west corner, outer
edge, in degrees.

For output cell column c, row r, with row 0 at the south:

```text
x_east = (c + 0.5) * cell_size_m
y_north = (r + 0.5) * cell_size_m
lon = lon_sw + x_east / meters_east_per_degree
lat = lat_sw + y_north / meters_north_per_degree
```

Sample the source elevation at that lon/lat by converting lon/lat back into the source
file's x and y with that file's own φ_ts, then into a source pixel. Bilinear sample. If
any contributing source pixel is no-data, the output cell is null. Do not bilinear-blend a
sentinel of −3e38 into a real slope. That creates a crater the size of a country at the
edge of a gap.

GeoTIFF row 0 is north. Your row 0 is south. The flip happens here, in the sampler,
exactly once. After this, nobody flips.

## Slope

Horn's method on the metric grid, after the resample. Cell size is `cell_size_m` in both
directions because you made the grid square in ground meters.

Label the 3 by 3 window with north at the high row index, because row increases north:

```text
a b c     <- row+1
d e f     <- row
g h i     <- row-1
```

`e` is the cell you are computing.

```text
dz/dx = ((c + 2f + i) - (a + 2d + g)) / (8 * cell_size_m)
dz/dy = ((a + 2b + c) - (g + 2h + i)) / (8 * cell_size_m)
slope_deg = atan(sqrt(dz/dx^2 + dz/dy^2)) * 180/π
```

Check the sign of `dz/dy` against a ramp before you trust a picture. Build a 5 by 5 grid
in the test, cell 10 m, elevation equal to `10 * row`. Ground rises 10 m per cell toward
the north, so the slope is 45°. Interior cell `(2, 2)` must be within 0.1° of 45. A sign
error in `dz/dy` still gives 45° because of the square. So also assert a pure east ramp,
elevation `10 * col`, is 45°, and assert a flat grid is 0. The test that catches a swapped
axis is a ramp that rises only toward the north-east: both partial derivatives non-zero,
slope near `atan(sqrt(2))` which is about 54.7° for a 10 m rise per 10 m in both axes.
Assert that.

Edge cells and any cell with a null neighbor in the 3 by 3 are null slope. Do not fill
them with zero. Zero is a parking lot. Null is "do not walk."

Roughness is the standard deviation of the elevations in the window that are not null. If
fewer than 6 of the 9 are present, roughness is null and slope is null. Use the population
or the sample standard deviation, pick one, write which in `region.json` as `roughness:
"population"` or `"sample"`, and do not switch. The router saturates roughness at 1 m. A
0.2 m difference in definition will not move a route. An accidental roughness in degrees
will.

## Coverage

On a CTX-only build, every cell with a real elevation gets coverage
1. Cells with null elevation get coverage 0.

On a HiRISE build, cells whose sample came from the HiRISE file get coverage
2. If you fill gaps with CTX, those gap cells are coverage 1, not
2. If you leave gaps null, coverage is 0. Do not fill gaps and then mark them as HiRISE.
   The uncertainty mode is the entire point of the second number.

Write `region.json` like this:

```json
{
  "schema": "jezero-walk.region.v1",
  "name": "Jezero candidate",
  "tier": 1,
  "southWest": [77.35, 18.42],
  "northEast": [77.39, 18.46],
  "cell_size_m": 20,
  "coverage2_fraction": 0,
  "elevation_min_m": -2600,
  "elevation_max_m": -2400,
  "notes": "CTX 20 m only. HiRISE window not in this file."
}
```

`southWest` is `[lon, lat]`. Tier 1 means CTX. Tier 2 means HiRISE elevation is actually
in the arrays. `coverage2_fraction` is the share of cells with coverage
2. If you claim tier 2 and the fraction is 0, the check script fails.

`elevation_min_m` inside the crop should be greater than −10,000 and less than −1,000 if
the sentinel was stripped. Jezero's floor is around −2,500 m. If your minimum is −3e38,
you exported no-data as elevation. If your minimum is 0, you shifted the values and the
briefing will not match MOLA. Do not shift. The mesh shifts for display. You store real
meters.

## Images

`imagery.jpg` is north-up, covering the same outer edges as the grid. It can be the CTX
ortho window, contrast-stretched for a screen, or a hillshade you compute from the
elevation. A hillshade is allowed as the imagery layer when the ortho is not ready. Say
which, in `region.json` `imagery: "hillshade"` or `"ctx-ortho"`.

Hillshade is a picture. It is not a second elevation. Do not feed it back into slope.

`slope.jpg` is north-up. Color the finite slopes. Paint null slope as a distinct dark
color, not as 0°. Include a legend strip on the left or document the ramp in
`region.json`. A simple ramp is enough: 0° dark blue, 12° yellow, 20° orange, 25° and
above red. Those breaks match the astronaut caution, the astronaut block, and the rover
block. They are legend breaks, not a recompute of the route.

Both JPEGs should be a few hundred kilobytes, not the GeoTIFF. 1,200 pixels on the long
side is plenty for a 2 km map on a laptop.

## build_grid.py

One command, from the repository root:

```text
python3 data/build_grid.py --tier 1 --sw 77.35 18.42 --ne 77.39 18.46 --cell 20
```

Tier 2:

```text
python3 data/build_grid.py --tier 2 --sw 77.35 18.42 --ne 77.39 18.46 --cell 5
```

The script reads `data/raw/` if the files are there, otherwise it may read `/vsicurl/` or
the HTTPS URL. It writes the three public files and prints the corner check, the min and
max elevation, the coverage counts, and the output paths. It exits non-zero if the corner
check against a stored constant fails, if the elevation minimum is below −1e30, or if the
array lengths do not match `width * height`.

Idempotent: running it twice overwrites the outputs and does not append. No network call
on the second run if `data/raw` is populated.

Dependencies, pinned in `data/requirements.txt` after you know they import: `numpy`,
`rasterio`, `pillow`. Python 3.11. If rasterio will not install on a teammate's laptop,
you are the person with the working environment. They do not need rasterio. They need your
JSON.

If rasterio cannot read the URL, download the CTX file. It is 86 MB. For HiRISE, do not
download 1.71 GB unless a windowed read has failed. The file is one uncompressed strip per
row, 21,400 samples of 4 bytes, about 85,600 bytes per row. A 2 km window is 2,000 rows
and about 170 MB because each strip is full width. A 1 km window is about 85 MB. Request
the row ranges you need. Document the byte offset if you write that reader: the strip
offsets are in the TIFF tag, not at a fixed stride, because the header and the IFD take
space before the pixels. Use the `StripOffsets` array. Do not assume pixel 0 starts at
byte 0. It does not.

## What good output looks like

After a tier 1 run, `check` prints something with these properties, your numbers will
differ once the rectangle moves:

- North-west of the source file matches the plan to 0.0001°.
- Crop corners are the ones you passed on the command line.
- `width` and `height` are near 100 if the cell is 20 m and the box is about 2 km. Compute
  the expected count from the meters-per-degree and put it in the handoff before you look
  at the script's answer, so you are checking the script rather than trusting it.
- Elevation minimum and maximum are both negative and separated by more than a few meters.
  A completely flat crop means you sampled one pixel, or you sampled the no-data fill and
  clamped it.
- Coverage 2 fraction is 0 on tier 1, and the notes say so.
- `python3 -c` import of the JSON: arrays have length `width * height`, and `slope_deg` is
  null wherever `elevation_m` is null.

Hand the file to Ayush by path. Do not paste it into chat.

## The move

You will want to move the rectangle after the first picture. Do it once, on Saturday, with
the hillshade open. Criteria:

- The outpost cell you will recommend is coverage not 0, slope under 12°, so the start is
  not already blocked for an astronaut.
- At least one destination cell is also gentle.
- At least one other destination is reachable only by going near slopes above 12°, so the
  terrain mode has something to do.
- The straight line between outpost and one destination crosses either a steep cell or a
  coverage change, so the three modes are not identical. If every route will be the same,
  slide the square. If you cannot find such a square inside the footprint, say so.
  Identical modes on honest ground are allowed. Pretending a difference is not.

Record the outpost and destination cells as `col` and `row` in a note the integration seat
copies into `pois.json`. You compute the cells. They write the names and the citations. Do
not invent the geology.

Places you may look up, and only use if the coordinate you found has a citation you can
paste:

- Octavia E. Butler Landing, 18.44° N, 77.45° E. It may fall outside your 2 km square.
  That is fine. It can be named in the briefing as context without being a marker.
- The western fan and the delta scarp, by looking at the hillshade, not by memory.
- Séítah and Kodiak, only with a source. Kodiak is described as on the order of a few
  kilometers from the landing site. Measure. If it is outside the square, leave it
  outside.

## README

`data/README.md` is the command, the expected corner numbers, the raw-file names, and the
sentence "do not commit data/raw". A teammate who was not in the room should be able to
rebuild `terrain.json` from that page and the downloads. Pin the Python version you used.

## Handoff

```text
Tier shipped: 1 or 2
Command:
Corner check: pass or the delta you saw
Elevation min/max:
Coverage counts:
Cell size and width/height:
Outpost cell and destination cells, if chosen:
Imagery is: hillshade or ctx-ortho
Known gap:
```

## Numbers to compute before you trust the script

The provisional box is 0.04° on a side. At 18.44° N and R = 3,396,190 m, a degree of
latitude is about 59.3 km and a degree of longitude is about 56.2 km. The box is therefore
about 2.2 km east-west and 2.4 km north-south. At 20 m cells, expect on the order of 110
by 120 cells, not 400 and not 4,000. At 5 m cells, expect on the order of 450 by 470.
Write your own exact count in the handoff before you open the JSON. If the script prints
4,456, it exported the whole CTX file and ignored the crop. If it prints 6 by 5, it wrote
the fixture.

Landing 18.44° N, 77.45° E is east of this box (the box ends at 77.39° E). It should not
appear as a cell. If your sampler returns a cell for it, the crop bounds were not applied.
That is a useful negative test. Run it.

A cell on the south-west corner, column 0, row 0, has its center half a cell inside the
corner. Its longitude is not exactly 77.35. It is 77.35 plus half a cell of degrees. Do
not "snap" the center back onto the corner. Dhani's image uses the outer edges. The
centers are for the route.

## Sampler, function by function

Keep the script boring. Four functions are enough.

`load_source(path)` returns width, height, tiepoint, pixel scale, φ_ts, radius, and a way
to read a window. Print those and compare to the plan before any math. A function that
silently substitutes φ_ts = 0 for the CTX file will shift the crop by kilometers. The CTX
value is 18.4663. Assert it.

`lonlat_to_pixel(lon, lat, source)` applies that source's formula and returns a fractional
column and row. Row 0 is north inside this function, because that is the file. The flip to
south-first happens when you store the output, not inside this conversion.

`sample(lon, lat, source)` reads the four surrounding pixels for a bilinear sample. If any
of the four is below −1e30, return null. If the fractional pixel is outside the file,
return null. Do not clamp to the edge. Clamping paints the border pixel across the whole
outside world and invents a plateau.

`write_grid(...)` fills elevation, then slope, then roughness, then coverage, then the
JPEGs, then the JSON. If slope throws, do not write a half JSON that the app will load.
Write to a temporary file and rename it. A reader that catches the file mid-write will
fail the length check and fall back to the fixture, and you will think the app is ignoring
you.

## A hand sample, one pixel

Pick the CTX north-west corner pixel center, not the outer corner. Pixel-is-area means
pixel (0, 0) covers x from the tiepoint to the tiepoint plus 20 m, and y from the tiepoint
down to the tiepoint minus 20 m. The center is 10 m east and 10 m south of the tiepoint.
Convert that center to degrees with the CTX formula and write it in the handoff as "pixel
0,0 center". Then ask `sample` for that lon/lat and expect a column and row within half a
pixel of (0, 0). This is the round trip. If it lands on pixel (200, 200), φ_ts was applied
twice or not at all.

Do the same for the HiRISE tiepoint before you trust a window. One round trip each. It
takes minutes and it saves the evening.

## Hillshade, only as a picture

If the ortho is not ready, build the imagery JPEG from the grid you already have. A
standard hillshade is enough:

```text
azimuth 315°, altitude 45°
slope and aspect from the same dz/dx and dz/dy you used for slope_deg
```

You do not need a named library. The usual formula shades a surface lit from the
north-west. Null cells are the same dark color as null slope. Do not paint them white.
White reads as a highlight, which reads as a ridge.

Stretch the gray values to the middle 98 percent of the finite cells so one cliff does not
turn the floor black. Record the stretch in the README in one sentence. The stretch is
display. It is not a change to `elevation_m`.

## What the app will do to your file

Dhani fetches `/terrain.json` once. Ayush refuses to run if the array lengths differ. The
mesh skips null slopes. So a file can be "valid JSON" and still be useless. Before you
call it done, run this in the same Python and paste the printed lines into the handoff:

- finite elevation count, null elevation count
- finite slope count, which must be less than or equal to the finite elevation count
- count of cells with slope >= 20 and slope >= 25
- count of coverage 0, 1, and 2
- the column and row of the minimum elevation and of the maximum elevation

If the slope-at-least-20 count is zero, say so. The terrain mode will then match the
shortest mode almost everywhere, and the team should know that before they demo a
difference they do not have. If that count is nearly all the cells, the rectangle is a
cliff and the astronaut search will be unreachable. Move the rectangle.

## HiRISE, the practical version

Try a windowed read of 200 rows before you try 2,000. Two hundred rows at full strip width
is about 17 MB. If that succeeds, the 2 km read is the same code and more time. If the
server resets the connection, retry the same range once. If it fails again, stay on tier 1
for the submission and keep the HiRISE job in the README as the next step. Do not promise
tier 2 on the project page because a download was "almost done."

When the window is in, sample it with its own φ_ts of 0. Then set coverage to 2 only where
that sample was finite. Where it was null and CTX is finite, coverage is 1 and the
elevation is the CTX sample. Where both are null, elevation is null and coverage is 0.
Write those three counts. A tier 2 file with zero coverage-2 cells is a bug in the mask,
and the check script should exit non-zero.

Seams between HiRISE strips exist in the real mosaic. A one-pixel step of a meter or two
is acceptable. A step of hundreds of meters means you sampled across the no-data gap and
blended the sentinel, or you mixed the two projections. Look at the elevation profile
along one row in the center of the crop. It should wander by meters to tens of meters, not
jump by a kilometer. If it jumps, do not smooth it. Fix the sample.

## README, the short version a teammate can run

Include the two commands, the corner numbers, the Python version, and this warning in your
own words if you want, but with these facts: raw tifs stay in `data/raw`, the public files
are the JSON and two JPEGs, row 0 of the arrays is south, row 0 of the JPEGs is north. A
person who flips one of those without flipping the other will draw every route upside down
and the tests on the fixture will still pass, because the fixture has no image. Your
README is the only place that fact is operational.

## Handoff

The headings from the earlier section, plus:

```text
Round trip pixel 0,0: pass or the error in pixels
Cells wide, cells tall, and the count you predicted:
Slope >= 20: count
Slope >= 25: count
Center-row elevation jump: none, or the size of the jump
```

## Done

You are done when `check_headers.py` matches the plan's corners, `build_grid.py` writes a
grid whose minimum elevation is a real Jezero number, slope on the synthetic ramp tests is
45° and about 54.7° on the diagonal ramp, null elevation never has a numeric slope, and
the two JPEGs cover the same rectangle as the grid. Tier 2 is better. Tier 1 with the
notes filled in is a finished data job if the HiRISE window did not arrive. Do not block
the demo on tier 2 past Sunday morning.

## Do not

- Do not blend the Caltech Murray Lab DEM with the USGS HiRISE mosaic. One elevation
  source per cell.
- Do not use MOLA as the route grid. Hundreds of meters per posting cannot see this walk.
- Do not store the no-data sentinel as a number in the JSON.
- Do not flip the rows in the JSON and also flip them in the JPEG. Pick north-up for
  images and south-to-north for arrays, as the plan says, and document it in the README in
  one sentence.
- Do not "correct" a route you dislike by editing elevation cells by hand. If a cell is
  wrong, fix the sampler and rebuild.

# 3D — the surface

You own the mesh and the camera. The elevation comes from `terrain.json`. The
line comes from the route's `cells`. You do not resample the GeoTIFF and you
do not search for a path. If the surface and the map disagree, one of you
converted a cell differently, and the conversion in plan section 8.2 wins.

The meeting wanted to walk around in a headset. The plan cuts that back. The
whole crop is visible on a laptop. A viewpoint looks around and does not move
the feet. A headset is a button on that same camera, and only after the laptop
view is already right.

React Three Fiber is allowed if you already know it. Plain Three.js in a
`useEffect` is also fine. Do not start a Unity project. Do not start Unreal.
The page has to be the same origin as Dhani's map, on a static host, by
Sunday.

## Files you own

```text
app/src/view3d/TerrainView.tsx
app/src/view3d/mesh.ts
app/src/view3d/routeLine.ts
app/src/view3d/viewpoints.ts
app/src/view3d/mesh.test.ts
handoff/view3d.md
```

`TerrainView` accepts:

```ts
type TerrainViewProps = {
  terrain: Terrain;
  routes: Route[];
  selectedMode: Mode | null;
  exaggeration: number;
  viewpointId: string | null;
};
```

Dhani leaves a panel. You fill it. If their panel is not ready, render
`TerrainView` on a route by itself so you can develop. Do not fork the route
data to do that. Import the fixture and call `planRoutes`, or import a saved
`RouteSet` JSON that Ayush's test already checks. A hand-built list of points
will not catch a bad index.

## Coordinates

X is east meters from the south-west corner. Y is up. Z is north meters from
the south-west corner. Three.js's default camera looks down −Z, which is fine
once you place the camera to the south and looking north, or you orbit. Do not
use a right-handed "Z up" frame and also a Y-up frame in the same scene.

Cell `(col, row)` center:

```text
x = (col + 0.5) * cell_size_m
z = (row + 0.5) * cell_size_m
```

Y is not the MOLA value. Jezero sits near −2,500 m, and the relief across the
crop may be only tens of meters, which is invisible at 1:1 next to a 2 km
square.

```text
Y = (elevation_m - elevation_min) * exaggeration
```

`elevation_min` is the minimum finite elevation in this grid, computed once
when the mesh builds. Default `exaggeration` is
3. The view prints `Vertical scale 3×` in a DOM label, not in the WebGL scene,
   so it stays sharp. Changing the control to 1 and to 5 rebuilds Y and does
   not rebuild the route's horizontal shape. Distances Dhani shows must not
   change when you touch this control. If they do, someone multiplied a
   distance by the exaggeration. That bug is yours only if you exported a
   length. Do not export a length.

A null elevation does not become Y = 0. Y = 0 is the floor of the crop, and a
null cell dropped to the floor looks like a pit the depth of the datums you
just removed. Skip the triangles that touch a null cell. A hole is the honest
picture. If the hole is huge, that is the data, and the data seat needs to see
it. Send them a screenshot of the hole before you fill it.

## The mesh

One vertex per cell that has a finite elevation and a finite slope. Cells with
null slope are the edge and the no-data mask. Skip those too, so the router
and the mesh refuse the same places. A cell the astronaut cannot step on
because it is steep is still drawn. Steep is visible. Missing is a hole. Do
not paint steep cells as holes.

Triangles: for each cell `(c, r)` that is drawn, and its east neighbor and its
north neighbor, emit two triangles when all three or all four corners exist.
Using cell centers as vertices means the surface passes through the samples
the route uses. Using cell corners requires you to invent elevations you do
not have. Use centers.

`mesh.test.ts` does not need WebGL. `buildPositions(terrain, exaggeration)`
returns a float array and a map from `(col, row)` to the vertex index, or −1
if skipped.

Tests:

- Fixture cell `(0, 0)`, elevation 0, exaggeration 3, minimum elevation 0.
  Position x = 5, y = 0, z = 5 when the cell is 10 m. The fixture origin of
  the mesh is the corner, and the cell size is 10.
- A grid with elevations −2500 and −2490, exaggeration
3. The higher MOLA value is 30 m higher in Y, not 2,490 m higher. Both Y
   values are non-negative.
- A null cell is absent from the index map. Its neighbors do not reference it.
- Vertex count equals the number of finite-slope cells.

Run that test without a GPU. A screenshot is extra.

## Color

Vertex color or a single texture. Prefer the imagery JPEG as a texture if the
UV is right. UV for a north-up image:

```text
u = (col + 0.5) / width
v = (row + 0.5) / height
```

Three.js textures have v = 0 at the bottom of the image in the usual setup,
and a north-up JPEG has row 0 of the file at the top. Your grid's row 0 is the
south, which is the bottom of a north-up image. So `v = (row + 0.5) / height`
matches a texture whose v increases toward the top of the image only if you
set `texture.flipY` consistently and then look. The test is visual and simple:
the north edge of the mesh shows the north edge of the JPEG. Put a one-pixel
red line on a throwaway JPEG, run it, and record which edge lit up. Do not
ship the red line.

If the JPEG is missing, color vertices by slope: low slopes in the same slate
family as the map, slopes at or above 20° in the red family. Use the astronaut
threshold from `TRAVELERS` if importing the router does not create a cycle. If
it does, duplicate the number 20 in the view and add a one-line comment that
the sheet owns the real legend. Prefer the import.

No photo-realistic rock texture tiled across the surface. A tiled rock says
there is a stone at a coordinate. There is not. The pixels are the
measurement.

## The route

`routeLine.ts` builds a line from the selected route's cells. Each point uses
the same x, z as the mesh vertex, and Y plus one meter times the exaggeration,
so `Y + 1 * exaggeration`. One meter of clearance before exaggeration becomes
three meters on screen at 3×, which is enough to stop z-fighting and small
enough to look like it sits on the ground. Use the mesh's vertex position when
the cell has a vertex. If the route contains a cell you skipped, do not invent
a point at Y = 0. Break the line. A route through a hole is a bug in the
router or in the mask. Show the break. Do not paper over it.

Draw the selected mode only, in the same color Dhani uses: slate `#4b5563`,
amber `#d97706`, teal `#0f766e`. A second faint line for the other modes is
allowed if it does not hide the selected one. Same colors. No offset. If two
modes share cells, one line.

`linewidth` on a WebGL line is unreliable. A `THREE.Line` is acceptable for
the demo. A tube is prettier and costs an evening. Ship the line first.

## Cameras

Default camera: orbit the crop. The target is the center of the mesh in x and
z, and the mean Y. Distance is about 1.5 times the crop width. A person can
drag to rotate and scroll to zoom. They cannot fly through the ground. Clamp
the polar angle so the camera does not go under the mesh.

Viewpoints come from `pois.json` entries that include `heading_deg` and
`eye_height_m`. The integration seat writes them. If the fields are missing,
you do not invent six scenic spots. You keep the orbit camera and you say the
viewpoints are not in the file.

When a viewpoint is selected:

- Position: the cell's x and z, and Y of that cell plus `eye_height_m *
  exaggeration`. Eye height is 1.7 m in real meters. On a 3× mesh that is 5.1
  m of scene Y. If you add 1.7 without the exaggeration, the camera is buried
  in the exaggerated surface.
- Look direction: `heading_deg` clockwise from north. North is +Z. East is +X.
  Heading 0 looks toward +Z. Heading 90 looks toward +X.

```text
lookX = sin(heading)
lookZ = cos(heading)
```

Pitch starts at −10° so the person sees ground rather than sky. Drag changes
yaw and pitch. It does not change position. Pitch clamps between −80° and
+40°. Yaw is unlimited. This is the "look around, do not walk" rule from the
meeting.

Switching back to orbit restores the orbit camera. Do not leave the user stuck
at a viewpoint with no way out. A button, "Back to overview", is enough.

At most six viewpoint buttons. They are the POI names. You do not render a
button for a POI that has no finite elevation.

## The fixture, so you can see a wall tonight

Load `corridor.json`. Elevations are 0, so the mesh is flat even at the 40°
cells. That is correct and it is a bad preview of a hill. For your own
eyeball, build a scratch terrain in the test folder that copies the fixture
slopes into elevation: elevation equals slope, so the 40° cells become a wall
40 m tall before exaggeration. Do not commit that as `terrain.json`. A
`devWall` flag in `TerrainView` is allowed only when `import.meta.env.DEV` is
true, and it must refuse to build in production. The production mesh uses
`elevation_m` only.

On that scratch wall you should see two tall cells and a route that goes
around them. If the route climbs the wall, you are reading slope as a path, or
the route cells include `(2, 2)`. Take that to Ayush with the cell list. Do
not lower the wall.

## Light and the ground

One directional light and a dim ambient light. No shadow map unless it is
free. No starfield that includes a logo. The clear color is a dark dust color,
not pure black and not NASA blue. Background `#1c1917` works with Dhani's
amber line. If their page is light, set the clear color to match the panel so
the canvas is not a black hole. Ask them which. One message, then decide.

Axes helper is on in dev and off in production. A visible RGB axis in the demo
reads as unfinished.

## Headset

A button, "Look around in a headset", rendered only when `'xr' in navigator`.
On click, request an immersive VR session with the local camera at the current
viewpoint, or at the orbit camera if no viewpoint is selected. The person
looks by moving their head. You do not implement teleport, controllers, or a
hand menu.

If the session fails, leave the desktop view as it was and show "This browser
did not start a headset session." Do not retry in a loop.

This button is optional. Hide it until the orbit view and one viewpoint work
on the desktop. Sunday after 18:00 Europe/Rome, do not start debugging the
headset. The plan is explicit.

Quest's browser can open the Vercel URL. It will not open `localhost` on your
laptop without a tunnel. A tunnel is not a Sunday task. If the desktop view is
right, the submission does not need the headset.

## Performance

A 400 by 400 mesh is 160,000 vertices. That is comfortable. Do not add a
subdivision pass that turns each cell into ten. The data is not finer than the
cell, and subdivision implies a measurement you did not make.

Compute the geometry when `terrain` or `exaggeration` changes, not on every
camera move. Store it. Rebuilding 160,000 vertices on a mousemove will drop
frames and will not change the shape.

## What you print when something is wrong

In dev, a corner overlay with the selected mode, the cell count of the line,
and the first and last cell. That overlay is how you and Dhani compare
indexes. It can stay in the production view if it is one quiet line: `Terrain
· 70 m line · vertical scale 3×`. The distance in that line is the route's
`distance_m`, read from the route object, not measured off the mesh. If you
measure off the mesh you will include the exaggeration or the clearance and
the two numbers will diverge.

## Handoff

```text
Command: cd app && npm test -- src/view3d
Result:
Orbit: works on the fixture or the scratch wall
Viewpoint: works, or pois lack heading_deg
Headset: not started, or started and the result
Vertical scale label: present
Null cells: become holes
Known gap:
```

## Build order

Create `buildPositions` and the four tests before you open a canvas. A green
test with a wrong camera is an hour. A pretty camera on a north-up flip is a
day, because everyone will "fix" it in a different file.

Then one scene: a mesh from the fixture, flat, orbit camera, no route. You
should see a small sheet. If you see nothing, the camera is inside the mesh or
looking the wrong way. Put the camera at `(width_m / 2, 80, -40)` looking at
the center before you install orbit controls. A known camera removes one
variable.

Then the route line from a real `planRoutes` result on the fixture. The line
has corners. If it is a single diagonal, you used the start and the goal and
ignored the cells in between.

Then exaggeration on a scratch grid that is not flat. The label changes when
the control changes. The sheet's distance, which you can log, does not.

Then one viewpoint. Then the hole for nulls. Then, if the real grid exists,
throw the fixture away and do not look back except for the tests.

## Cleanup

A Vite hot reload will mount the scene twice if you do not dispose it. On
unmount, cancel the animation frame, dispose the geometry, dispose the
material, and dispose the renderer. A leaked renderer is why the laptop fans
spin after ten edits and the demo tab dies. This is part of the job, not a
polish pass.

Do not create the renderer in the render body of a React component. Create it
once, when the container div is available. Dependencies of that effect are the
container, not the route. Route changes update the line geometry only.

## The viewpoint, in numbers

Cell size 5 m, cell `(10, 20)`, exaggeration 3, elevation −2,510, elevation
minimum −2,540. Scene position of the ground:

```text
x = 10.5 * 5 = 52.5
z = 20.5 * 5 = 102.5
Y = (-2510 - -2540) * 3 = 90
```

Eye height 1.7 m becomes `1.7 * 3 = 5.1` added to Y. Camera Y is 95.1. Heading
90 looks east: the look direction is `(1, 0, 0)` plus the −10° pitch, so a
small downward component. You do not need to assert the pitch vector in the
unit test. Assert the ground position and that the camera Y equals ground Y
plus `eye_height_m * exaggeration`. A test with these numbers takes ten lines
and catches the buried-camera bug before you put a headset on.

## Manual look

On the scratch wall:

- The two tall cells are near the middle, not on the south edge. If they are
  on the south edge, row 0 was treated as north.
- The terrain route goes through the low side of the wall, the uncertainty
  route along the opposite edge. You need Ayush's function for this. If you
  draw a straight line, say so in the handoff. Do not approximate.
- Zoom until one cell is a large part of the view. The line still passes
  through the cell centers, not between them.
- Set exaggeration to
1. The wall gets shorter. Set it to
5. The wall gets taller. The line's horizontal corners do not move.
- Toggle a null cell by editing a throwaway copy. A hole appears. The line
  stops at the hole if the route included that cell, or the line simply avoids
  it if the route did. Neither result may show a spike to Y = 0.

On the real grid, when it exists:

- The surface is not a bowl the size of the datum. If the whole mesh sits in a
  pit relative to a zero plane you accidentally added, you used raw MOLA as Y.
- Relief is visible at 3× and subtle at 1×. If it is invisible at 5×, the crop
  is flat or the elevations were replaced with zeros.
- The north edge of the texture matches the north edge of Dhani's image. Stand
  next to each other and look at one distinctive blotch.

## Colors and the line, again, because this is where demos lie

Use the hex values from Dhani's assignment. If their assignment and a
screenshot disagree, use the assignment until they change it in the file you
both import. A shared `colors.ts` is a good gift. You may create it under
`src/view3d/colors.ts` and let Dhani import it, or the other way around. One
file. Two copies of the hex will diverge on Saturday night.

The line's clearance is vertical, in scene units, `exaggeration * 1`. It is
not a second path. It does not move the cell sideways. A sideways move to "see
the line better" is the offset the plan forbids.

## If the real mesh is too heavy

400 by 400 is not too heavy. If a laptop stutters, you are rebuilding the
geometry every frame or you have a shadow map on a large receiver. Remove
those. Do not decimate the mesh. Decimation moves the surface off the samples
and the route no longer sits on a vertex you can name.

## Handoff

Add to the headings already listed:

```text
Camera on first load: a known position, or orbit controls
Dispose on unmount: yes or not yet
Scratch wall: the tall cells sit on row 2, or what you saw
Shared colors file: path
```

## Done

You are done when the mesh tests pass, the route sits on the surface and
breaks at a hole instead of diving to zero, the vertical scale is printed,
exaggeration does not change any number in the sheet, and a viewpoint looks
but does not translate. The headset is extra. A gray mesh with a correct amber
line is a finished 3D job. A pretty rock texture on the wrong coordinates is
not.

## Do not

- Do not download a Mars terrain model from a marketplace.
- Do not drop the rover or an astronaut mesh onto the surface and call it a
  measurement. If you add one as a scale figure at the viewpoint, the caption
  in the DOM says "Figure for scale, not a mapped object."
- Do not recompute slope from the mesh to color it differently from
  `slope_deg`. Use the array.
- Do not flip row here. The data seat already defined row 0 as south. If the
  north edge is wrong, fix it with them once, in the data build, not with a
  minus sign that only the mesh knows about.
## The controls, named

The buttons are text, not icons. Use these labels so the video and the sheet
use the same words.

- `1×`, `3×`, `5×` for the vertical scale. The visible sentence is `Vertical
  scale 3×` and the digit changes with the button.
- `Back to overview` leaves a viewpoint and restores orbit.
- Viewpoint buttons use the POI `name` field, not the id. An id like
  `scarp-look` is for the code.
- `Look around in a headset` is the only VR string. It is absent when
  `navigator.xr` is missing.

Put the scale buttons outside the canvas, in the panel chrome, so a screen
recording reads them at 720p. Text drawn inside WebGL becomes mush in a
30-second video.

## A lost click

Orbit controls and a click-to-readout will fight if both listen to the
pointer. You do not own the readout. Dhani does. Do not add a second click
handler that sets a destination. If you want a hover cell for yourself while
debugging, print it in the dev overlay and remove the print before you hand
the view over. A click inside the canvas that changes `goalId` is a bug even
if it feels helpful.

Dragging the mouse rotates. Scrolling zooms. The middle of the crop stays in
frame. If a drag also pans the target into a corner and the mesh disappears,
set the orbit target once, to the center, and turn panning off. Panning is how
a demo gets lost on a blank clear color.

## Memory

Call `geometry.dispose()` and `material.dispose()` when exaggeration changes
and you build a new geometry. Assign the new geometry and dispose the old one.
Do not keep both. A 400 by 400 grid is about 160,000 vertices. Rebuilding ten
times without disposing is enough to make a laptop tab reload in the middle of
a take.

The texture, if you load the JPEG, is disposed with the material. A new JPEG
URL means a new texture. The fixture has no JPEG. Do not throw if `imageryUrl`
is missing. Color by slope instead, and leave the DOM label as it is.

## What you say if the surface looks wrong

Use these sentences in the handoff so the data seat knows which bug you are
reporting. Do not say "the 3D is broken."

- "The north edge of the mesh does not match the north edge of the JPEG." That
  is a flip. Fix it once, in the data build, if the arrays and the image
  disagree. Fix it in the UV only if the arrays are already south-first and
  the image is north-up and your v coordinate is the thing that is wrong.
- "A hole was filled with a spike to the datum." That is a null elevation
  stored as a number, or you substituted 0. Check `elevation_m` for null
  before you subtract `elevation_min`.
- "The line leaves the surface and cuts a chord across a bend." You connected
  cells that are not neighbors, or you used only the first and last cell.
  Print the cell list length and the vertex count of the line. They match on a
  route with no holes.
- "The line is present and the mesh is a flat sheet on real Jezero data." The
  elevations are real and the relief is small at 1×. Switch to 3× before you
  call it a bug. If it is still flat at 5×, the elevation array is constant.
  That is the data file.

## Saturday night

Stop when orbit works, the selected line sits on the mesh, the scale label is
truthful, and one viewpoint does not translate. Push that. A headset attempt
after that is optional and goes in the handoff as a separate line so the
integration seat does not wait on it. If the real grid arrives after you have
only tested the fixture, load it once and look at the north edge before you
change any math. Most of the time the math is already right and the camera is
just too far away to see the relief.

## Before you say the view is done

Confirm each of these on the build you are about to hand over. A no on the
first four is still your bug. A no on the headset is a note, not a delay.

- The mesh test passes without a GPU.
- Vertical scale reads 3× on first load.
- The 1× and 5× buttons change that label and the relief.
- The selected route uses the same hex color as the sheet.
- A null cell is a hole. Nothing in that hole sits at the MOLA datum.
- The north edge matches Dhani's image on one shared cell.
- Viewpoint drag changes where you look, not where you stand.
- `Back to overview` returns the orbit camera.
- The headset button is hidden when no headset API exists.
- Reload does not stack a second canvas.
- Any dev overlay leaves the scale label readable.

If all of those are true and the real grid is still downloading, you are done for the night. Watch the download. Do not invent terrain to stand in for it. A flat practice sheet with the correct line is a finished evening. A dramatic surface from the wrong file is not.

# Integration — the shell, the science, the submission

You own the seams and the thing the judges actually open. The other four can
finish their files and still have no project. You make one page, one briefing,
one public URL, and one project-page submission that tells the truth about
which tier of data shipped.

You do not reimplement the search, the sampler, or the mesh. If a seam does
not fit, you change the wiring or you write the mismatch in
`handoff/integration.md` and make the owner fix their side. A quiet patch
inside their module will be overwritten the next time they work, and the demo
will break in the room.

Read the whole plan once. After that, live in sections 11, 15, 17, and 19. The
contract types live in the plan so you can paste them without waiting for
anyone.

## Files you own

```text
app/src/contract.ts
app/src/App.tsx
app/src/briefing/Briefing.tsx
app/src/briefing/briefing.test.ts
app/public/pois.json
app/public/fixtures/corridor.json     only if Ayush has not added it yet
app/package.json
app/index.html
.gitignore
README.md
handoff/integration.md
docs/submission.md                    the text you will paste into the project page
```

`corridor.json` is Ayush's fixture. If it is missing on Saturday afternoon,
create it from the grid diagram in the algorithm assignment and tell him. Do
not create a second fixture with a friendlier wall.

## contract.ts

Paste the types from the plan and from Ayush's assignment. One module.
Everyone imports from here. Fields:

- `Terrain` with `schema`, `cell_size_m`, `width`, `height`, `arrays`, and
  optional `sources`.
- `RouteRequest` with camelCase `avoidUncertain`.
- `Route` and `RouteSet` with snake_case `avoid_uncertain` on the set.
- `Mode`, `Traveler`, `BlockReason`.
- `Poi` with `id`, `name`, `col`, `row`, `caption`, `citation`, optional
  `heading_deg`, optional `eye_height_m`.

Do not add a field because it would be convenient. A `safe: boolean` field is
the kind of convenience that ends up on the briefing. If you need a derived
fact, compute it in the briefing from numbers that already exist.

Export the types and nothing that fetches. This file has no side effects. A
test imports it and constructs a fixture object. If that test needs a network,
the file is wrong.

## The shell

`App.tsx` is the only place that calls `planRoutes`. It loads `/terrain.json`.
If that fails or the arrays are the wrong length, it loads
`/fixtures/corridor.json` and sets `practice` true. Dhani's banner reads that
flag. You pass it down. You do not let the map fetch a second copy.

State: `traveler`, `avoidUncertain`, `goalId`, `selectedMode`. `selectedMode`
becomes the route set's `recommendation` whenever the set's identity changes,
unless you are in the middle of a click. The simplest correct policy is the
one in Dhani's assignment: snap back to the recommendation when traveler,
goal, or flag changes.

POIs come from `/pois.json`. The outpost is the start of every request. The
selected goal is the destination. Both must have integer `col` and `row`
inside the loaded grid. A POI outside the grid is dropped and listed in the
console once, not alerted in a loop.

Render order: Dhani's page, and inside it the slots they left for
`TerrainView` and `Briefing`. If `TerrainView` throws, catch it at the
boundary and show "The 3D view failed to start." The sheet must still be on
screen. A mesh bug is not an outage.

## pois.json

You write the names. The data seat writes the cells. Do not guess a column.

Each destination needs a `citation` string that is a URL or a paper title the
team can open. The caption is one or two sentences about why a crew would walk
there. It may say the ground preserves a delta, a crater-floor unit, or a
scarp, only if the source says that about this place. "Ancient water" is
allowed when the source is the Jezero delta literature, and it is attached to
the fan, not to every marker. A marker on undistinguished floor does not get a
water sentence.

The landing site, 18.44° N, 77.45° E, is context. If it is outside the crop,
it does not become a button. The briefing can say "The Perseverance landing
site, Octavia E. Butler Landing, is outside this crop, at 18.44° N, 77.45° E."
That sentence is allowed because the coordinate is published. Extra digits are
not.

Three destinations is the goal. One destination and the outpost is enough to
submit if the rectangle is small. A sixth viewpoint is not a goal. Viewpoints
reuse these POIs. Set `heading_deg` only after you have looked at the mesh and
chosen a direction that faces the feature. A heading of 0 on every point means
you did not look.

`eye_height_m` is 1.7 when you set it. That is an assumption about eyes, and
the briefing does not need to mention it. The 3D view uses it.

## The briefing

`Briefing.tsx` reads the route set, the selected mode, `region.json`, the POI
caption, and `terrain.sources`. It does not contain a typed distance. The test
builds a route set with distance 70 and asserts the text contains `70` and
does not contain `safe`.

Order on the page:

1. `Jezero Walk` and the region name.
2. Traveler, destination name, recommended mode in the sheet's words (Terrain,
   Shortest, or Observed).
3. Distance, climb, maximum slope, poorly observed percent, planning time.
   Same formatters Dhani exports from `src/format/routeCopy.ts`. Import them.
   If you format time a second way, the briefing and the sheet will disagree
   by a minute and a judge will notice.
4. The comparison sentence, the same function the sheet uses.
5. Assumptions, which are a fixed paragraph plus the numbers from `TRAVELERS`
   and the weights. The paragraph is:

```text
The route minimizes a stated cost on a four-connected grid.
Cells at or above the traveler's slope limit are not used.
The astronaut limit in this demo is 20 degrees.
The rover limit is 25 degrees.
Those limits are stricter than published rover driving practice
and they are not a flight rule for a crew.
Planning speeds are 1,000 m per hour for the astronaut and
110 m per hour for the rover.
The astronaut speed is an assumption.
The rover speed is a planning rate near published autonomous
driving, not a claim about a particular sol.
Vertical exaggeration on the 3D view does not enter these numbers.
```

6. Datasets, one line each, title and URL from `sources`. If the list is
   empty, write "Dataset list missing from terrain.json" in red. Do not
   substitute a prettier sentence that names a mission you did not sample.
7. Limits. Tier 1: "Elevation is the Mars 2020 CTX mosaic at 20 m per pixel,
   resampled to the cell size above. A cell cannot see a boulder smaller than
   that posting." Tier 2: "Elevation is the Mars 2020 HiRISE DTM mosaic at 1 m
   per pixel, resampled to the cell size above. Coverage marked coarser is CTX
   or a gap. Neither posting is a walk-around survey of loose rock."
8. The caption and the citation for the destination.

`briefing.test.ts` covers: numbers come from the object, the word `safe` is
absent, tier 1 produces the CTX sentence, tier 2 produces the HiRISE sentence,
an empty source list produces "Dataset list missing".

## README and gitignore

The README is half a page. What the page does. How to run `npm install` and
`npm run dev` in `app/`. How to run the router tests. How to rebuild the grid,
pointing at `data/README.md`. The URL once you have it. The sentence that this
is a planning demo with stated limits, not a traverse product.

`.gitignore` includes `node_modules`, `data/raw`, `*.tif`, `.env`, and dist if
you do not deploy dist by hand. It does not ignore `app/public/terrain.json`
or the JPEGs. Those are the site.

Do not put an API key in the repository. This project does not need one. If
someone adds a model key to make a caption, remove it. Captions are written by
you, from sources.

## Deploy

Vercel, static, root `app`, output the Vite build. The free default is enough.
No custom domain. The project page needs a URL that opens in a private window
without a login.

Build once locally with `npm run build` and open `dist` with a static file
server before you call the deploy done. A dev server that only works on your
laptop is not a submission.

If the JSON is too large for the host, shrink the JPEG quality and confirm the
JSON size. Do not move the grid to a second server. One origin.

Write the URL in the README and in `docs/submission.md`.

## The thirty seconds

Record the screen after the story works, then record it again if you make it
cleaner. Keep the first recording. Sunday evening you may need it.

Shot list, timed, for a 30-second video. Speak in English or show the words on
screen. The submission text is English either way.

- 0–4 s. The crop, the practice banner absent, the title Jezero Walk.
- 4–10 s. Click a destination. Three lines. The sheet shows two different
  distances.
- 10–16 s. Toggle Avoid poorly observed ground. The recommended line changes,
  or the sentence says why it cannot.
- 16–22 s. The 3D view shows the same line on the surface. The vertical scale
  label is readable.
- 22–30 s. The briefing, with a dataset name readable. Cut before the
  assumptions paragraph ends if you must. The dataset name matters more than
  the full paragraph.

No intro logo. No music you do not have rights to. No AI-generated flyover. If
a shot is AI imagery, watermark it and do not use it as the terrain. The
terrain is the screen recording of your page.

Also outline seven slides in `docs/submission.md`, in case the video is late:

1. Title, team, challenge name.
2. The problem: a walk needs slope and a way to say the map is coarse.
3. The crop on Jezero, one picture, the corner coordinates.
4. The three costs, one sentence each, the thresholds.
5. A picture of two routes and the number that made the recommendation.
6. The 3D surface, with the exaggeration printed.
7. Datasets, assumptions, the URL.

Seven includes the title and the close. Do not add an eighth.

## Project page text

Draft this in `docs/submission.md` and edit it Sunday to match the tier you
shipped. Do not leave the draft's numbers if the rectangle moved.

Summary:

```text
Jezero Walk is a page for planning a short traverse on a
cropped piece of Jezero crater. It turns a NASA elevation
model into a grid, estimates slope, and compares a shortest
legal route, a terrain-aware route, and a route that penalizes
coarser elevation. The same grid is drawn as a map and as a
3D surface. The briefing lists the assumptions and the
datasets. It is a planning demo, not a crew product.
```

AI disclosure, edit to the tools you actually used:

```text
The team used Cursor and Grok to draft the specification and
to help write code. Route choices are computed by A* from
the published weights. No language model selects a path.
No AI-generated image is presented as Mars data.
```

Data, tier 1:

```text
USGS Astrogeology Mars 2020 CTX DEM mosaic, 20 m,
M20_JezeroCrater_CTXDEM_20m. The grid is a resample of a
crop of that file. Imagery is a hillshade of the same grid
or the CTX orthomosaic, whichever the region file names.
```

Data, tier 2, add:

```text
USGS Mars 2020 HiRISE DTM mosaic
JEZ_hirise_soc_006, 1 m, resampled to the route cell.
CTX fills or surrounds cells that the HiRISE window does
not cover, and those cells are marked coarser.
```

References: the catalog URL, the Mangold and others 2021 Science paper if you
cite the delta, the NASA rover components page if you cite the 30° driving
note or the speed, and the libraries (Leaflet, Three.js, React). Cite the
plan's source list. Add anything you actually opened. A reference you did not
use is not a credit. It is noise.

Team size on the form must match the people who will be on the project. The
eligibility range is two to six. Five is inside it.

## The clock you enforce

You are the person who says no after Sunday 18:00 Europe/Rome. No new dataset.
No headset session that has not already worked. No renamed fields. The
recording and the form are the work. A route bug that steps on a null cell is
still worth fixing after 18:00. A new color is not.

Before you submit, open the URL in a private window, click one destination,
toggle the flag, and open the briefing. Then open the video or the slides.
Then open each citation URL. If any of those need a login, they do not count.

Submit on the team project tab with time left before 23:59 Europe/Rome. Ask
the Milano organizers earlier in the day whether they want a local file
sooner. The Space Apps page is the one that makes you eligible for global
judging.

## When the others are late

You can still assemble a story.

- No HiRISE: ship tier 1 and make the briefing say 20 m. Do not wait.
- No mesh: ship the map, the sheet, and the profile. Mention the 3D view as
  not in this build. Do not embed a picture of someone else's Mars.
- No live router: this is a problem. The fallback is Ayush's Python files of
  precomputed routes for the destinations, loaded by id. The flag then
  switches files rather than recomputing. Label it. Do not pretend the toggle
  ran A* in the browser if it did not.
- No POI citations: ship one destination called "North-east of the crop" with
  a caption that says the point was chosen to exercise the grid, not because
  of a named outcrop. That is honest and weaker. It is better than a
  fabricated outcrop.

## Handoff

```text
URL:
Build command and result:
Briefing tests:
Private-window check: pass or what failed
Tier in the briefing:
Video: recorded or not
Known gap:
```

## Saturday, in order

Start by putting `contract.ts` and a loading shell in the repository even if
every panel says "not connected." Ayush can import types. Dhani can render
into a real page. The 3D seat can mount a canvas that shows the fixture. None
of that requires the crater.

Then write `pois.json` for the fixture so the page has two buttons before
Jezero exists. Outpost at column 0, row 2, id `outpost`, name `Outpost`. Goal
at column 5, row 2, id `east`, name `East side`, caption `Practice goal on the
flat grid.`, citation empty. A second goal at column 2, row 2, id `wall`, name
`Blocked cell`, caption `This cell is above the slope limit. It exists so the
page can show an unreachable destination.`, citation empty. The practice
banner is the only thing that makes these names honest. When `practice` is
false, do not load this file. Load the real `pois.json` the data seat's cells
belong to. Keep the practice pois in `public/fixtures/pois.json` so a failed
terrain fetch still has goals.

Then the briefing tests, against a fake route set, before the wording gets
pretty. A test that locks the word `safe` out of the component is worth more
than a paragraph you are proud of.

Then wire `planRoutes`. Log the recommendation to the console once. Click the
flag. The log should change on the fixture from `terrain` to `uncertainty`. If
it does not, you are not passing the flag through, or you are caching the
first route set in a ref that does not update. Fix that before anyone styles
it.

Then deploy a preview that shows the fixture, with the banner. A public URL of
the practice grid is a useful checkpoint. Replace the data when the JSON
exists. Do not wait to learn the deploy at midnight.

## The route set is one object

Pass the same `RouteSet` reference to the sheet, the briefing, and the 3D
view. Do not let each child call `planRoutes` itself. Three calls should be
identical, and they will not be if anyone closes over an old flag. One call in
`App.tsx`, in a `useMemo` that depends on terrain, traveler, flag, start, and
goal.

If `planRoutes` throws, show "The route calculation rejected this grid." and
keep the map up. Do not catch and draw a straight line. A straight line is a
false route.

## Submission checklist

Walk this on Sunday. Each line is a yes or a no in `docs/submission.md`.

- The URL loads in a private window.
- The practice banner is absent.
- One destination click draws a route that is not a straight line across a
  cliff, or the sheet explains that the modes agree.
- The flag does something visible, or the sheet says the well-observed route
  is the same line.
- The briefing names the DEM that `region.json` says you used.
- The briefing does not say safe, certified, or NASA-approved. Search the page
  for those words.
- The video is 30 seconds or under, or the deck is seven slides or under.
- The AI disclosure matches the tools the team actually opened.
- Every link on the form opens without a login.
- The team on the form is the team that did the work, between two and six
  people.
- The challenge selected on the form is Interplanetary Survival Guide: Martian
  Map.

A no on the banner or the dataset name is a stop. Fix it. A no on the headset
is not a stop.

## Spoken line, if you record with a voice

One take, about twenty-five seconds, so the cuts have room:

```text
This is a two-kilometer crop of Jezero.
The amber line is the route that avoids steep cells.
The teal line stays on the finer elevation and is longer.
The same cells sit on the surface.
The briefing names the NASA elevation model and the limits we assumed.
```

Change the colors if the recommendation is not amber that day. Do not say "the
safe route." Do not say "real time." Do not say the rover drove this path.

## If two people edit the same prop

The map wants `onSelectGoal`. The briefing wants the selected POI. You define
both in `App.tsx` and pass them down. If Dhani and the 3D seat both create a
`selectedCell` state, delete one. The cell under the cursor can stay local to
the map. The selected route mode cannot. It has to be yours so the mesh and
the sheet move together.

When a file conflict names a field, open the plan and keep the plan's name.
`avoidUncertain` on the request, `avoid_uncertain` on the JSON result. You
will be asked to "make them consistent." Do not. The split is in the plan so
JSON and TypeScript can each look like themselves. Document it in the README
in one sentence so the next editor does not file it as a bug.

## README shape

Six short parts. What it is. What it is not, in two sentences: not a crew
product, not a colony, not a headset requirement. How to run the app. How to
run the tests. How to rebuild the grid. The deployed URL. No architecture
essay. The plan is the essay.

## Done

You are done when a person who was not in the room can open the URL, select a
destination, read why one line was recommended, see the dataset name, and
refresh without an error. The repository builds from a clean `npm install`.
The submission draft matches the tier. The word "safe" does not appear on the
page. Search the built files for it before you submit.

## Do not

- Do not put the NASA insignia on the page or the slides.
- Do not claim the route is the one Perseverance drove. If you draw the
  rover's traverse, it is a separate layer labeled as history, and only if you
  have the coordinates from a NASA page.
- Do not add a language-model call to "explain" the route. The comparison
  sentence is the explanation, and it is testable.
- Do not change a weight in `profiles.ts` to make the recording look more
  dramatic. That file is Ayush's. The recording uses the weights the tests
  use.
## pois.json, the practice copy

Put this in `app/public/fixtures/pois.json` so the page runs before the crater
file exists. The integration seat owns it until Ayush's fixture is the only
grid the app can see.

```json
{
  "schema": "jezero-walk.pois.v1",
  "pois": [
    {
      "id": "outpost",
      "name": "Outpost",
      "col": 0,
      "row": 2,
      "caption": "Practice start on the flat grid.",
      "citation": ""
    },
    {
      "id": "east",
      "name": "East side",
      "col": 5,
      "row": 2,
      "caption": "Practice goal. The three modes disagree on the way here.",
      "citation": ""
    },
    {
      "id": "wall",
      "name": "Blocked cell",
      "col": 2,
      "row": 2,
      "caption": "Above the slope limit, so the page can show an unreachable goal.",
      "citation": ""
    }
  ]
}
```

When the real grid loads, this file is not used. The real
`app/public/pois.json` has cells the data seat measured and citations you
looked up. Empty citation strings are allowed on the practice file and are not
allowed on a real destination you describe as geology. A real destination with
an empty citation is rendered by Dhani without a science sentence. Leave it
that way until you have a source. Do not fill the silence with a plausible
paragraph.

## The search you run before submit

From `app/` after `npm run build`:

```text
grep -R -n -i -E "safe|certified|nasa-approved" dist/ || true
```

Any hit in your briefing, the sheet, or a README that the build copied is a
rewrite, not a debate. A hit inside `node_modules` or a minified library name
is not yours. Look at the file. `unsafe` in a comment you wrote still counts.
Delete the comment.

Also open the briefing and read the dataset line out loud. If you cannot
pronounce the product because the field is empty, the data seat's `sources`
array did not get into the JSON. Do not type the product name into the
component as a fallback. The red "Dataset list missing" sentence is the
fallback, and it is there so you notice.

## Two previews

Deploy the practice-grid preview on Saturday even if you are embarrassed by
it. The banner makes it honest. Deploy the real-grid preview when
`terrain.json` is valid, over the same project. Keep the Saturday URL in the
README until the real one has been clicked in a private window. If the real
deploy fails at 21:00, the Saturday URL is still a submission, and the text
says it is the practice grid. That is a weak submission and a real one. A
broken real URL is not a submission.

Write both URLs in `docs/submission.md` with one line each: which grid, what
time you opened it in a private window, whether the flag moved the
recommendation. The private-window time is Europe/Rome. The form will be read
by people who were not in Milano, so the page itself has to carry the
explanation the room would have given.
