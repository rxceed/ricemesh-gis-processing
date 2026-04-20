# Takes the polygon segmentation GeoJSON and produces a second GeoJSON
# where each feature is the axis-aligned bounding box of that segment.
# Both the original polygon and its bbox are stored as attributes.

import json
from pathlib import Path
import geopandas as gpd
import rasterio
from shapely.geometry import box as shapely_box


def export_bboxes(
    segments_geojson: Path,
    reference_tif: Path,       # used to detect and reproject CRS
    output_geojson: Path,
    min_area_ha: float = 0.005,    # 50m² minimum — removes noise
    max_area_ha: float = 20.0,     # 20ha maximum — removes over-merged blobs
    min_compactness: float = 0.05, # very permissive — drone plots can be narrow
) -> gpd.GeoDataFrame:
    """
    Convert segment polygons to bounding box polygons and save as GeoJSON.

    Why bbox polygons instead of convex hull?
    Bounding boxes are the simplest representation for "field extent" and
    integrate naturally with the digital twin's grid-based cell model —
    you can directly map a bbox to a set of grid cells.

    Output GeoJSON attributes per feature:
        plot_id      : integer segment ID from SAM3
        bbox_minx    : bounding box in CRS units
        bbox_miny
        bbox_maxx
        bbox_maxy
        area_ha      : area of the ORIGINAL polygon in hectares
        width_m      : bbox width in metres
        height_m     : bbox height in metres
        compactness  : Polsby-Popper score of original polygon
    """
    output_geojson.parent.mkdir(parents=True, exist_ok=True)

    # Load segments and reproject to match the raster CRS
    with rasterio.open(reference_tif) as src:
        raster_crs = src.crs

    gdf = gpd.read_file(segments_geojson)
    if gdf.crs is None or gdf.crs != raster_crs:
        gdf = gdf.set_crs(raster_crs, allow_override=True)

    utm_crs = gdf.estimate_utm_crs()
    gdf_utm = gdf.to_crs(utm_crs)
    utm_epsg = utm_crs.to_epsg() 

    # Compute attributes on the original polygons
    gdf_utm["area_ha"]    = gdf_utm.geometry.area / 10_000
    gdf_utm["perimeter"]  = gdf_utm.geometry.length
    gdf_utm["compactness"] = gdf_utm.apply(
        lambda r: (4 * 3.14159 * r.area_ha * 10_000) / (r.perimeter ** 2 + 1e-8),
        axis=1,
    )

    # Filter
    initial = len(gdf_utm)
    gdf_utm = gdf_utm[
        (gdf_utm["area_ha"] >= min_area_ha) &
        (gdf_utm["area_ha"] <= max_area_ha) &
        (gdf_utm["compactness"] >= min_compactness)
    ].copy()
    print(f"Segments after filter: {len(gdf_utm)} / {initial}")

    # Build bbox polygon per segment
    bboxes = []
    for idx, row in gdf_utm.iterrows():
        minx, miny, maxx, maxy = row.geometry.bounds
        bbox_geom = shapely_box(minx, miny, maxx, maxy)
        bboxes.append({
            "geometry": bbox_geom,
            "plot_id":  int(row.get("value", idx)),
            "bbox_minx": round(minx, 4),
            "bbox_miny": round(miny, 4),
            "bbox_maxx": round(maxx, 4),
            "bbox_maxy": round(maxy, 4),
            "area_ha":   round(row["area_ha"], 4),
            "width_m":   round(maxx - minx, 2),
            "height_m":  round(maxy - miny, 2),
            "compactness": round(row["compactness"], 4),
        })

    bbox_gdf = gpd.GeoDataFrame(bboxes, crs=f"EPSG:{utm_epsg}")

    # Save in WGS84 (GeoJSON standard)
    bbox_gdf_wgs = bbox_gdf.to_crs(epsg=4326)
    bbox_gdf_wgs.to_file(output_geojson, driver="GeoJSON")

    print(f"Bounding box GeoJSON saved → {output_geojson}")
    print(f"  {len(bbox_gdf_wgs)} farm plot bounding boxes")
    return bbox_gdf_wgs