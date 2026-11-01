from pathlib import Path

import pytest

from simcore.assets import AssetError, DirectoryAssetStore, sha256_hex
from simcore.importers.drag import DragTableError, parse_drag_csv
from simcore.importers.thrust import ThrustCurveError, parse_eng

CALISTO = Path(__file__).parents[3] / "tests" / "fixtures" / "calisto"


def test_parse_eng_reads_header_and_points() -> None:
    curve = parse_eng((CALISTO / "Cesaroni_M1670.eng").read_text())
    assert curve.designation == "M1670-BS"
    assert curve.diameter_m == pytest.approx(0.075)
    assert curve.points[0] == (0.0, 0.0)
    # An M motor: 5,120 to 10,240 N·s.
    assert 5120 < curve.total_impulse_ns < 10240


def test_parse_eng_does_not_duplicate_t0() -> None:
    curve = parse_eng("X 10 100 0 0.1 0.2 T\n0 5\n0.5 10\n1 0\n")
    assert curve.points == [(0.0, 5.0), (0.5, 10.0), (1.0, 0.0)]


@pytest.mark.parametrize(
    "text",
    ["", "X 10 100 0 0.1 0.2 T\n", "X 10\n0.1 1\n0.2 2\n", "X 10 100 0 0.1 0.2 T\n0.2 1\n0.1 2\n"],
)
def test_parse_eng_rejects_bad_files(text: str) -> None:
    with pytest.raises(ThrustCurveError):
        parse_eng(text)


def test_parse_drag_csv_allows_one_header() -> None:
    assert parse_drag_csv(b"mach,cd\n0.1,0.4\n0.5,0.45\n") == [(0.1, 0.4), (0.5, 0.45)]


def test_parse_drag_csv_requires_increasing_mach() -> None:
    with pytest.raises(DragTableError):
        parse_drag_csv(b"0.5,0.4\n0.1,0.45\n")


def test_directory_store_detects_corruption(tmp_path: Path) -> None:
    store = DirectoryAssetStore(tmp_path)
    sha = store.put(b"thrust")
    assert store.read(sha) == b"thrust"
    (tmp_path / sha).write_bytes(b"tampered")
    with pytest.raises(AssetError, match="corrupt"):
        store.read(sha)


def test_directory_store_rejects_non_hashes(tmp_path: Path) -> None:
    with pytest.raises(AssetError):
        DirectoryAssetStore(tmp_path).read("../../etc/passwd")
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_bundle_round_trip_and_tamper_detection() -> None:
    import io
    import zipfile

    from simcore.assets import assets_from_directory
    from simcore.bundle import BundleError, read_bundle, write_bundle
    from simcore.mission import load_mission, parse_yaml

    mission = load_mission(parse_yaml((CALISTO / "calisto.mission.yaml").read_text()))
    data = write_bundle(mission, assets_from_directory(CALISTO))
    raw, assets = read_bundle(data)
    assert load_mission(raw) == mission
    assert set(assets) == mission.referenced_assets()

    # Swap an asset's bytes: the hash check must catch it.
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buf, "w") as dst:
        for info in src.infolist():
            body = b"evil" if info.filename.startswith("assets/") else src.read(info)
            dst.writestr(info.filename, body)
    with pytest.raises(BundleError, match="does not match"):
        read_bundle(buf.getvalue())


def test_bundle_rejects_unexpected_paths() -> None:
    import io
    import zipfile

    from simcore.bundle import BundleError, read_bundle

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mission.yaml", "meta: {name: x}\n")
        z.writestr("../../etc/cron.d/evil", "x")
    with pytest.raises(BundleError, match="unexpected"):
        read_bundle(buf.getvalue())
