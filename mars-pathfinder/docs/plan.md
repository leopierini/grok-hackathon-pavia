# Jezero Walk — project plan

Status: build specification for the NASA Space Apps Challenge 2026 project. Written Saturday 14 November 2026, afternoon Europe/Rome. Nothing in this file has been implemented yet. The code does not exist. The numbers that come from files were read from those files; the numbers that are planning choices are marked as choices.

This is the plan for the whole product. The five assignments that implement it are in [tasks.md](tasks.md). If this file and a task disagree about a field name, a threshold, or a file path, this file wins. A person who thinks the contract is wrong writes the proposal in their handoff. They do not rename the field in their own code.

The working name is **Jezero Walk**. The earlier draft called the project Mars Pathfinder. Do not use that name on the submission page. Mars Pathfinder is the 1997 lander, and a judge who searches the name will land on the wrong mission. Jezero Walk says where the walk is. The name can change later. The behavior in this file cannot change without everyone seeing the change.

## 1. What we are building

Jezero Walk is a mission-planning page for one small piece of Jezero crater. A person chooses a traveler, an astronaut or a rover, and a scientific destination. The page draws three routes on real NASA elevation data, says which route it recommends and why, and shows the same ground as a 3D surface. A few fixed viewpoints let the person look around. They do not walk freely across the model.

The user is cast as a mission commander at a small fictional outpost. The outpost is a marker on the map. It is not a colony simulation. The terrain under it is the real terrain.

The product has to do all of the following in one sitting, on a laptop browser, without a Python server:

1. Show the cropped region with imagery, slope, and a coverage layer.
2. Accept one start and one destination from a short list. The start is the outpost. The destinations are scientific places inside the crop.
3. Show three routes for the selected traveler: shortest legal route, terrain-aware route, uncertainty-aware route.
4. Show distance, climb, maximum slope, the fraction of the route that is poorly observed, and the elevation along the route.
5. Change the recommended route when the traveler changes or when "avoid poorly observed ground" is turned on, if the data actually supports a different route.
6. Show the same route on a 3D surface built from the same elevation grid.
7. Open a briefing that a person could read aloud in thirty seconds, with the dataset names in it.

That is the demo. Everything else is optional.

### What counts as finished

There are two acceptance levels. Report them separately. Do not describe the second as if it were the first.

**Level 1 — the submission.** A public web page loads a real cropped elevation grid, computes or displays the three routes, and shows them on the 2D map and on the 3D surface. The briefing names the datasets. The page works after a refresh. The repository does not contain the multi-gigabyte source files.

**Level 2 — the stretch.** One ground-level viewpoint can be opened, and a Meta Quest browser can look around that viewpoint. Level 1 must already be true. If the headset is not ready on Sunday, submit Level 1.

A hillshade with a hand-drawn line on it is not Level 1. A 3D model downloaded from the internet, sitting under a route that came from a different place, is not Level 1. A route computed on a synthetic grid is acceptable only as a labeled fallback if the real crop fails, and the briefing has to say so in the first sentence.

## 2. Decisions already made

These came out of the team conversation on Friday 13 November 2026 and from checking the data on Saturday. They are not a menu.

| Question | Decision |
| --- | --- |
| What is the challenge? | Interplanetary Survival Guide: Martian Map. A layered view of one place or route that helps a person plan a Marswalk. |
| Where? | Jezero crater, inside the HiRISE 1 m terrain mosaic that contains the landing site and the western fan. The exact rectangle is chosen after one look at the hillshade, inside the footprint in section 6. |
| What is the user doing? | Planning a walk or a drive from a marked outpost to a scientific stop. |
| Colony simulator? | No. No oxygen, no base-building, no crew schedules. |
| Who picks the route? | A deterministic cost search. Not a language model. |
| How many routes? | Three modes, defined in section 10. Not every possible path. |
| Do astronaut and rover share a route? | No. Two traveler profiles, same ground, different slope limits and speeds. |
| What is uncertain ground? | Ground whose elevation is missing, coarser than the grid, or outside the HiRISE stereo model. The page says which. |
| 3D models from the internet? | No, for the terrain. The surface is the elevation grid. A generic rover or suit, if used at all, is decoration and is labeled as decoration. |
| Free walking in 3D? | No. Orbit the whole crop. Look around from at most six fixed viewpoints. |
| Unity or Unreal? | No. The team has one weekend, mixed laptops, and Eduroam. The page is Vite, React, TypeScript, Leaflet, and Three.js. |
| Do we need a GIS desktop application? | No. Python reads the GeoTIFFs. QGIS is optional for one person who wants to look; nobody else waits on it. |
| Where does the algorithm run? | In the browser, on a prepared grid. No FastAPI, no laptop in the room acting as a server. |
| Language of the algorithm? | TypeScript, so the page can recompute when a toggle changes. Ayush owns it. A Python prototype may be used to think, and then deleted or kept as a private check. The page imports the TypeScript module. |
| Who builds the interface? | Dhani. The map, the route comparison, the layer toggles, and the briefing layout. |
| Hosting? | Static files on Vercel, or any static host. No purchased domain. |
| Repository? | A new repository for this project. Do not build it inside the robot-patrol repository. These two documents are the specification. |
| Map projection in the browser? | A local image of the crop in meter coordinates. Not Google Maps, not Apple Maps, not a Web Mercator basemap of Earth. |
| Diagonal steps? | Not in this version. Four-connected movement only. |
| Vertical exaggeration? | Allowed on the 3D view, default 3×, and printed on the view. The briefing uses real meters. |

## 3. What we are not building

