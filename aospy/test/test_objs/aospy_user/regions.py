from aospy.region import Region
# Globe
globe = Region(
    name='globe',
    description='Entire globe',
    lat_bounds=(-90, 90),
    lon_bounds=(0, 360),
    do_land_mask=False
)
# Land.
land = Region(
    name='land',
    description='Land',
    lat_bounds=(-90, 90),
    lon_bounds=(0, 360),
    do_land_mask=True
)
# Ocean.
ocean = Region(
    name='ocean',
    description='Ocean',
    lat_bounds=(-90, 90),
    lon_bounds=(0, 360),
    do_land_mask='ocean'
)
