"""Test library of functions for use in aospy.
"""
import numpy as np
import xray

from aospy.constants import grav, r_e
from aospy.utils import (level_thickness, to_pascal, to_radians,
                         integrate, int_dp_g, dp_from_ps, vert_coord_name)


def dp(ps, bk, pk, arr):
    """Pressure thickness of hybrid coordinate levels from surface pressure."""
    return dp_from_ps(bk, pk, ps, arr[PFULL_STR])


def msf(vcomp, dp):
    """ Returns the mean meridional mass streamfunction. We take
    the zonal mean first and then take the time mean.
    """
    try:
        dp = dp.mean('lon')
    except:
        pass
    dp = to_pascal(dp)
    v = vert_coord_name(dp)

    msf_ = vcomp.mean('lon').copy(deep=True)
    integrand = dp * vcomp.mean('lon')
    for k in range(len(dp[v])):
        msf_[{v: k}] = integrand.isel(**{v: slice(k, None)}).sum(dim=v)
    msf_ *= 2. * r_e.value * np.pi * np.cos(np.deg2rad(vcomp.lat)) / grav.value
    return msf_


def pfull(p):
    """ Returns the pressure at the level midpoints."""
    return to_pascal(p)