- A colony, a habitat designer, or a resource game.
- A rover-driving game with physics.
- A language model that "decides" the safe path.
- A global Mars gazetteer.
- A reconstruction of individual rocks. The elevation posting is 1 m in the best product and 20 m in the backup. A rock smaller than that is not in the data. Do not sprinkle 3D rocks on the mesh and call them measurements.
- A claim that a route is safe for a crew. The page compares routes under stated assumptions.
- Meta Quest as a requirement for the demo.
- Any download of the full 1.7 GB HiRISE mosaic into git, onto Vercel, or onto a teammate's laptop if a window can be read instead.

## 4. The challenge, the clock, and the judging

The public brief, as restated by 2026 local-event pages while the official challenge site was returning HTTP 500, is: create a layered, integrated view of a location or route on Mars that pulls together data from more than one NASA mission and could help a human explorer plan and carry out a Marswalk while doing science along the way.

Official project editing opens Saturday 14 November 2026 at 09:00 local time. Submission closes Sunday 15 November 2026 at 23:59 local time. For Milano that is Europe/Rome. Ask the Milano organizers whether they want a local presentation earlier than that. The Space Apps page is what makes the team eligible for global judging. Submit there even if the local session is earlier.

Global judging eligibility, from the 2026 participant discussion and FAQ:

- The team has between two and six people, registered for the same event.
- The project answers one of the 2026 challenges.
- At least one NASA data source from that challenge's resource list is actually used, not merely mentioned.
- The demo is a video of no more than 30 seconds, or a deck of no more than seven slides including the title and the closing slide.
- The submission text is in English. Every source is cited, including open-source libraries and AI tools.
- AI-generated images and video need a visible watermark. Do not put the NASA insignia, the meatball, or mission patches on AI-generated pictures.

The five criteria local organizers have been quoting, each scored from 1 to 10, are impact, creativity, validity, relevance, and presentation. The official judging guide wins if its wording differs. Build for those five anyway:

- Impact: a commander can see which way is shorter, which way is steeper, and which way is a guess.
- Creativity: the same grid explains the route, the uncertainty, and the 3D view.
- Validity: real elevation, named assumptions, tested routes, and a plain statement of what the grid cannot see.
- Relevance: several NASA products, one walk, one place.
- Presentation: one story from outpost to destination. The 30-second video shows the toggles, not a title card.

Participants are not expected to finish a flight product. A small thing that runs beats a large thing that needs the author to narrate over a crash.

This plan was written around 12:15 Europe/Rome on Saturday. The useful time left is Saturday afternoon through Sunday evening. Leave Sunday 21:00 onward for the recording, the links, and the form. Do not start the Quest setup after 18:00 on Sunday.

## 5. The user journey

The page opens on the crop. The outpost is already marked. Three destination cards are visible. The traveler control says Astronaut or Rover. The uncertainty control says Avoid poorly observed ground, and it is off.

The person picks a destination. Three lines appear. One is marked recommended. The sheet beside the map lists, for each line: distance, climb, descent, maximum slope, estimated time under the stated speed, and the share of cells that are poorly observed. A sentence says why the other two lost. Example, which must be generated from the numbers and not stored as a fixed slogan: "The shortest route crosses 180 m of ground with no HiRISE elevation. The terrain-aware route is 240 m longer and stays on the 1 m model."

The person turns on Avoid poorly observed ground. If a legal route remains on well-observed cells, the uncertainty-aware line becomes the recommendation and the map updates. If none remains, the page says the destination is unreachable under that rule. It does not draw a line through the forbidden cells.

The person selects a line. The elevation profile highlights. The 3D view flies the camera so that line is in frame. The line on the model is the same sequence of cells.

The person opens a viewpoint. The camera sits about 1.7 m above the surface at that cell and drag-to-look rotates it. A caption names the place and the source of the picture if a real panorama is available. If no panorama is available, the caption says the view is the elevation model, not a photograph.

The person opens the briefing. It is one page: mission, traveler, destination, recommended route, the three numbers that decided it, the assumptions, the datasets with links, and what the model cannot see.

## 6. Where on Mars

Jezero crater is the right site because the challenge asks for a real walk with science along it, and because two elevation products overlap there. Mount Sharp is a good site for a different team. We are not doing both.

The following bounds were computed on 14 November 2026 from the GeoTIFF headers, not from the HTML pages. Recompute them before trusting a screenshot. The method is in section 7.

### 6.1 CTX elevation mosaic, 20 m

File: `M20_JezeroCrater_CTXDEM_20m.tif`

Verified URL, after the USGS redirect:

`https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif`

Size: 90,345,300 bytes (about 86 MB). Width 4,456. Height 5,067. One sample, float32, uncompressed, one row per strip. No-data sentinel stored as the text `-3.4028234663852886e+38`.

Geographic footprint of the outer pixel edges:

| Edge | Value |
| --- | --- |
| West | 76.997437° E |
| East | 78.582563° E |
| North | 19.290187° N |
| South | 17.580520° N |

The Astrogeology HTML page lists minimum latitude 19.29 and maximum latitude 17.58. Those two labels are swapped relative to the file. Use the file.

This mosaic covers the crater, including the landing site. It is the backup elevation if the HiRISE window cannot be read.

### 6.2 HiRISE elevation mosaic, 1 m

File: `JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif`

Verified URL:

`https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif`

Size: 1,839,545,409 bytes (about 1.71 GB). Width 21,400. Height 21,488. One sample, float32, uncompressed, one row per strip, 1 m pixels. No-data text `-3.40282265508890445e+38`. Note that this sentinel is not the same text as the CTX file. Test no-data with a threshold, elevation less than −1e30, not with string equality.

Geographic footprint of the outer pixel edges:

| Edge | Value |
| --- | --- |
| West | 77.222933° E |
| East | 77.583964° E |
| North | 18.669315° N |
| South | 18.306799° N |

