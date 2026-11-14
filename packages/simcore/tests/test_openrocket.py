"""OpenRocket import. Lanius tests need the team's file in data/ and skip without it."""

from pathlib import Path

import pytest

from simcore.importers.openrocket import OrkError, import_openrocket

ROOT = Path(__file__).parents[3]
LANIUS = ROOT / "data" / "Lanius.ork"
M1340W = ROOT / "tests" / "fixtures" / "motors" / "AeroTech_M1340W.eng"

SMALL = b"""<?xml version='1.0' encoding='utf-8'?>
<openrocket version="1.10" creator="OpenRocket 24.12">
  <rocket><name>Tiny</name>
    <subcomponents><stage><name>Sustainer</name><subcomponents>
      <nosecone><name>Nose</name>
        <material type="bulk" density="1000.0">Test</material>
        <length>0.3</length><thickness>0.002</thickness><shape>conical</shape>
        <shapeparameter>0</shapeparameter><aftradius>0.04</aftradius>
      </nosecone>
      <bodytube><name>Body</name>
        <overridemass>1.0</overridemass>
        <material type="bulk" density="1000.0">Test</material>
        <length>1.0</length><thickness>0.002</thickness><radius>0.04</radius>
        <subcomponents>
          <innertube><name>Motor tube</name>
            <axialoffset method="bottom">0.0</axialoffset>
            <material type="bulk" density="1000.0">Test</material>
            <length>0.3</length><outerradius>0.02</outerradius><thickness>0.001</thickness>
            <motormount><overhang>0.0</overhang>
              <motor configid="a"><manufacturer>Test</manufacturer><designation>H100</designation>
                <diameter>0.038</diameter><length>0.2</length></motor>
            </motormount>
          </innertube>
          <masscomponent><name>Avionics</name><axialoffset method="top">0.1</axialoffset>
            <packedlength>0.1</packedlength><packedradius>0.03</packedradius><mass>0.5</mass>
          </masscomponent>
          <trapezoidfinset><name>Fins</name><axialoffset method="bottom">0.0</axialoffset>
            <material type="bulk" density="1000.0">Test</material>
            <fincount>3</fincount><thickness>0.003</thickness><rootchord>0.1</rootchord>
            <tipchord>0.05</tipchord><sweeplength>0.04</sweeplength><height>0.06</height><cant>0.0</cant>
          </trapezoidfinset>
          <parachute><name>Chute</name><axialoffset method="top">0.2</axialoffset>
            <material type="surface" density="0.05">Nylon</material>
            <packedlength>0.1</packedlength><packedradius>0.03</packedradius>
            <cd>1.5</cd><diameter>1.0</diameter><deployevent>apogee</deployevent><deploydelay>0.5</deploydelay>
          </parachute>
        </subcomponents>
      </bodytube>
    </subcomponents></stage></subcomponents>
    <motorconfiguration configid="a" default="true">
      <stage number="0" active="true"/>
    </motorconfiguration>
  </rocket>
</openrocket>
"""


def test_small_design_maps_geometry_and_masses() -> None:
    r = import_openrocket(SMALL)
    rocket = r.rocket
    assert rocket.radius_m == pytest.approx(0.04)
    assert rocket.nose.kind == "conical"
    assert rocket.motor_position_m == pytest.approx(1.3)  # nose 0.3 + body 1.0, motor tube flush
    [fins] = rocket.fins
    assert fins.position_m == pytest.approx(
        1.2
    )  # root leading edge, fins flush with the body's end
    assert r.motor is not None and r.motor.designation == "H100"
    [chute] = r.recovery.devices
    assert chute.cd_s_m2 == pytest.approx(1.5 * 3.14159265 * 0.25, rel=1e-6)
    assert chute.lag_s == 0.5
    # The measured body tube (1.0 kg) and the avionics (0.5 kg) are exact.
    assert rocket.dry_mass_kg > 1.5


TRAPEZOID_XML = (
    b"<trapezoidfinset>",
    b"<tipchord>0.05</tipchord><sweeplength>0.04</sweeplength><height>0.06</height>",
    b"</trapezoidfinset>",
)
# The same trapezoid drawn as a freeform outline, starting off x = 0 as OpenRocket allows.
FREEFORM = (
    SMALL.replace(TRAPEZOID_XML[0], b"<freeformfinset>")
    .replace(
        TRAPEZOID_XML[1],
        b"<finpoints><point x='0.01' y='0.0'/><point x='0.05' y='0.06'/>"
        b"<point x='0.1' y='0.06'/><point x='0.11' y='0.0'/></finpoints>",
    )
    .replace(b"<rootchord>0.1</rootchord>", b"")
    .replace(TRAPEZOID_XML[2], b"</freeformfinset>")
)


