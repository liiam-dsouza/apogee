"""``.mission.zip`` bundles: the mission YAML plus every asset it references.

A bundle works on a laptop that has never seen the project. Inside:
``mission.yaml`` and ``assets/<sha256>``. Reading verifies every hash.
"""

import io
import re
import zipfile
from typing import Any

from simcore.assets import AssetStore, sha256_hex
from simcore.mission import Mission, dump_yaml, parse_yaml

MAX_BUNDLE_BYTES = 100 * 1024 * 1024
_ASSET_NAME = re.compile(r"^assets/([0-9a-f]{64})$")


class BundleError(ValueError):
    """The zip is not a usable mission bundle."""


def write_bundle(mission: Mission, assets: AssetStore) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("mission.yaml", dump_yaml(mission))
        for sha in sorted(mission.referenced_assets() | set(mission.assets)):
            z.writestr(f"assets/{sha}", assets.read(sha))
    return buf.getvalue()


def read_bundle(data: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Return the raw mission dict (unvalidated) and its assets by hash."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise BundleError("not a zip file") from e
    with z:
        infos = z.infolist()
        if sum(i.file_size for i in infos) > MAX_BUNDLE_BYTES:
            raise BundleError("bundle is too large when unpacked")
        names = {i.filename for i in infos if not i.is_dir()}
        if "mission.yaml" not in names:
            raise BundleError("no mission.yaml in the bundle")
        assets: dict[str, bytes] = {}
        for name in names - {"mission.yaml"}:
            match = _ASSET_NAME.match(name)
            if not match:
                raise BundleError(f"unexpected file in bundle: {name}")
            content = z.read(name)
            if sha256_hex(content) != match.group(1):
                raise BundleError(f"{name} does not match its hash")
            assets[match.group(1)] = content
        mission = parse_yaml(z.read("mission.yaml").decode())
    return mission, assets
