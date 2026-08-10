# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project State

This repository is in its initial stage. `RainbowConnections.py` is currently empty — no engine, classes, or functions exist yet. `Rules.md` is the game-design specification that the engine in `RainbowConnections.py` is meant to implement. There is no build system, package manifest, test suite, or lint config yet; when these are introduced, this file should be updated with the actual commands.

## Game Rules Summary (from Rules.md)

Rainbow Connections is a board game for 1–3 players where players place **tiles** on **cells** to form **bridges** and win **tokens**; the player with the most tokens at the end wins.

- **Board**: 16 equilateral triangle **cells** arranged into one large triangle. Cells are addressed with coordinates `[x, y]`, each ranging 0–3 (see the "Logic of Checking Adjacent Tiles" section of `Rules.md` for the coordinate scheme and adjacency-checking branches, which distinguish quad centers, quad edges, the central purple quad, and board edges).
- **Tiles**: Triangular, three colors (red, yellow, blue) forming three **sets** of six tiles each. Each tile has three numbered edges (numbers are perpendicular to their edge) and a blank black back. The six numbers per set are grouped as `{1,10,18}, {2,9,17}, {3,12,14}, {4,11,13}, {5,8,16}, {6,7,15}`.
- **Poles**: Placed in the center of a cell; a tile is placed around a pole, and later a bridge end can be set over it.
- **Bridges**: Rectangular pieces in orange, green, purple. Placed over a captured tile to hold tokens; at most 4 bridges may sit on a single tile (only when bridges lead to all adjacent spaces and a circuit is completed).
- **Tokens**: Silver pegs placed on bridges; counted per bridge color at game end to determine the winner.
- **Setup**: Players choose a bridge color, then tiles are shuffled face-down and distributed (18 tiles total: 9 each for 2 players, 6 each for 3 players, drawn one at a time for solitaire). Turn order and color priority are determined by each player placing one tile face-down; highest number goes first, and that tile's color becomes the "high color" (capturing it is worth +3 points). Ties are replayed; three-player ties are broken by Rock/Paper/Scissors.
- **Turn structure**: Place a tile on any vacant cell. If no tiles are adjacent, the turn ends immediately. Otherwise, compare each of the placed tile's three edge numbers against the matching number on the immediately adjacent tile (only the directly facing number, not any of the three) — for each comparison where the placed tile's number is greater, a bridge may be placed between the two tiles, with tokens (per color-priority values) placed on it first. Then check for completed **circuits** (a closed hexagonal ring of six bridges); completing one awards 6 tokens on the completing bridge, plus an extra bridge if the completing player owns more than 3 of the 6 bridges in that circuit.
- **End game**: Once every cell is filled and all bridges placed, bridges are removed and tokens tallied per player color; most tokens wins.

## Architecture Notes for Implementation

When implementing the engine in `RainbowConnections.py`, the adjacency-checking logic outlined at the bottom of `Rules.md` is the key non-obvious piece of game logic — it dispatches differently based on cell position:

- Center of a quad (`x == y`, 4 of 16 cells) → `checkTilesAroundQuadCenter`
- On a board edge (`y == 0`, non-center) → `checkEdge`
- Non-center of the central/purple quad (`x == 0`, non-edge) → `checkTilesAdjacentToNonCentralPurpleQuad`
- All other non-center, non-edge cells → `checkTwoSides`

This branching reflects that cells have different numbers of neighbors (and different adjacency geometry) depending on where they sit in the triangular board, so any engine implementation needs to handle these four cases distinctly rather than using a single uniform adjacency rule.
