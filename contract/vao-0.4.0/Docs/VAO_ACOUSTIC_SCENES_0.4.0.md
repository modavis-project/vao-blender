# VAO spatial/acoustic implementation notes 0.4.0

This document is informative. The normative conformance contracts are the [Spatial profile](VAO_SPATIAL_PROFILE_0.4.0.md), [Acoustics profile](VAO_ACOUSTICS_PROFILE_0.4.0.md), main [standard](VAO_STANDARD_0.4.0.md), schemas, and conformance document.

AES69-SOFA, WAVE/FLAC, HDF5, netCDF, Zarr, glTF, IFC, and ADM remain external realization formats. VAO binds their exact bytes and records coordinate, measurement, provenance, and cross-file relationships; it does not override their internal standards.

A moving source, receiver, performer, camera, listener, or sensor uses an exact trajectory realization, Track, and Timebase when motion is scientifically interpreted. A geodetic location should be converted through a documented/provenance-bearing operation into a suitable local projected or Cartesian frame before affine geometry transforms, orientations, or acoustic rendering are applied.
