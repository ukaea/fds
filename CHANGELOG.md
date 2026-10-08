# Changelog

## [0.0.7](https://github.com/ukaea/fds/compare/v0.0.6...v0.0.7) (2026-10-08)


### Features

* Accept Entra ID app roles as scopes ([7ff7bcd](https://github.com/ukaea/fds/commit/7ff7bcd206648302ef4acdacf01ddb7144def18d))


### Bug Fixes

* Accept no scopes from an issuer that lists none ([#152](https://github.com/ukaea/fds/issues/152)) ([d6c6aeb](https://github.com/ukaea/fds/commit/d6c6aeb4147e4300e7b38edd41fb7f5dda74d27e))
* Check read access on a collection's activity ([d0f8e88](https://github.com/ukaea/fds/commit/d0f8e883b49fe8ea2a1d05a0ffb76ec2e7405b8b))
* Choose the storage provider by URL scheme as well as endpoint ([#167](https://github.com/ukaea/fds/issues/167)) ([9aaa5e4](https://github.com/ukaea/fds/commit/9aaa5e4cf3937243823c2d8f652f4b295de92c07))
* Drop the per-distribution access level ([aa0d2be](https://github.com/ukaea/fds/commit/aa0d2be5817c110ca2edc696ce9fa93ad294c272))
* Leave npm out of the UI runtime image ([#143](https://github.com/ukaea/fds/issues/143)) ([b19b9a4](https://github.com/ukaea/fds/commit/b19b9a4033b7aeccd2c77e4bcb00d9852ff8d1f5))
* Let CodeQL parse the base service ([#140](https://github.com/ukaea/fds/issues/140)) ([767cd1d](https://github.com/ukaea/fds/commit/767cd1dfed5e90cf8ef39e6e66f47869c9667d69))
* Name activity link removals in the audit log ([#173](https://github.com/ukaea/fds/issues/173)) ([4f6e7f3](https://github.com/ukaea/fds/commit/4f6e7f37d7f20aabada917467580bf81aa94dc94))
* Record restricted shot reads in the audit trail ([#159](https://github.com/ukaea/fds/issues/159)) ([fe159a6](https://github.com/ukaea/fds/commit/fe159a65cb29228eae43f8aacb1694dda7a128ee))
* Return Azure and GCS storage options for single datasets ([#166](https://github.com/ukaea/fds/issues/166)) ([6b2a64d](https://github.com/ukaea/fds/commit/6b2a64d03006d5bb009ece2329f352397e3aa416))
* Upgrade Alpine packages in the UI image ([#180](https://github.com/ukaea/fds/issues/180)) ([69b03ef](https://github.com/ukaea/fds/commit/69b03efabd3c4ac11edb26d17cbe91f25c94a2bd))
* Vend Azure credentials for abfss:// and account-named URLs ([#168](https://github.com/ukaea/fds/issues/168)) ([9b4aa61](https://github.com/ukaea/fds/commit/9b4aa615515040061a846da4fa2b86729c045a02))

## [0.0.6](https://github.com/ukaea/fds/compare/v0.0.5...v0.0.6) (2026-10-06)


### Features

* Draw the provenance graph from the published JSON-LD ([#131](https://github.com/ukaea/fds/issues/131)) ([a9284fa](https://github.com/ukaea/fds/commit/a9284fab82fd143bc137aa1e291a76f04e5db8ca))
* Let a distribution name its group within a file ([#136](https://github.com/ukaea/fds/issues/136)) ([8205090](https://github.com/ukaea/fds/commit/82050904be380d6921e15ad7c0fe520c3026f2c3))
* Load the zarr viewer faster and draw heatmaps to scale ([#135](https://github.com/ukaea/fds/issues/135)) ([b73bfd4](https://github.com/ukaea/fds/commit/b73bfd48cf5a6960d892277d504ee385e3c8d026))

## [0.0.5](https://github.com/ukaea/fds/compare/v0.0.4...v0.0.5) (2026-10-05)


### Features

* Find a shot by ID on the device page ([#123](https://github.com/ukaea/fds/issues/123)) ([efb6898](https://github.com/ukaea/fds/commit/efb68989fd53295fec38c85815896908218aaca4))
* Record a persistent identifier on citable records ([#128](https://github.com/ukaea/fds/issues/128)) ([a36ea37](https://github.com/ukaea/fds/commit/a36ea3746cd2d422713c3e5c8b22775c48bc7e01))
* Rework the dataset page ([#130](https://github.com/ukaea/fds/issues/130)) ([9b528cd](https://github.com/ukaea/fds/commit/9b528cd39a86e7f53130f45ca49e25f4a13354ad))
* Say why a shot cannot be shown ([#126](https://github.com/ukaea/fds/issues/126)) ([6ba35cd](https://github.com/ukaea/fds/commit/6ba35cd01f8baf2dcfd8289a61c60a3a9cca7aa3))


### Bug Fixes

* Match the shot property filter only on readable shots ([#125](https://github.com/ukaea/fds/issues/125)) ([f2e34a5](https://github.com/ukaea/fds/commit/f2e34a5d846c8838ae53b126cf2588c5eb70b003))
* Update records with PATCH, not PUT ([#129](https://github.com/ukaea/fds/issues/129)) ([bb1a314](https://github.com/ukaea/fds/commit/bb1a314e79de2a67611b1dc187d5d0c6782c2b49))

## [0.0.4](https://github.com/ukaea/fds/compare/v0.0.3...v0.0.4) (2026-10-04)


### Features

* Add the FDS logo and brand colours to the UI and docs ([#121](https://github.com/ukaea/fds/issues/121)) ([8f97995](https://github.com/ukaea/fds/commit/8f97995742e6db2862d57daa0decdce0f29d67d9))
* Show member collections and rework the collection page ([#118](https://github.com/ukaea/fds/issues/118)) ([a21d6c4](https://github.com/ukaea/fds/commit/a21d6c42dbaa92ca3b3b1ebb7b4822035d96f649))

## [0.0.3](https://github.com/ukaea/fds/compare/v0.0.2...v0.0.3) (2026-10-04)


### Features

* Apply read access in the query so pages are exact ([#117](https://github.com/ukaea/fds/issues/117)) ([029972e](https://github.com/ukaea/fds/commit/029972e686d8d765a51aceba0cd3df3d71c5aaba))
* Bound list paging parameters ([#114](https://github.com/ukaea/fds/issues/114)) ([4ad4fb4](https://github.com/ukaea/fds/commit/4ad4fb4432ef06ddad732b8a35c1d03074b0c2aa))
* List collections by scope in the UI ([#116](https://github.com/ukaea/fds/issues/116)) ([43d1f9d](https://github.com/ukaea/fds/commit/43d1f9d942bc998c4a62a740a58235686f5c8aa7))
* Page collection membership ([#112](https://github.com/ukaea/fds/issues/112)) ([540e01d](https://github.com/ukaea/fds/commit/540e01dad191c7d962c20a14f0a81979e6b0a75a))

## [0.0.2](https://github.com/ukaea/fds/compare/v0.0.1...v0.0.2) (2026-10-02)


### Features

* Publish FDS's own dates on a catalogue record ([#102](https://github.com/ukaea/fds/issues/102)) ([4239fd3](https://github.com/ukaea/fds/commit/4239fd35452f8dc0714e8e054a28e95c0dc03dcb))
* Side-panel filters, descriptions, endless scroll and a theme switch ([#104](https://github.com/ukaea/fds/issues/104)) ([7c9efca](https://github.com/ukaea/fds/commit/7c9efca17163dabfa69713b1470b55431276909c))


### Bug Fixes

* Keep when FDS listed a record out of callers' hands ([#103](https://github.com/ukaea/fds/issues/103)) ([8c96f39](https://github.com/ukaea/fds/commit/8c96f39657a4fa2e34d02fd4ee01eef4a47c8bf9))
* Store and return datetimes in UTC ([#99](https://github.com/ukaea/fds/issues/99)) ([ea8e560](https://github.com/ukaea/fds/commit/ea8e560de461c7669fe8d3129d4bac3aea8cc0b3))
