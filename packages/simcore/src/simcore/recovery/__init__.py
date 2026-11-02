"""Recovery sizing: steady descent rates under each device, and the CdS a rate needs."""

from simcore.recovery.descent import DeviceDescent, cd_s_for_rate, descent_rate, descent_table

__all__ = ["DeviceDescent", "cd_s_for_rate", "descent_rate", "descent_table"]