Octavia E. Butler Landing, 18.44° N, 77.45° E, falls inside this footprint, near column 13,459 and row 13,593 counting from the north-west corner. The mosaic is large enough to contain the landing site and ground several kilometers west of it, which is the direction of the western fan and of Kodiak. Confirm those places by looking. Do not take the column numbers as the science.

### 6.3 The rectangle we will actually route on

The route grid is a square inside the HiRISE footprint, so the best elevation and the backup elevation both exist there.

Rules for the person who locks the rectangle:

- Keep it inside 77.222933° E to 77.583964° E and 18.306799° N to 18.669315° N.
- Prefer 2 km by 2 km. That is 400 by 400 cells at 5 m, which the browser can search, and 2,000 by 2,000 HiRISE posts, which is a window rather than the whole mosaic.
- The square must contain the outpost and at least three destinations that are not the same slope in different clothes: one on the crater floor, one at a scarp or fan front, one at a named feature whose science sentence is real.
- If the first square is a flat parking lot, move it. Interesting means the slope histogram has walkable cells and blocked cells, not merely that the picture looks dramatic.
- Write the result to `app/public/region.json` and stop editing it. Everyone else reads that file.

Provisional square, to be accepted or moved after the hillshade, not before:

- South-west corner 77.35° E, 18.42° N.
- North-east corner 77.39° E, 18.46° N.

This box is about 2.1 km east-west and 2.4 km north-south, inside the HiRISE footprint, and west of the landing longitude. It is a candidate, not a finding. If the hillshade shows it is the wrong side of the fan, move it and record why.

### 6.4 Places the science text may use

Only places with a published position or a position read off a NASA map that you save a citation for:

- Octavia E. Butler Landing, the Perseverance landing site, 18.44° N, 77.45° E. Source: the name and coordinates published for that site. Use this precision. Do not invent extra digits.
- Séítah, the rocky unit on the crater floor that the rover skirted.
- The western fan / delta front, the scarp of the ancient delta.
- Kodiak, the butte south of the main scarp, described in the literature as on the order of 2.6 km west of the landing site. Measure its pixel in the crop before putting it on the page. If it is outside the crop, do not drag the crop across half the crater just to include it. Mention it in the briefing as context.

Destinations on the page are points inside the crop. Three is the requirement. Six viewpoints is the maximum.

## 7. The projection, which will silently break the overlay

Both files are equirectangular, on a sphere of radius 3,396,190 m, longitude positive east, planetocentric latitude, pixel-is-area. They do not share a projected coordinate system. Overlaying them by their meter coordinates is wrong.

The CTX DEM header says:

- Projection code 17, equirectangular.
- Latitude of true scale, standard parallel, 18.4663°.
- Center longitude 0, center latitude 0, false easting 0, false northing 0.
- Pixel scale 20 m.
- Upper-left corner, the outer corner of pixel (0, 0), at projected x = 4,328,999.999999998 m, y = 1,143,420.0000000028 m.
- Radius 3,396,190 m. The HTML page says 3,396,160 m. The file wins.

The HiRISE DEM header says:

- The same projection family, but the latitude of true scale is 0°. The file name says `latTs0`.
- Pixel scale 1 m.
- Upper-left corner at projected x = 4,577,366 m, y = 1,106,618 m.
- Radius 3,396,190 m.

Formulas, with longitude and latitude in radians and φ_ts the latitude of true scale:

```text
x = R * cos(φ_ts) * λ
y = R * φ
λ = x / (R * cos(φ_ts))
φ = y / R
```

For CTX, cos(18.4663°) is about 0.94851, so an east-west meter in the file is a true ground meter near Jezero. For HiRISE, cos(0) = 1, so an east-west meter in the file is a meter at the equator, and the same ground kilometer is a larger number of file-meters. A point's x in the CTX file is not its x in the HiRISE file.

Also, GeoTIFF row 0 is north. The route grid's row 0 is south. Flip once, in the data build, and never again.

The HTML page's "20 m pixel" is the map pixel. At this latitude the CTX pixel happens to be close to 20 m on the ground because the standard parallel sits on Jezero. The HiRISE pixel is 1 m in the equatorial scaling, which is about 0.95 m of east-west ground distance at 18.5° N. Do the routing on a grid that is square in local ground meters, built with the formulas, not by assuming the pixels are already that grid.

Check the reader against the headers before any route exists. The north-west corner of each file, converted with these formulas, must match section 6 to 0.0001°. If rasterio or PROJ returns the projected meters as if they were degrees, or applies a different radius, stop and convert with the formula. Do not "fix" it in the interface by nudging the image.

## 8. How the data becomes the app

Three tiers. Start at tier 1 while someone tries tier 2. Do not block the route work on tier 2.

| Tier | Elevation | What the team does | When it is enough |
| --- | --- | --- | --- |
| 1 | CTX 20 m, whole crater is 86 MB, the crop is a few megabytes | Resample the crop to 20 m cells. Coverage flag is "CTX elevation". | Sunday morning if HiRISE has not opened. Honest and submittable. |
| 2 | HiRISE 1 m window, resampled to 5 m cells for the route and the mesh | Read only the rows of the window. Build slope from the 5 m grid. Mark CTX-only cells, if any remain, as coarser. | This is the intended demo. |
| 3 | HiRISE image texture, CRISM mineral summary, or a published panorama at one viewpoint | Drapes or labels. Does not move the route by itself. | Add only after tier 2 routes match on the 2D and 3D views. |

