"""Result storage: a JSON record plus a Parquet trajectory per result."""

from simcore.results.downsample import lttb
from simcore.results.store import (
    ChannelInfo,
    FlightPath,
    Provenance,
    ResultNotFound,
    ResultRecord,
    Series,
    list_records,
    read_flown_mission,
    read_path,
    read_record,
    read_series,
    result_key,
    write_flight,
)

__all__ = [
    "ChannelInfo",
    "FlightPath",
    "Provenance",
    "ResultNotFound",
    "ResultRecord",
    "Series",
    "list_records",
    "lttb",
    "read_flown_mission",
    "read_path",
    "read_record",
    "read_series",
    "result_key",
    "write_flight",
]
