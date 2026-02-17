# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "xarray",
#     "zarr",
#     "rich",
# ]
# ///
import xarray as xr
import zarr

path = "/Users/nathan/fair-mast/data/zarr/30420.zarr"

print(f"Inspecting {path}...")

try:
    # Try opening as a group
    zg = zarr.open_group(path, mode="r")
    print("Zarr Group Structure:")
    print(zg.tree())

    # Try opening a specific dataset with xarray to see metadata
    # e.g. summary
    print("\nOpening 'summary' subgroup with xarray:")
    ds = xr.open_zarr(f"{path}", group="summary", consolidated=False)
    print(ds)

except Exception as e:
    print(f"Error: {e}")
