## Welcome to Rainbow Connections
- In Rainbow Connections, place **tiles** on **cells** to build **bridges** and win **tokens**. At the end of gameplay, the player with the most tokens wins.  Rainbow Connections can be played with one, two, or three players.

## 0) Board Description
### Cells
- The standard Rainbow Connections board consists of 16 equilateral triangles called **cells** arranged to create a larger equilateral triangle. Cells are like squares on a chess board, they designate where a piece will be placed. 
- The standard state of a board cell is empty.
- We will represent each cell in the engine using [x,y], where x and y range from 0 to 3. as shown in this image.
![[Pasted image 20260806203639.png]]
### Tiles
- **Tiles** are triangular pieces with a number on each edge of one side.  The orientation of each number is perpendicular to its respective edge. Tiles come in three colors: red, yellow, and blue. These colors can be called a **set**. Each set of colored tiles has six tiles with different numbers each. These are:
	- [{1, 10, 18}, {2,9,17}, {3,12,14}, {4,11,13}, {5,8,16}, {6,7,15}]
- Each tile has a face and a back, with the face having the numbers showing. A tile's back shows neither the numbers nor the color of the set, but is instead black.

### Poles
- Poles are white cylinders that are placed in the center of a cell so that a tile may be placed down around it, and later one end of a bridge may be set down over that.

### Bridges
- Bridges are rectangular pieces that come in the colors orange, green, and purple.
- Bridges are placed over tiles after they are captured, and are used to hold the number of **tokens** associated with that capture.
- Bridges may only be placed after tiles are captured, and at most four bridges may be placed over the top of any single tile, in the case that bridges are placed leading to all adjacent spaces *and* a circuit has been completed.

### Tokens
- Tokens are silver pegs that are the objective of the game.
- Tokens are placed on bridges and remain there until the game ends and each player counts the tokens on bridges of their respective color.

### 1) Player Colors
- Each player chooses their desired bridge color. These bridges hold tokens and are the means of allocating points to players at the end of the game.
### 2) Distribute the Pieces
- On a standard triangular board, there are 18 total tiles, consisting of three different colors of sets of six tiles. To distribute tiles, players place all the tiles with the colors face down and mix them. 
#### One Player
- In solitaire mode the player picks face down tiles one at a time at random to distribute them on the board.
#### Two Players
- After jumbling the tiles, players take turns selecting pieces until each player has nine tiles.
#### Three Players
- After jumbling the tiles, players take turns selecting pieces until each player has six tiles.
### 3) Determine Turn and Color Priority
-  Each player chooses one tile to place face down for priority. The player with the highest number on their chosen tile goes first. That tile must be their first played piece. The color of that tile is the high color, meaning that capturing a tile of that color adds three points. Second and third priority are picked in the same manner, although the second and third players may choose different tiles to play on their first turn.
- In the event that all players choose tokens of the same value, players take their tokens back and choose different pieces
- In the event that two players place the same piece in a three player match, priority is determined by a single match of Rock/Paper/Scissors
### 4) Player Turns
####  Place Tiles
- A player's turn starts with placing one of their tiles on the board. Tiles may be placed in any vacant space. 
- If a player places a tile on a space where there are no tiles adjacent to that space, the player's turn is ended.
- If a player places a tile on a space where there are one or more adjacent tiles, the numbers on the placed tile are then compared to the matching numbers on the immediately adjacent tiles. This means that one of the three numbers on a tile is compared against the immediately adjacent number on the adjacent tile, not just any of the three.
	- For each tile where the placed tile's number is greater than the matching number on the immediately adjacent tile, the player may place a bridge between those two tiles.
	- Before a bridge is placed, the player places tokens on that bridge equivalent to the sums of the value of the tiles as determined by color priority in step two.
#### Check for Circuits
- A circuit is a conjoined series of bridges closing a hexagonal set of six spaces. Any player who finishes a circuit by placing a piece may put six tokens on the bridge that complete the circuit. If that player's bridges consist of more than three of the six bridges in the circuit, that player may place an additional bridge with that number of tokens on the bridge.
#### Turn End
- Once a player has placed their tile, placed any possible bridges, and checked for possible circuits, the player's turn is over.
Gameplay proceeds until the last open space on the board has been filled.
### 4) End Game
- Once the last space has been filled with a tile and all bridges have been placed, players remove their bridges from the board.
- Each player counts the number of tokens on their bridges, and the player with the most tokens wins.


# The Logic of Checking Adjacent Tiles

	// if we are not in the center of a quad tile (12/16)
	if (x != y) {

		// if we are not on an edge (9/12)  
		if (y !=0) {

			// if we are not in the central quad (6/9)
			if (x != 0) {
				checkTwoSides(x,y)
			}

			// we must be non-center of the purple quad (3/9)
			else(checkTilesAdjacentToNonCentralPurpleQuad(x,y))
 
		}

		// we are on an edge (3/12)
		else(checkEdge(y))
	}
	
	// we are in the center of a quad (4/16)
	else(checkTilesAroundQuadCenter(x))