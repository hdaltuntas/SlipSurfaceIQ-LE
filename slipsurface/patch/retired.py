"""Files earlier releases shipped that later releases dropped.

The updater normally never deletes files in ``examples/`` or ``docs/``, because
users keep their own projects there. A file listed here is removed during an
update only when its SHA-256 equals one of the published versions, so a copy
the user edited is kept. Generated from the release tags; extend it when a
release drops a file from those folders.
"""

RETIRED_FILES: dict[str, tuple[str, ...]] = {
    "examples/anchored_cut.slp.json": (
        "bea9697da59073495a6c7564d36b5b7c48d4cd1db4a4738dacdb47dce0a4dea6",
    ),
    "examples/ankrajli_yarma.slp.json": (
        "bfde342825fbbab7e31197b1dd1b03da118491f43467b2ac12b3da327e7dcd36",
    ),
    "examples/arai_tagyo_layered_circular.slp.json": (
        "748b78f3fd330dc39051e7fde7cd91d3c9870133865c52271af738e074778f1e",
    ),
    "examples/arai_tagyo_layered_noncircular.slp.json": (
        "0fee217c5fcedd995bfda9a34457599bd3b19e095e806395966d9ad81ac62e8a",
    ),
    "examples/basit_sev.slp.json": (
        "ca311e62f2143b138861e7022f3bf24758e5f604f523c210e1677d35af882e95",
    ),
    "examples/borges_cardoso_case2.slp.json": (
        "18756cf6c78f69e2cc51739c12bafb2e9c4de6375f4fdd94f525df9b59b6e7fe",
        "99b64a43b9a0bb6a46849718d68af41d934e67207ff0f18629994a0f2e4518ba",
    ),
    "examples/civili_puskurtme_betonlu_yarma.slp.json": (
        "0f82fe6e75743dee3d214bc70dbeea29eca9ae158647157ca3fe1f5002c61bd2",
    ),
    "examples/gerilme_catlakli_sev.slp.json": (
        "a9f26413d68a7578615e25ab6341840486b34c35d540c9aac9c74cdfc7aa1601",
    ),
    "examples/katmanli_yass.slp.json": (
        "b6a22c138be88242e128438ae37e535087c05935dc58272c77daab68c8eb7a35",
    ),
    "examples/layered_water_table.slp.json": (
        "32868c7f56cfdeb47f7289628039ea579856e3c7ae2f8593a444056f86332c5c",
    ),
    "examples/power_law.slp.json": (
        "7d9821c13e98f5ff35a08c52e8a72412f91dba58eb63f2bd36e0017ae98f63c4",
        "f4b646607498c77030e83ab80d33e9590082b1533c61ad4ec305d545e482ff05",
    ),
    "examples/scripted_slope.py": (
        "d7741df8acd629df0989d5e2401798c26633e388b94e1c85abcb942b0083b358",
        "e4d80dcc5f0cb4d45d88a52d97fb9580f874cca84456ac7011712cdd5cf060e1",
    ),
    "examples/seismic.slp.json": (
        "9b95ea4d244110960225255c7650f1b4a7599c1142804dde939c91bac802e996",
        "d94452395efe8255ad9ee005fb3cf535364f2f0a231f1d48650bf8058540a141",
    ),
    "examples/simple_slope.slp.json": (
        "216ca80e9e1c7a57faaf5fb57f26348327069521b48ddd9f6c87524ea2009d91",
    ),
    "examples/soil_nail_shotcrete.slp.json": (
        "e0d769d0e9d1f2f1fa4345501e564e41450924513b3fa11164ae208ddb104938",
    ),
    "examples/tension_crack.slp.json": (
        "c2f6ddb04ec3deed5b04c6bbafb37bc7749e807a64f5262e645b04d3d2cbf52b",
    ),
    "examples/undrained_clay.slp.json": (
        "368fdc3fd73448d3e0a5c0547b7daae2f8d88dfe5d380b7b3374c07a788347d6",
        "c1c6dbed826f04caeff2dab9909bf40fc3fb8f698fb4c19e16ee15a4559b42a3",
    ),
}
