# Tile rotation inspection scene (prepared, push when the GM client is connected)

Open the Foundry GM tab on Arcturus (http://VEGA:30000) so `curl -s http://127.0.0.1:3030/health` shows `moduleConnected: true`, then:

```
python illustrator/generators/tile_rotation_inspect.py push --dry-run     # check
python illustrator/generators/tile_rotation_inspect.py push               # creates scene "ZZ Tile Rotation Inspect", 6 tiles, label drawings
```

Equivalent manual form (tiles only, no label drawings):
`python illustrator/generators/foundry_push.py push-models --placements illustrator/out/tile_rotation_inspect/placements.json --scene-name "ZZ Tile Rotation Inspect" --set-name inspect`

Scene: 60 x 40 squares of 5 ft (6000 x 4000 px, 20 px/ft). Marker model: L-shaped building, arms east and north from the SW elbow; RED walls face model +Y (north), BLUE east, WHITE south, GREEN west, yellow roof arrow and magenta post at the north end.

Tiles: rotation 0, 90, 180, 270 at px (1000|2200|3400|4600, 800); known position tile (rotation 0) centred at (100, 150) ft = px (2000, 3000); 10 ft cube at the scene centre (150, 100) ft = px (3000, 2000), edge should span exactly 2 grid squares.

Look at: which way the RED wall / yellow arrow points at each rotation. If rotation 0 shows the arrow pointing to the top of the screen, keep `foundry.tile_rotation_deg: 0`; if rotation 180 does, set it to 180 in the manifest (worldpack.py).

Delete: `python illustrator/generators/foundry_push.py delete-scene --scene-uuid <uuid>`
