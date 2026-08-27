# VAO 0.3.2 visual-acoustic integration fixture

`acousticrooms-bathrooms-idx-0.vao` is the canonical VAO-Blender fixture for the VAO 0.3.2 visual-acoustic update.

- Carrier SHA-256: `54aef8656162f485a0c4aa37dca56accc909284db4f746b33f85500749da2286`
- Carrier size: 1,754,708 bytes
- Manifest SHA-256: `8bf67a8240db327d481bcc23f532ba2c198c8a886f5659efcab909a9273ab652`
- Payload: 8 files, 1,722,650 bytes
- Upstream: AcousticRooms commit `3c87318a0188e1b441fc75846d54b487ca215fbb`
- License for incorporated AcousticRooms data: CC BY 4.0
- Selected room/pair: `Bathrooms_idx_0`, `S000_R0011`

The carrier contains the upstream OBJ, a Blender 5.1.1 GLB visualization derivative, a mono 22,050 Hz hybrid RIR, exact source/receiver XYZ metadata, simulation configuration, upstream README/license, and fixture provenance.

It is copied byte-for-byte from:

`/Users/dominik/Desktop/Projects/orgrec/dist/acousticrooms-bathrooms-idx-0.vao`

Do not regenerate or normalize the fixture silently. Any replacement must be validated with the pinned VAO 0.3.2 reference implementation, receive a new checksum/oracle, and retain the upstream attribution evidence.

Expected Blender behavior is defined in `expected-inspection.json`. Import must use manifest/carrier IDs and coordinate transforms, not archive filenames or Blender object names.