def test_freeform_fins_import_with_their_outline() -> None:
    trapezoid = import_openrocket(SMALL)
    freeform = import_openrocket(FREEFORM)
    [fins] = freeform.rocket.fins
    assert fins.kind == "free_form"
    assert fins.points == [
        (0.0, 0.0),
        pytest.approx((0.04, 0.06)),
        pytest.approx((0.09, 0.06)),
        pytest.approx((0.1, 0.0)),
    ]
    assert fins.position_m == pytest.approx(1.2)
    # Same shape, same material: the polygon mass model matches the trapezoid one.
    assert freeform.rocket.dry_mass_kg == pytest.approx(trapezoid.rocket.dry_mass_kg, rel=1e-9)
    assert freeform.rocket.dry_cg_m == pytest.approx(trapezoid.rocket.dry_cg_m, rel=1e-9)
    assert not any("no mass model" in u.detail for u in freeform.report.unsupported)


def test_freeform_fins_off_the_body_tube_are_reported_not_flown() -> None:
    off_body = FREEFORM.replace(b"<point x='0.11' y='0.0'/>", b"<point x='0.11' y='0.01'/>")
    with pytest.raises(OrkError, match="no fins this importer can fly"):
        import_openrocket(off_body)


def test_drag_is_estimated_even_without_a_simulation() -> None:
    r = import_openrocket(SMALL)
    assert r.rocket.drag.power_off.estimate and r.rocket.drag.power_on.estimate
    assert r.cross_check_drag is None and r.assets == {}
    assert any(a.target == "rocket.drag" for a in r.report.approximated)
    assert [c.status for c in r.report.cross_checks] == ["unavailable"]


def test_hostile_xml_is_refused() -> None:
    bomb = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>
<openrocket><rocket>&lol2;</rocket></openrocket>"""
    with pytest.raises(OrkError):
        import_openrocket(bomb)


def test_not_an_openrocket_file_is_refused() -> None:
    with pytest.raises(OrkError):
        import_openrocket(b"<svg/>")


lanius = pytest.mark.skipif(not LANIUS.exists(), reason="team's Lanius.ork is not in data/")


@lanius
def test_lanius_mass_and_cg_match_openrocket() -> None:
    r = import_openrocket(LANIUS.read_bytes())
    by_name = {c.quantity: c for c in r.report.cross_checks}
    dry = by_name["Dry mass"]
    assert dry.ours == pytest.approx(dry.openrocket, rel=1e-3)
    cg = by_name["CG at liftoff, with motor"]
    assert cg.ours is not None and cg.openrocket is not None
    assert abs(cg.ours - cg.openrocket) < 0.002
    assert all(c.status == "ok" for c in r.report.cross_checks)


@lanius
def test_lanius_report_flags_what_a_team_should_know() -> None:
    r = import_openrocket(LANIUS.read_bytes())
    text = " ".join(r.report.warnings)
    assert "out of date" in text
    assert "actually uses 2 m/s" in text
    assert r.report.reference_simulation == "0 m/s Wind"
    assert [d.name for d in r.recovery.devices] == ["drogue", "main"]
    assert r.recovery.devices[1].trigger.kind == "altitude_agl"


@lanius
def test_lanius_flies_like_openrocket(tmp_path: Path) -> None:
    from simcore.assets import DirectoryAssetStore
    from simcore.importers.openrocket import cross_check_mission
    from simcore.importers.thrust import generic_motor_estimate, parse_eng
    from simcore.jobs import openrocket_cross_check

    r = import_openrocket(LANIUS.read_bytes())
    store = DirectoryAssetStore(tmp_path / "assets")
    assets = {}
    for sha, (name, data) in r.assets.items():
        store.put(data)
        assets[sha] = {"kind": "drag_table", "filename": name, "size": len(data)}
    eng = M1340W.read_bytes()
    tsha = store.put(eng)
    assets[tsha] = {"kind": "thrust_curve", "filename": M1340W.name, "size": len(eng)}
    motor = {
        "kind": "generic",
        "thrust_curve": tsha,
        **generic_motor_estimate(parse_eng(eng.decode())),
    }
    mission = cross_check_mission(
        r.rocket, r.recovery, motor, assets, r.reference, drag=r.cross_check_drag
    )
    rows = {
        row["quantity"]: row
        for row in openrocket_cross_check(
            mission.model_dump(mode="json"), reference=r.reference, data_dir=str(tmp_path)
        )
    }
    assert rows["Apogee"]["ours"] == pytest.approx(rows["Apogee"]["openrocket"], rel=1e-3)
    assert rows["Apogee"]["status"] == "ok"
    cp = next(v for k, v in rows.items() if k.startswith("Centre of pressure"))
    assert abs(cp["ours"] - cp["openrocket"]) < 0.01
    assert rows["Rail exit velocity"]["status"] == "explained"


def test_fin_thickness_and_material_come_across() -> None:
    unknown = import_openrocket(SMALL)
    [fins] = unknown.rocket.fins
    assert fins.thickness_m == pytest.approx(0.003) and fins.material is None
    assert any("no known shear modulus" in i.detail for i in unknown.report.approximated)

    fiberglass = SMALL.replace(
        b'<material type="bulk" density="1000.0">Test</material>\n            <fincount>',
        b'<material type="bulk" density="1850.0">Fiberglass</material>\n            <fincount>',
    )
    [fins] = import_openrocket(fiberglass).rocket.fins
    assert fins.material is not None and fins.material.shear_modulus_pa == pytest.approx(3e9)