A window of the HiRISE file is cheaper than the whole file and still not small. The file is one strip per row, and each strip is the full width, 21,400 samples of 4 bytes, about 85 KB per row. A 2 km window is 2,000 rows and about 170 MB of strips, because the unused columns in each row still travel. A 1 km window is about 85 MB. Start the transfer early. If it fails, tier 1 is the product, not a disgrace.

The 5 m CTX orthomosaic also exists, at about 343 MB:

`https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXortho_mosaic_5m.tif`

Use it as a texture if a window can be read. Otherwise use Mars Trek CTX tiles as pictures only. Trek tiles are not elevation. A pretty mosaic cannot feed the slope.

Other products that may be named in the briefing if they are actually shown:

- Mars Trek MOLA hillshade, as regional context, not as the route grid. MOLA posting is hundreds of meters. It must not be the surface the route claims to follow.
- A CRISM mineral browse for one destination, if a browse image can be placed by its own footprint. If it cannot be aligned, leave it out.
- Perseverance's published traverse, as a reference line, separate from our planned routes. Our line is not the rover's history.

Curiosity's radiation record and the Ames climate model are real and are the wrong scale for a 2 km walk. Do not bolt them on to look like more data. One sentence in the briefing may say radiation and weather are not resolved inside this crop.

### 8.1 The grid

The data build writes one JSON file, `app/public/terrain.json`, and two images, `app/public/layers/imagery.jpg` and `app/public/layers/slope.jpg`. The JSON is the only elevation the algorithm and the mesh are allowed to read.

```json
{
  "schema": "jezero-walk.terrain.v1",
  "built_at": "2026-11-14T18:00:00+01:00",
  "sources": [
    {
      "id": "hirise-dtm",
      "title": "Mars 2020 HiRISE DTM mosaic, 1 m",
      "url": "https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40",
      "role": "elevation"
    }
  ],
  "crs": {
    "radius_m": 3396190,
    "latitude_of_true_scale_deg": 18.4663,
    "local_frame": "east_north_meters_at_southwest_corner"
  },
  "origin": { "lon_deg": 77.35, "lat_deg": 18.42, "corner": "south_west" },
  "cell_size_m": 5,
  "width": 400,
  "height": 400,
  "nodata_rule": "elevation_below_-1e30_or_null",
  "row_order": "south_to_north",
  "column_order": "west_to_east",
  "arrays": {
    "elevation_m": [],
    "slope_deg": [],
    "roughness_m": [],
    "coverage": []
  }
}
```

`arrays` are row-major. Index of column `c`, row `r` is `r * width + c`. Row 0 is the south edge. Column 0 is the west edge. Length of each array is `width * height`.

`elevation_m` is MOLA elevation in meters. Jezero's floor is near −2,500 m. Negative is real. `null` is no data. Never encode no-data as 0 or as −9999.

`slope_deg` is the Horn slope in degrees on this metric grid, from 0 to 90. `null` where elevation is missing or the 3×3 window is incomplete.

`roughness_m` is the standard deviation of elevation in the 3×3 window, in meters. `null` on the same cells as slope.

`coverage` is an integer:

| Value | Meaning |
| --- | --- |
| 0 | No elevation, or only a regional product coarser than 100 m. Impassable. |
| 1 | CTX 20 m elevation, resampled. Usable, and uncertain, because a 20 m posting cannot see a boulder. |
| 2 | HiRISE elevation resampled to the cell. Best available. Still blind to anything smaller than the posting. |

The images are north-up JPEGs of the same rectangle. `region.json` carries the south-west and north-east corners in degrees so Leaflet can place the image. The mesh does not use the JPEG for heights.

Slope is computed after resampling onto square ground meters:

```text
dz/dx = ((c + 2f + i) - (a + 2d + g)) / (8 * cell_size_m)
dz/dy = ((g + 2h + i) - (a + 2b + c)) / (8 * cell_size_m)
slope = atan(sqrt(dz/dx^2 + dz/dy^2)) in degrees
```

The letters are the 3×3 elevations in the usual order, `a b c` on the north row, `g h i` on the south row, because our row index increases northward. If the implementation uses a north-up array, it has to match this definition or the tests fail. A missing neighbor makes the center `null`, not a substituted zero. Zero would invent a cliff at every no-data edge.

Roughness uses the cells that exist in that window. If fewer than 6 of the 9 exist, roughness is `null` and coverage stays whatever the elevation source was, but slope is `null` and the cell is not traversable. A route may not step onto a null slope.

### 8.2 Local meters

For a cell column `c` and row `r`, the cell center in local meters from the south-west corner is:

```text
x_east = (c + 0.5) * cell_size_m
y_north = (r + 0.5) * cell_size_m
```

Convert to degrees with the latitude of the region's mid-line, φ_mid, and radius R = 3,396,190 m:

```text
λ = λ_sw + x_east / (R * cos(φ_mid))
φ = φ_sw + y_north / R
```

Use one φ_mid for the whole crop, the latitude halfway up the rectangle. Across 2 km the error from holding cos(φ) constant is a few meters. That is smaller than the CTX posting and is acceptable if it is the same formula everywhere. Do not mix this with a Web Mercator conversion.

## 9. Travelers and costs

These are simulator assumptions. They are not NASA flight rules. Print them on the briefing.

Published rover facts the assumptions are built next to, not on top of:

- Perseverance's top speed on flat hard ground is just under 0.1 mph, about 152 m per hour, and the wheel-drive limit cited by JPL is 4.2 cm/s. Source: NASA's Perseverance rover-components page and the JPL mobility write-up.
- The rover is designed to withstand a 45° tilt without tipping, and drivers avoid terrain that would tilt it more than 30°. Source: the same NASA components page. Tilt is not the same number as the terrain slope of a 5 m cell. A 5 m cell can hide a 30° rock.

Our rover profile uses stricter cell limits than 30°, because the cell is an average and we have no wheel model:

