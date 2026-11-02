# Weather on launch day

The wind decides where the rocket lands and how much it turns off the rail.
This is the routine for getting it right with no internet at the site. The
method behind it is in [Weather and wind](../methods/weather.md).

## The evening before (with internet)

1. Open the mission and check **Site**: the pad's coordinates and elevation are right.
2. In **Weather**, choose **Fetch forecast**. Apogee keeps every forecast it
   fetches, so this one stays available offline.
3. Pick the planned launch time under **Launch time** and choose **Use this hour**.
   The charts show wind speed and direction against height above the pad.
4. Look at the shape, not just the surface wind. A strong jet a few kilometres up
   carries a descending rocket further than the breeze at the pad does.
5. Run **Single flight** and note where it lands. Save the mission.

If the launch window spans several hours, try each hour and fly the worst one too.

## At the pad (no internet)

1. Check the forecast's age, under the heading in **Weather**. It turns amber
   after 6 hours and red after 24 hours. An old forecast is still the best you have
   offline, but treat the landing point as rougher.
2. **Measure the surface wind** with a hand anemometer, in the open, at a known
   height (2 m is typical). Take the average over a minute, and the direction it
   blows *from*.
3. In **Weather**, choose **Add surface wind** and enter speed, direction and
   anemometer height. Near the ground the profile now follows your measurement,
   fading into the forecast by the blend depth (300 m by default). The charts
   show the forecast as a dashed line and the blended profile as a solid one, so
   you can see what the blend did.
4. Run **Single flight** again. Compare the landing point against the range
   boundary on the **Site** map.
5. Run a campaign in **Dispersion** (200 samples is a good start). Read the
   chance of landing outside the boundary by its upper bound, not the estimate:
   see [Monte Carlo](../methods/monte-carlo.md).

## If the range gives you a wind table

Some ranges brief a wind table (height, speed, direction). In **Weather**, choose
**By hand**, then **Start a table** (or **Start from the forecast in use** to edit
the forecast's values). Note where it came from. If you have the pad's
temperature and station pressure, enter them too; on a hot day they move apogee.

## Choosing the blend settings

- **Exponent (alpha):** 0.14 over open, flat ground; 0.2 to 0.25 over scrub or
  rough terrain. Higher means the wind increases faster with height.
- **Blend depth:** how high your measurement is trusted. 300 m suits a steady
  day. Use less if the forecast and measurement disagree a lot and you trust the
  forecast aloft, or more if the forecast looks wrong near the ground.

## When a measurement looks wrong

A surface wind blowing the opposite way to the forecast is possible (sea
breezes, valley flows), but check it. The blend turns smoothly between the two,
but it can't tell you which one is right.
