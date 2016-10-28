from aospy import Run

files = ['{:04d}0101.precip_monthly.nc'.format(year) for year in range(1, 7)]
im_example = Run(
    name='im_example',
    description=(
        'Control simulation of the idealized moist model'
    ),
    data_in_direc='data',
    data_in_dir_struc='one_dir',
    data_in_files={'monthly': {'condensation_rain': files,
                               'convection_rain': files}}
)