| Profile | Caution slope | Blocked at or above | Planning speed | Speed source |
| --- | --- | --- | --- | --- |
| `rover` | 15° | 25° | 110 m/h | Near the autonomous-drive rate JPL has described, not the 4.2 cm/s wheel cap. Labeled as a planning rate. |
| `astronaut` | 12° | 20° | 1,000 m/h | Assumption. There is no flown Mars-suit walking speed. One kilometer per hour is a slow suited walk used only for the clock on the page. |

A cell is impassable when slope is null, coverage is 0, or slope is greater than or equal to the traveler's block threshold. Caution does not block. It raises cost.

Cost to step from one cell into an orthogonal neighbor, in meters of equivalent distance:

```text
S = slope_deg / block_deg          # 0 to just under 1 on a legal cell
U = 0 if coverage is 2
    1 if coverage is 1
    impassable if coverage is 0
R = min(roughness_m / 1.0, 1)      # 1 meter of local standard deviation saturates the term

cost = cell_size_m * (1 + alpha * S + beta * R + gamma * U)
```

Weights by mode:

| Mode | alpha | beta | gamma | Extra rule |
| --- | --- | --- | --- | --- |
| `shortest` | 0 | 0 | 0 | Impassable cells stay impassable. This is not a straight line through cliffs. |
| `terrain` | 4 | 2 | 0 | Slope and roughness matter. Coverage does not, except coverage 0 which is already impassable. |
| `uncertainty` | 4 | 2 | 6 | Same as terrain, plus a heavy penalty on coverage 1. |

`avoid_uncertain` is a request flag. When it is true, the uncertainty mode is the one that can become the recommendation, and coverage 1 is impassable rather than merely expensive. When it is false, all three modes are still computed, and the recommendation is the uncertainty mode only if its equivalent cost is within 15% of the terrain mode and its poorly-observed fraction is lower. Otherwise the recommendation is the terrain mode. Shortest is shown and is not the default recommendation. People already know the shortest line. The point of the page is when it is a bad recommendation.

Equivalent cost for that comparison is the sum of step costs, not the ground distance.

Speeds turn ground distance into a clock only. They do not change which path wins. The time on the sheet is `ground_distance_m / speed` and is labeled "at the planning speed, ignoring stops."

Climb is the sum of positive elevation changes along the cell centers. Descent is the sum of the absolute values of the negative changes. A null elevation on the path is a bug, because those cells were impassable.

## 10. The search

A* on the four-connected grid. Each step's ground length is `cell_size_m`, so the heuristic is the Manhattan distance in cells times `cell_size_m`. That heuristic is admissible because every weight in the cost is non-negative and the cheapest possible step is exactly `cell_size_m` (all of S, R, U zero). Do not use Euclidean distance while forbidding diagonal steps. Do not use a heuristic that includes slope. An inconsistent heuristic is not worth debugging tonight.

Tie-break, so two laptops draw the same line: when two open cells have the same f, expand the one with the smaller `g`; if `g` is equal, the smaller row; if the row is equal, the smaller column. Implement the priority as `(f, g, row, col)` with an increasing counter at the end if the language's heap is unstable. Document the counter. Tests use it.

No diagonal steps means a path cannot cut a corner. That bug is gone because the corner does not exist. Do not add diagonals on Sunday morning.

Reconstruct the path from parent pointers, including the start cell and the goal cell. Reverse it so the array begins at the start.

If the open set empties, the result is `unreachable`. There is no partial line presented as a route. The sheet says unreachable and names the rule that blocked the search: slope, no-data, or the avoid-uncertain flag.

The three modes are three searches. They are not one search with a color change. They may still coincide. When they coincide, the map draws one line and the sheet says the three modes agree. Do not offset the lines graphically to pretend there are three corridors.

### 10.1 The worked fixture

`app/public/fixtures/corridor.json` is a tiny grid the route tests use before the real crop exists. It is also the integration test. The data person does not have to produce it. It is part of the contract.

- Schema `jezero-walk.terrain.v1`, width 6, height 5, cell 10 m.
- Origin 77.35° E, 18.42° N. The origin is irrelevant to the path test.
- Every cell has elevation 0 except where noted, roughness 0, coverage 2, slope 2°.
- Cells (2, 2) and (3, 2) have slope 40°. Impassable for both travelers.
- Cells (1, 3), (2, 3), (3, 3), and (4, 3) have slope 3° and coverage 1.
- Cells (1, 1), (2, 1), (3, 1), and (4, 1) have slope 18° and coverage 2.
- Start cell (0, 2). Goal cell (5, 2). Rows south to north, columns west to east.

Only (2, 2) and (3, 2) are blocked, so a search is free to step through (1, 2) and (4, 2). Row 0 is flat 2° ground. The interesting result is that the winning lines are not the two hand-drawn detours around the wall. They were checked by running the search with the neighbor order and the heap key from section 10. Step cost uses the cell being entered. The start cell is not charged a step.

`shortest`, either traveler, seven steps, 70 m, ignores the 18° slope:

```text
(0,2) (1,2) (1,1) (2,1) (3,1) (4,1) (5,1) (5,2)
```

`terrain`, either traveler, seven steps. Astronaut equivalent cost 106. Rover equivalent cost 98.8. The line uses the gentle coverage-1 cells and comes back to row 2 as soon as the wall ends:

```text
(0,2) (1,2) (1,3) (2,3) (3,3) (4,3) (4,2) (5,2)
```

`uncertainty`, either traveler, nine steps, 90 m. It refuses both the 18° cells and the coverage-1 cells, and it takes the flat south edge. Astronaut equivalent cost 126. Rover equivalent cost 118.8.

