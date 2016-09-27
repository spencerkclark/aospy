import os
from collections import OrderedDict

user_path = os.path.join(os.getenv('HOME'), 'aospy_user', 'aospy_user')

ETA_STR = 'sigma'
LON_STR = 'lon'
LAT_STR = 'lat'
LON_BOUNDS_STR = 'lon_bounds'
LAT_BOUNDS_STR = 'lat_bounds'
PHALF_STR = 'phalf'
PFULL_STR = 'pfull'
PLEVEL_STR = 'level'
TIME_STR = 'time'
TIME_STR_IDEALIZED = 'year'
TIME_BOUNDS_STR = 'time_bounds'
YEAR_STR = 'year'
BOUNDS_STR = 'bnds'
AVERAGE_T1_STR = 'average_T1'
AVERAGE_T2_STR = 'average_T2'
ZSURF_STR = 'zsurf'
SFC_AREA_STR = 'sfc_area'
LAND_MASK_STR = 'land_mask'
PK_STR = 'pk'
BK_STR = 'bk'
AVERAGE_DT_STR = 'average_DT'

GRID_ATTRS = OrderedDict(
    [(LAT_STR, ('lat', 'latitude', 'LATITUDE', 'y', 'yto')),
     (LAT_BOUNDS_STR, ('latb', 'lat_bnds', 'lat_bounds')),
     (LON_STR, ('lon', 'longitude', 'LONGITUDE', 'x', 'xto')),
     (LON_BOUNDS_STR, ('lonb', 'lon_bnds', 'lon_bounds')),
     (ZSURF_STR, ('zsurf',)),
     (SFC_AREA_STR, ('area', 'sfc_area')),
     (LAND_MASK_STR, ('land_mask',)),
     (PK_STR, ('pk',)),
     (BK_STR, ('bk',)),
     (PHALF_STR, ('phalf',)),
     (PFULL_STR, ('pfull',)),
     (PLEVEL_STR, ('level', 'lev', 'plev')),
     (TIME_STR, ('time',)),
     (AVERAGE_DT_STR, ('average_DT',)),
     (AVERAGE_T1_STR, ('average_T1',)),
     (AVERAGE_T2_STR, ('average_T2',))]
)

del os
