from aospy.units import Units
from aospy.constants import seconds_in_day

unitless = Units(units='')
K = Units(units='K')
m = Units(units='m')
m2 = Units(units=r'm$^2$')
latlon = Units(units=r'$^\circ$')
m_s1 = Units(
    units=r'm s$^{-1}$',
    vert_int_units=r'kg m$^{-1}$ s$^{-1}$'
)
kg_s1 = Units(
    units=r'kg s$^{-1}$',
    plot_units=r'kg day$^{-1}$',
    plot_units_conv=seconds_in_day
)
W_m2 = Units(
    units=r'W m$^{-2}$',
    vert_int_units=r''
)
Pa = Units(
    units=r'Pa',
    plot_units=r'hPa',
    plot_units_conv=1e-2
)
hPa = Units(
    units=r'hPa',
)
