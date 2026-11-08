# Third-party assets (PRIVATE USE ONLY)

**Remove everything in this folder before any public release of this repository, and purge it from git history** (for example with `git filter-repo --path third_party --invert-paths`). The repository is private and these files must never be distributed.

## baileywiki/
Converted copies (npz meshes and PNG textures) of models from the user's licensed Baileywiki 3D tree packs, read from the Foundry data folder (`\VEGA\C\FoundryVTT resources\Data`). Used by `illustrator/generators/foliage_import.py` as extra foliage species (European beech, ash, young ash, two bushes). Without this folder the procedural foliage still works; the imported species are simply skipped.