```text
(0,2) (0,1) (0,0) (1,0) (2,0) (3,0) (4,0) (5,0) (5,1) (5,2)
```

The astronaut's terrain cost on the shortest path's cells, if you score those cells with terrain weights, is 226, higher than the rover's 194.8 on the same cells, because the block thresholds differ. That comparison is a test. It is not a fourth route.

`avoid_uncertain: true` does not change these three cell lists on this fixture, because the uncertainty line never needed a coverage-1 cell. It does change the recommendation. With the flag off, 126 is more than 15 percent above 106, so the recommendation is `terrain` even though that line is half poorly observed (four of eight cells). With the flag on, the recommendation is `uncertainty`. The terrain search is unchanged by the flag.

If an implementation returns any other cell list, the neighbor order, the heap key, or the legality test is wrong. Matching the distance without matching the cells is a failure.

## 11. What the route module returns

```json
{
  "schema": "jezero-walk.routes.v1",
  "traveler": "astronaut",
  "avoid_uncertain": false,
  "start": { "id": "outpost", "col": 10, "row": 12 },
  "goal": { "id": "scarp", "col": 80, "row": 90 },
  "recommendation": "terrain",
  "routes": [
    {
      "mode": "shortest",
      "status": "ok",
      "cells": [[10, 12], [11, 12]],
      "distance_m": 5,
      "climb_m": 0,
      "descent_m": 0,
      "max_slope_deg": 4.2,
      "mean_slope_deg": 3.1,
      "poorly_observed_fraction": 0,
      "equivalent_cost_m": 5,
      "time_h": 0.005,
      "blocked_reason": null
    }
  ]
}
```

`cells` are `[col, row]`. `poorly_observed_fraction` is the fraction of path cells whose coverage is 1. Coverage 0 cannot appear on an `ok` path. `blocked_reason` is `null`, `"slope"`, `"nodata"`, `"uncertain"`, or `"outside"`. `status` is `ok` or `unreachable`. `recommendation` is one of the three mode names, or `null` if every mode is unreachable.

The function signature, TypeScript, which Dhani calls and Ayush implements:

```ts
export function planRoutes(terrain: Terrain, request: RouteRequest): RouteSet
```

Pure. No `fetch`, no `Date.now` inside the search, no mutation of `terrain`. The same request returns the same object shape every time. Times use the speeds in section 9, not the clock.

`RouteRequest` is `{ traveler, avoidUncertain, start, goal }` where start and goal are `{ id, col, row }`.

Out of range columns, a start on an impassable cell, or a goal equal to the start: return a `RouteSet` with all three routes `unreachable` and a reason, do not throw. Throwing is reserved for a terrain object that fails the schema, which is a programmer error and may throw once at the boundary.

## 12. The 2D map

Leaflet with `CRS.Simple`. The image is the crop. The south-west corner of the image is map coordinate `[0, 0]` and the north-east corner is `[width_m, height_m]`, in the same local meters as section 8.2. Cell centers convert to that plane by the formula already given.

Do not use a tiled Earth basemap underneath. Do not use Mars Trek tiles as a Leaflet tile layer unless their equirectangular indices are converted into this same meter plane. A default Leaflet or MapLibre map is Web Mercator and will shear the crop. One image overlay is the whole basemap.

Layer toggles swap the image or draw a canvas under the routes:

- Imagery: the JPEG.
- Slope: the slope JPEG, with a legend from 0° to the astronaut block threshold and above.
- Coverage: a canvas of three colors. Coverage 2 is quiet, coverage 1 is marked, coverage 0 is marked as no route.

Routes are SVG or canvas polylines in the same meter plane. Colors are fixed: shortest slate, terrain amber, uncertainty teal. The recommended route is thicker. Color is not the only encoding. The sheet names them, and the lines are labeled at their midpoints.

Clicking the map does not create an arbitrary destination in this version. The meeting was right that an arbitrary click needs a complete map. Destinations are the markers in `pois.json`. A click on the ground can show the cell's elevation, slope, and coverage in a readout. That readout is how a judge sees that the grid is real.

## 13. The 3D view

Three.js. One mesh. X is east meters, Y is up, Z is north meters, from the same south-west corner. Y is not the raw MOLA value, because −2,500 m would put the camera in a hole and because the relief across 2 km may be only tens of meters.

```text
Y = (elevation_m - elevation_min_of_crop) * exaggeration
```

Default exaggeration is 3. The view always prints "Vertical scale 3×" or whatever the control is set to. The readout on hover shows the unscaled MOLA elevation.

One vertex per cell center is enough. Skip null cells by leaving a hole or by not building those triangles. Do not drop them to Y = 0. That fabricates a pit at −2,500 m below the floor, which is exactly the no-data bug.

The route is a ribbon or a fat line on the mesh, a meter above the surface so it does not z-fight, using the same cell list. If the 2D line and the 3D line have different corners, one of them is not reading `cells`.

Viewpoints come from `pois.json`:

```json
{
  "id": "scarp-look",
  "name": "Delta-front scarp",
  "col": 80,
  "row": 90,
  "heading_deg": 270,
  "eye_height_m": 1.7,
  "caption": "Elevation model only. No panorama is loaded for this point.",
  "panorama": null
}
```

`heading_deg` is degrees clockwise from north. The camera sits at eye height above the exaggerated surface and looks along that heading. Drag changes yaw and pitch. It does not translate. Six viewpoints maximum. If a real Mastcam-Z or other public panorama is aligned, `panorama` can be an image URL and the caption must say it is a photograph from the rover, not from the mesh. If alignment is not confident, leave it null. A wrong panorama is worse than the mesh.

