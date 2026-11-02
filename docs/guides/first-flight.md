# Run your first flight

About ten minutes, with nothing installed except Docker.

1. **Start the stack.** From the repository: `docker compose up --build`
   (or `make up`). Open http://localhost:4321.
2. **Import the reference rocket.** In **Missions**, choose **Import mission
   file** and pick `missions/examples/calisto.mission.zip`. A bundle carries the
   mission and its thrust curve and drag table, so it flies straight away.
3. **Open it.** Select the Calisto card and choose **Open in editor**.
4. **Fly it.** Go to **Single flight** and choose **Run flight**. It takes
   about a second. You should see an apogee of about **3,306 m** above the pad.
5. **Read where the number came from.** The panel under the run button lists
   the mission's config hash, the RocketPy version, the build and the atmosphere.
   That is the answer to "where did this number come from?"
6. **Change something.** In **Site**, set the inclination to 80°, then run the
   flight again. A banner says the old result no longer matches the mission;
   the new run updates it. Undo (⌘Z / Ctrl+Z) puts it back.

## Without Docker

`uv run python -m simcore run tests/fixtures/calisto/calisto.mission.yaml`
prints the same summary as JSON. See [the method](../methods/flight.md) for
what the numbers assume.
