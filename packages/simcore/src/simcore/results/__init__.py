"""Result storage: a JSON record plus a Parquet trajectory per result."""

from simcore.results.downsample import lttb
from simcore.results.store import (
    ChannelInfo,
    Provenance,
    ResultNotFound,
    ResultRecord,
    Series,
    read_record,
    read_series,
    result_key,
    write_flight,
)

__all__ = [
    "ChannelInfo",
    "Provenance",
    "ResultNotFound",
    "ResultRecord",
    "Series",
    "lttb",
    "read_record",
    "read_series",
    "result_key",
    "write_flight",
]