WebXR: a button, "Look around in a headset", that starts an immersive session at the current viewpoint. Hide the button if `navigator.xr` is absent. The desktop drag-look is the required behavior. The headset is Level 2.

No shadows that pretend to be illumination from a particular sol. A single directional light is fine. No skybox of stars with a company logo.

## 14. The briefing

Generated from the `RouteSet`, the selected mode, `region.json`, and `pois.json`. No paragraph that contains a number is typed by hand into the component. Hand-written text is allowed only for the science sentence of a destination, and that sentence lives in `pois.json` with a `citation` field.

The page contains, in this order:

1. Title, traveler, destination, and the recommended mode.
2. Distance, climb, max slope, poorly observed fraction, planning time.
3. Two sentences produced from the comparison rule in section 9. If the modes agree, say they agree.
4. Assumptions: block thresholds, weights, speed, cell size, four-connected movement, exaggeration not used in these numbers.
5. Datasets: title and URL from `terrain.json` sources.
6. Limits: cell size, what coverage 1 cannot see, that this is not a traverse plan for a crew.

A print stylesheet so the browser's print-to-PDF is the leave-behind. No separate PDF library.

## 15. Repository, once the code starts

Create a new repository. Suggested name `jezero-walk`. These specification files can be copied in as `docs/plan.md` and `docs/tasks.md`.

```text
app/
  index.html
  package.json
  src/contract.ts          types from sections 8 and 11
  src/router/              Ayush
  src/map/                 Dhani
  src/briefing/            the integration seat, the text
  src/view3d/              the 3D seat
  src/App.tsx              the integration seat wires the four
  public/terrain.json      generated, committed if under about 8 MB
  public/region.json
  public/pois.json
  public/layers/*.jpg
  public/fixtures/corridor.json
data/
  build_grid.py            the data seat
  raw/                     gitignored GeoTIFFs and downloads
  README.md                how to rebuild the public files
```

`app/src/contract.ts` is copied from this plan and treated as frozen in the same way. The integration seat commits it first so the others can import it. Until that commit exists, each person may paste the types into their own file, and they must match.

Ignore `data/raw/`, `node_modules/`, and any `*.tif`. The JPEGs and `terrain.json` are build outputs that are committed so Vercel does not need GDAL.

Versions to pin when first installed, then leave alone: Node 20, React 18, Vite 5, TypeScript 5, Leaflet 1.9, Three r160 or the current stable that the 3D seat actually runs, Vitest. Python 3.11, numpy, rasterio, pillow. If rasterio will not install, the fallback is a tiny TIFF-strip reader for these two uncompressed files, not a different dataset. The strips are simple: one row each, no compression. That fallback is the data seat's problem, and the header formulas in section 7 are enough to crop without PROJ.

## 16. The five seats

The work is split so each person can finish a fake version before the real grid lands. Nobody's daily work is "help whoever is stuck."

| Seat | Person | Owns | Does not own |
| --- | --- | --- | --- |
| 1 | Ayush | `src/router/**`, router tests, the three modes, both travelers | GeoTIFF, CSS, the mesh, the submission form |
| 2 | Dhani | `src/map/**`, the route sheet, layer toggles, the page layout except the WebGL canvas internals | The search, the GeoTIFF, the mesh geometry |
| 3 | Data, name yourself in the handoff | `data/**`, `terrain.json`, the layer JPEGs, `region.json` bounds | React components, A* |
| 4 | 3D, name yourself in the handoff | `src/view3d/**` | A second copy of the route, a second coordinate system |
| 5 | Integration, name yourself in the handoff | `contract.ts`, fixtures, `App.tsx`, `pois.json` science text, briefing component, Vercel, the 30-second video, the project-page text | Rewriting the search because the colors are hard |

If a seat is empty, drop them in this order and say so in the submission: first drop headset and extra viewpoints, then drop the mesh and keep the elevation profile, then drop the rover profile and keep the astronaut. Do not drop the real grid to save the mesh. A mesh of noise is the failure mode the meeting already identified.

## 17. Order of the weekend

Times are Europe/Rome on the weekend of 14–15 November 2026.

**Saturday 14:00–16:00.** Data seat starts the CTX crop and a HiRISE window in the background. Integration commits `contract.ts`, `corridor.json`, and an app shell that loads the fixture. Ayush makes `planRoutes` pass the fixture tests. Dhani draws the fixture image and three SVG lines from a hard-coded `RouteSet`. The 3D seat extrudes the fixture into a mesh, including the 40° wall, so the hole or the cliff is visible.

**Saturday 16:00–20:00.** The real grid replaces the fixture in the app through a URL flag, `?grid=terrain`, defaulting to the fixture until `terrain.json` validates. Routes on the real grid are inspected by eye against the slope image. If the line crosses a white no-data hole or a red slope, stop and fix the mask, not the camera.

**Saturday 20:00–24:00.** Recommendation rule, both travelers, the briefing filled from JSON, the 3D line on the real mesh. Deploy a preview URL.

**Sunday morning.** Move the rectangle if the science is in the wrong place. Add coverage coloring and the avoid-uncertain control. Write the real captions. Record a backup screen capture as soon as the story works, then try to make it prettier.

**Sunday after 18:00.** No new data sources. No Quest unless Level 1 has already been recorded. Fill the project page. Open every link in a private window. Submit with time left before 23:59.

## 18. Tests that are not optional

Router, on the fixture:

