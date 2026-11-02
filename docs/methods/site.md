# Launch site: method

What the **Site** section stores and how each part is used.

## The rail

| Field | Used for |
| --- | --- |
| `latitude_deg`, `longitude_deg` | Where the flight starts, and where forecasts are fetched for. WGS84. |
| `elevation_m` | Pad height above mean sea level. Air density at launch, and where the wind profile starts. |
| `rail_length_m` | Usable rail length. Rail exit is when the upper rail button leaves it. |
| `inclination_deg` | Angle above horizontal; 90 is vertical. |
| `heading_deg` | Direction the rail points, clockwise from true north. Not drawn on the map for a vertical rail (89.5° or more), where it has no meaning. |

Angles are degrees ([ADR 0001](../adr/0001-angles-in-degrees.md)).

**Elevation matters more than it looks.** It sets the air density at launch,
and it is where the forecast profile is anchored, so an error of 70 m moves
surface pressure by about 8 hPa. Survey the pad, or take it from a GPS averaged
over a few minutes. Model terrain heights (including the one Open-Meteo
reports) are averages over kilometres.

## Range geometry

- **Boundary:** the polygon the rocket must land inside. Dispersion analysis
  reports the probability of landing outside it, so draw the real range limits,
  not a rough square. A pad outside its own boundary is a warning.
- **Hazard zones:** polygons the rocket must not land in (buildings, roads,
  water, crowds). A pad inside one is an error.
- **Access roads:** drawn for the recovery team; not used in any calculation yet.

Polygons are stored as `[longitude, latitude]` points, without repeating the first.

## The map

The basemap is chosen once when the app loads:

1. local vector tiles if the stack has a tile file (`VITE_MAP_PMTILES`; fully offline);
2. otherwise OpenFreeMap street tiles when the browser is online;
3. otherwise no basemap, with a scale bar and the site's own layers only.

**Satellite** (top right) switches to Esri World Imagery when online. It is the
easiest way to place the pad and trace a boundary accurately. The imagery is
only for display: nothing in a simulation depends on it.
