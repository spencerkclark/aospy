#!/usr/bin/env python
"""Test suite for aospy.data_loader module."""
import unittest
import os
import xarray as xr
import numpy as np
import pandas as pd

from aospy.data_loader import DictDataLoader
from test_objs.variables import t_surf, temp, bk
from aospy import LAT_STR, LON_STR, TIME_STR, AVERAGE_T1_STR, AVERAGE_T2_STR


class AospyDataLoaderTestCase(unittest.TestCase):
    def setUp(self):
        # Create some synthetic data.
        if not os.path.exists('test_data'):
            os.makedirs('test_data')

        average_T1 = pd.date_range(start='2000-01-01',
                                   end='2000-03-31', freq='MS')
        average_T2 = pd.date_range(start='2000-01-01',
                                   end='2000-03-31', freq='M')
        time = average_T1 + pd.tseries.offsets.DateOffset(days=15)
        lat = [0]
        lon = [0]
        data = np.ones((3, 1, 1))
        self.ALT_LAT_STR = 'LATITUDE'
        ds = xr.DataArray(data, coords=[time, lat, lon],
                          dims=[TIME_STR, self.ALT_LAT_STR, LON_STR],
                          name=t_surf.name).to_dataset()
        ds[AVERAGE_T1_STR] = xr.DataArray(average_T1, coords=[ds[TIME_STR]])
        ds[AVERAGE_T2_STR] = xr.DataArray(average_T2, coords=[ds[TIME_STR]])
        ds.set_coords([AVERAGE_T1_STR, AVERAGE_T2_STR], inplace=True)

        temp_alt_name, = temp.alt_names
        ds[temp_alt_name] = ds[t_surf.name]

        ds.isel(**{TIME_STR: 0}).to_netcdf('test_data/2000-01-01_monthly.nc')
        ds.isel(**{TIME_STR: 1}).to_netcdf('test_data/2000-02-01_monthly.nc')
        ds.isel(**{TIME_STR: 2}).to_netcdf('test_data/2000-03-01_monthly.nc')

        file_dict = {'monthly': ['test_data/2000-01-01_monthly.nc',
                                 'test_data/2000-02-01_monthly.nc',
                                 'test_data/2000-03-01_monthly.nc']}
        self.dl = DictDataLoader(file_dict)

    def tearDown(self):
        os.remove('test_data/2000-01-01_monthly.nc')
        os.remove('test_data/2000-02-01_monthly.nc')
        os.remove('test_data/2000-03-01_monthly.nc')


class TestDataLoader(AospyDataLoaderTestCase):
    def test_sel_var(self):
        file_set = self.dl.file_map['monthly']
        result = self.dl._sel_var(file_set, t_surf)
        self.assertEqual(result.name, t_surf.name)

        # Test a variable with an alternative name in the files
        result = self.dl._sel_var(file_set, temp)
        self.assertEqual(result.name, temp.name)

        # Test a variable that does not exist in the files
        with self.assertRaises(KeyError):
            self.dl._sel_var(file_set, bk)

    def test_sel_time_avg_data(self):
        file_set = self.dl.file_map['monthly']
        da = self.dl._sel_var(file_set, t_surf)

        start_date = np.datetime64('2000-01-01')
        start_date_bad = np.datetime64('1999-12-31')
        end_date = np.datetime64('2000-02-01')
        end_date_bad = np.datetime64('2000-04-01')

        with self.assertRaises(AssertionError):
            result = self.dl._sel_time(da, start_date_bad, end_date)

        with self.assertRaises(AssertionError):
            result = self.dl._sel_time(da, start_date, end_date_bad)

        expected = da.sel(**{TIME_STR: slice(start_date, end_date)})
        result = self.dl._sel_time(da, start_date, end_date)
        assert result.equals(expected)

    def test_establish_grid_attrs(self):
        file_set = self.dl.file_map['monthly']

        # Open file_set, but don't preprocess
        ds = xr.open_mfdataset(file_set, concat_dim=TIME_STR)

        # Add a sfc_area attribute, indexed by 'lat' on 'lon'
        ds['sfc_area'] = ds[t_surf.name].isel(**{TIME_STR: 0}).drop(TIME_STR)

        # Establish that 'sfc_area' is not initially carried with 't_surf'
        assert 'sfc_area' not in ds[t_surf.name]

        # Establish the coordinate name for 'lat' is wrong initially
        assert self.ALT_LAT_STR in ds
        assert LAT_STR not in ds

        result = self.dl.establish_grid_attrs(ds)
        assert LAT_STR in result
        assert 'sfc_area' in result[t_surf.name]

    def test_sel_time_inst_data(self):
        # TODO
        pass

if __name__ == '__main__':
    unittest.main()
