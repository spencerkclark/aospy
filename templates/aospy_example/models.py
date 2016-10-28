from aospy import Model

from .runs import im_example


im = Model(
    name='idealized_moist',
    grid_file_paths=(
        ('data/00010101.precip_monthly.nc',
         'data/im.landmask.nc'),
    ),
    runs=[im_example]
)
