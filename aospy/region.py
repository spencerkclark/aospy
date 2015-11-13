"""region.py: Region class and region_inst()."""
from . import LAT_STR, LON_STR
import warnings
import xray


class Region(object):
    """Geographical region."""
    def __init__(self, name='', description='', lon_bounds=[], lat_bounds=[],
                 mask_bounds=[], do_land_mask=False):
        """Instantiate a Region object."""
        self.name = name
        self.description = description
        if lon_bounds and lat_bounds and not mask_bounds:
            self.mask_bounds = [(lat_bounds, lon_bounds)]
        else:
            self.mask_bounds = mask_bounds
        self.do_land_mask = do_land_mask

    def __str__(self):
        return 'Geographical region "' + self.name + '"'

    __repr__ = __str__

    @staticmethod
    def _add_to_mask(data, lat_bounds, lon_bounds):
        """Add mask spanning given lat-lon rectangle."""
        mask_lat = ((data[LAT_STR] > lat_bounds[0]) &
                    (data[LAT_STR] < lat_bounds[1]))
        return mask_lat & ((data[LON_STR] > lon_bounds[0]) &
                           (data[LON_STR] < lon_bounds[1]))

    def make_mask(self, data):
        """Construct the mask that defines this region."""
        # For each set of bounds add to the conditional.
        mask = False
        for lat_bounds, lon_bounds in self.mask_bounds:
            mask |= self._add_to_mask(data, lat_bounds, lon_bounds)
        return mask

    def mask_var(self, data):
        """Mask the data of the given variable outside the region."""
        return data.where(self.make_mask(data))

    @staticmethod
    def _get_land_mask(data, do_land_mask):
        try:
            land_mask = data.land_mask
        except AttributeError:
            # S. Hill 2015-10-14: Eventually aospy will have a built-in land
            # mask array that it can use in case the object doesn't have one
            # of its own.  For now the object /must/ have one.
            warnings.warn("Land mask not found.  No land mask will be applied.")
            return 1
        if do_land_mask in (True, 'land'):
            return land_mask
        if do_land_mask == 'ocean':
            return 1. - land_mask
        if do_land_mask in ('strict_land', 'strict_ocean'):
            raise NotImplementedError
        return 1

    @staticmethod
    def _sum_over_lat_lon(arr):
        """Sum an array over the latitude and longitude dimensions."""
        return arr.sum(LAT_STR).sum(LON_STR)

    def ts(self, data):
        """Create time-series of region-average data."""
        data_masked = self.mask_var(data)
        sfc_area = data.sfc_area
        land_mask = self._get_land_mask(data, self.do_land_mask)
        weights = self._sum_over_lat_lon((self.mask_var(sfc_area)*land_mask))
        return (self._sum_over_lat_lon(data_masked*sfc_area*land_mask) /
                weights)

    def av(self, data):
        """Time average of region-average time-series."""
        ts_ = self.ts(data)
        if 'year' not in ts_.coords:
            return ts_
        return ts_.mean('year')

    def std(self, data):
        """Standard deviation of region-average time-series."""
        ts_ = self.ts(data)
        if 'year' not in ts_.coords:
            return ts_
        return ts_.std('year')