- The three paths in section 10.1 for the astronaut, `avoidUncertain` false.
- The same three cell lists for the rover. Assert rover terrain cost close to 98.8 and rover uncertainty cost close to 118.8. Assert that scoring the shortest path's cells with astronaut terrain weights (226) costs more than scoring them with rover terrain weights (194.8).
- `avoidUncertain: true` leaves the three cell lists unchanged on this fixture and switches the recommendation from `terrain` to `uncertainty`.
- Goal on cell (2, 2) is unreachable with reason slope.
- Start equal to goal is unreachable with reason outside, or a dedicated `same-cell` reason if you add it to the contract. Pick `outside` and document it. Do not return a one-cell path as a successful walk unless the contract is revised. A zero-length walk is not a demo.
- A terrain object with elevation −2,500 and slope 1 is traversable. Negative elevation is not no-data.
- Two calls return deep-equal results.

Data, on the real header:

- Computed north-west corners match section 6 within 0.0001°.
- A known pixel near the landing converts to within a pixel of column 13,459, row 13,593 on the HiRISE file.
- No slope cell is non-null where elevation is null.
- The minimum elevation in the crop is greater than −10,000 and less than −1,000. If the minimum is −3e38, the sentinel leaked into the array.
- The fraction of coverage 2 is reported in `region.json`. If it is zero, the app is on tier 1 and the briefing must say "20 m CTX elevation."

Interface, by hand, because a full browser suite is optional:

- Both travelers, three destinations, refresh, the recommendation survives a reload only as a new computation, not as a stale global.
- Avoid-uncertain either changes the line or shows a sentence that no well-observed route exists.
- The 2D midpoint and the 3D midpoint are the same cell. Check one route by printing `(col, row)`.

## 19. Submission text, to be finished Sunday

The project page needs a short summary, a demo link, a project link, the data used, the AI disclosure, and references. Draft the shape now so Sunday is editing rather than invention.

Summary, to be rewritten once the rectangle is real:

> Jezero Walk plans a short traverse on the western side of Jezero crater. It resamples NASA elevation into a grid, estimates slope, and compares a shortest legal route, a terrain-aware route, and a route that penalizes poorly observed ground. The same grid is drawn as a map and as a 3D surface. Assumptions and dataset links are on the briefing.

AI disclosure, edit to match what was actually used:

> The team used Cursor and Grok to draft the specification and to assist coding. The route is computed by A* with the published weights. No language model chooses the path. No AI-generated imagery is presented as Mars data.

Data section, edit to the tier that shipped:

> USGS / Mars 2020 CTX DEM mosaic, 20 m, and, if present, the HiRISE 1 m DTM mosaic `JEZ_hirise_soc_006`. Imagery from the CTX orthomosaic or Mars Trek. Landing-site coordinates from the published Octavia E. Butler Landing location.

Do not write "we used NASA data" without the product names.

## 20. Claims the page is allowed to make

Allowed:

- The elevation comes from the named NASA product, at the named posting, resampled to the named cell size.
- Slope is the Horn slope of that grid.
- A route minimizes the stated cost and avoids cells at or above the stated block threshold.
- Coverage 1 is coarser than coverage 2, and the page prefers coverage 2 when the weights say so.
- The 3D surface is that grid, with a stated vertical exaggeration.

Not allowed:

- "Safe for astronauts."
- "The shortest path on Mars."
- "High-resolution" without the number.
- "Real time from the rover."
- "This rock is at this coordinate" for any rock that was modeled by an artist.
- A NASA logo, or a sentence that implies NASA operates the tool.

## 21. Sources checked while writing this plan

The official challenge page and the Milano event page both returned HTTP 500 on 14 November 2026, so the brief is taken from the public 2026 wording mirrored by local-event sites, principally the UAE challenge list and the Space Data Atlas notes for this challenge. Those mirrors are not the authority. Open the official Resources tab before submission and cite what you actually call.

Files whose headers were read directly:

- CTX DEM, 90,345,300 bytes, tags as in section 7. Astrogeology catalog page: `https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic`
- CTX orthomosaic, 359,599,280 bytes, URL in section 8, existence checked by HTTP HEAD only. Its projection was not decoded for this plan. Decode it before draping.
- HiRISE DTM, 1,839,545,409 bytes, tags as in section 7. Catalog discussion of the TRN mosaic: the Astrogeology Mars 2020 HiRISE DTM pages.

Other references:

- NASA, Perseverance rover components, for the 45° tip tolerance, the 30° driving avoidance, and the speed "just under 0.1 mph (152 meters per hour)": `https://science.nasa.gov/mission/mars-2020-perseverance/rover-components/`
- JPL robotics, Mars 2020 mobility, for the 4.2 cm/s wheel speed and the roughly 110 m per hour autonomous drive: `https://www-robotics.jpl.nasa.gov/what-we-do/flight-projects/mars-2020-rover/m2020mobility/`
- Octavia E. Butler Landing coordinates 18.44° N, 77.45° E, as published with that place name.
- Mangold and others, 2021, Science, on the delta-lake system, cited by the USGS mosaic page: `https://doi.org/10.1126/science.abl4051`
- NASA Space Apps participant FAQ and the 2026 community answers on team size, the 30-second video or seven-slide deck, AI disclosure, and the data requirement.

The Caltech Murray Lab Jezero page hosts a separate 1 m DEM mosaic of about 582 MB. It is a different processing of similar stereo pairs. Do not mix it with the USGS mosaic in the same grid. One elevation source per cell. If HiRISE USGS cannot be read, use CTX, not a silent blend of two DEMs.

## 22. How to read the tasks

[tasks.md](tasks.md) gives each seat one assignment. The headings inside an assignment are for reading. They are not a license to cut the job into new tickets with new interfaces. Each assignment is written so it can be copied into its own file later. Shared rules are repeated on purpose, in short form, because that person may not have the others' pages open.

When the real rectangle moves, only `region.json`, `pois.json`, and `terrain.json` change. The router does not change. The mesh does not change. The map does not change. If a move requires a code change, the grid contract was violated.
