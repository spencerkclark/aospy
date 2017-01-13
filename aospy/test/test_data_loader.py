#!/usr/bin/env python
"""Test suite for aospy.data_loader module."""
import unittest
from datetime import datetime
import xarray as xr
import numpy as np

from aospy.data_loader import (DataLoader, DictDataLoader, GFDLDataLoader,
                               OneDirDataLoader)
from data.objects.examples import condensation_rain, convection_rain, precip
from aospy import (LAT_STR, LON_STR, TIME_STR, TIME_BOUNDS_STR, NV_STR,
                   SFC_AREA_STR)


class AospyDataLoaderTestCase(unittest.TestCase):
    def setUp(self):
        self.DataLoader = DataLoader()
        self.generate_file_set_args = dict(
            var=condensation_rain, start_date=datetime(2000, 1, 1),
            end_date=datetime(2002, 12, 31), domain='atmos',
            intvl_in='monthly', dtype_in_vert='sigma', dtype_in_time='ts',
            intvl_out=None)
        time_bounds = np.array([[0, 31], [31, 59], [59, 90]])
        nv = np.array([0, 1])
        time = np.array([15, 46, 74])
        data = np.zeros((3, 1, 1))
        lat = [0]
        lon = [0]
        self.ALT_LAT_STR = 'LATITUDE'
        self.var_name = 'a'
        ds = xr.DataArray(data,
                          coords=[time, lat, lon],
                          dims=[TIME_STR, self.ALT_LAT_STR, LON_STR],
                          name=self.var_name).to_dataset()
        ds[TIME_BOUNDS_STR] = xr.DataArray(time_bounds,
                                           coords=[time, nv],
                                           dims=[TIME_STR, NV_STR],
                                           name=TIME_BOUNDS_STR)
        units_str = 'days since 2000-01-01 00:00:00'
        ds[TIME_STR].attrs['units'] = units_str
        ds[TIME_BOUNDS_STR].attrs['units'] = units_str
        self.ds = ds

    def tearDown(self):
        pass


class TestDataLoader(AospyDataLoaderTestCase):
    def test_rename_grid_attrs(self):
        assert LAT_STR not in self.ds
        assert self.ALT_LAT_STR in self.ds
        ds = self.DataLoader.rename_grid_attrs(self.ds)
        assert LAT_STR in ds

    def test_set_grid_attrs_as_coords(self):
        ds = self.DataLoader.rename_grid_attrs(self.ds)
        sfc_area = ds[self.var_name].isel(**{TIME_STR: 0}).drop(TIME_STR)
        ds[SFC_AREA_STR] = sfc_area

        # Assert that SFC_AREA_STR is not initially carried by self.var_name
        assert SFC_AREA_STR not in ds[self.var_name]

        # Apply method, then assert that SFC_AREA_STR is carried
        ds = self.DataLoader.set_grid_attrs_as_coords(ds)
        assert SFC_AREA_STR in ds[self.var_name]

    def test_sel_var(self):
        time = np.array([0, 31, 59]) + 15
        data = np.zeros((3))
        ds = xr.DataArray(data,
                          coords=[time],
                          dims=[TIME_STR],
                          name=convection_rain.name).to_dataset()
        condensation_rain_alt_name, = condensation_rain.alt_names
        ds[condensation_rain_alt_name] = xr.DataArray(data, coords=[ds.time])
        result = self.DataLoader._sel_var(ds, convection_rain)
        self.assertEqual(result.name, convection_rain.name)

        result = self.DataLoader._sel_var(ds, condensation_rain)
        self.assertEqual(result.name, condensation_rain.name)

        with self.assertRaises(KeyError):
            self.DataLoader._sel_var(ds, precip)


class TestDictDataLoader(TestDataLoader):
    def setUp(self):
        super(TestDictDataLoader, self).setUp()
        file_map = {'monthly': ['a.nc']}
        self.DataLoader = DictDataLoader(file_map)

    def test_generate_fileset(self):
        result = self.DataLoader._generate_file_set(
            **self.generate_file_set_args)
        expected = ['a.nc']
        self.assertEquals(result, expected)

        with self.assertRaises(KeyError):
            self.generate_file_set_args['intvl_in'] = 'daily'
            result = self.DataLoader._generate_file_set(
                **self.generate_file_set_args)


class TestOneDirDataLoader(TestDataLoader):
    def setUp(self):
        super(TestOneDirDataLoader, self).setUp()
        file_map = {'monthly': {'condensation_rain': ['a.nc']}}
        self.DataLoader = OneDirDataLoader(file_map)

    def test_generate_fileset(self):
        result = self.DataLoader._generate_file_set(
            **self.generate_file_set_args)
        expected = ['a.nc']
        self.assertEqual(result, expected)

        with self.assertRaises(KeyError):
            self.generate_file_set_args['var'] = convection_rain
            result = self.DataLoader._generate_file_set(
                **self.generate_file_set_args)


class TestGFDLDataLoader(TestDataLoader):
    def setUp(self):
        super(TestGFDLDataLoader, self).setUp()
        self.DataLoader = GFDLDataLoader()

if __name__ == '__main__':
    unittest.main()
