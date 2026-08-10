"""Rainbow Connections - pygame implementation.

Board geometry and adjacency are derived from GridLayoutDiagram.png and
cross-checked against the adjacency pseudocode in Rules.md (every cell's
neighbor count matches the four branches described there).

Implemented so far: board setup, tile deck/dealing, the face-down priority
mini-game (skipped for solo play, which assigns priority at random and has
no mandatory first tile), interactive tile placement with rotation, and
automatic bridge creation. Per project decision, the Rock/Paper/Scissors
tie-break described in Rules.md is replaced with random assignment.

The priority mini-game ranks the 3 tile colors into 3/2/1 points (ties for
an unsettled color, which is common with fewer than 3 players, are broken
at random), shown throughout play in a small on-screen HUD. Whether a
bridge forms is decided by the two tiles' printed edge numbers - strictly
higher wins outright, and a tied number is instead broken by color
priority - but a bridge's token value is always just the sum of its two
tiles' color points (2 to 6 tokens), never the numbers.

Circuits (see find_hexagons(): each is the ring of 6 cells around one of
this board's 3 interior vertices) add +6 tokens to the completing bridge,
plus a bonus bridge if the completing player owns more than 3 of the 6
circuit bridges. Completed circuits are marked with a black tick across
each of their 6 bridges and a badge showing the total bonus earned.

Not yet implemented (see Rules.md): end-of-game bridge removal.
"""

import asyncio
import math
import os
import random
import sys

import pygame
import pygame.gfxdraw

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_SIZE = (900, 800)
BOARD_TOP = (450, 40)
BOARD_SIZE = 640

BG_COLOR = (24, 26, 30)
TEXT_COLOR = (230, 230, 230)
EMPTY_OUTLINE = (90, 90, 95)
EMPTY_CELL_COLOR = (245, 242, 235)

SET_COLORS = {
    "red": (200, 60, 60),
    "yellow": (215, 190, 45),
    "blue": (55, 115, 205),
}

BRIDGE_COLORS = {
    "orange": (230, 140, 30),
    "green": (70, 175, 95),
    "purple": (155, 85, 195),
}
BRIDGE_ORDER = ["orange", "green", "purple"]

NUMBER_SETS = [(1, 10, 18), (2, 9, 17), (3, 12, 14), (4, 11, 13), (5, 8, 16), (6, 7, 15)]

HAND_TILE_SIZE = 74
HAND_TILE_GAP = 18
HAND_Y = 650

# ---------------------------------------------------------------------------
# Board geometry and adjacency
# ---------------------------------------------------------------------------
# (row, position-in-row) -> board [x, y] cell coordinate, taken directly from
# GridLayoutDiagram.png. Row 0 is the single apex cell; row 3 is the 7-cell
# base row. Even positions are "up"-pointing cells, odd positions are "down".

ROWPOS_TO_COORD = {
    (0, 0): (3, 0),
    (1, 0): (3, 1),
    (1, 1): (3, 3),
    (1, 2): (3, 2),
    (2, 0): (2, 1),
    (2, 1): (0, 3),
    (2, 2): (0, 0),
    (2, 3): (0, 1),
    (2, 4): (1, 2),
    (3, 0): (2, 0),
    (3, 1): (2, 2),
    (3, 2): (2, 3),
    (3, 3): (0, 2),
    (3, 4): (1, 3),
    (3, 5): (1, 1),
    (3, 6): (1, 0),
}
COORD_TO_ROWPOS = {coord: rp for rp, coord in ROWPOS_TO_COORD.items()}
ALL_COORDS = list(COORD_TO_ROWPOS.keys())


def build_edge_neighbors():
    """coord -> {edge_index: neighbor_coord}.

    Each cell has 3 edges. For an "up" cell: 0=left, 1=right, 2=bottom.
    For a "down" cell: 0=left, 1=right, 2=top. Same-row neighbors always
    join a left cell's edge 1 to the right cell's edge 0. A row's "up"
    cells additionally touch a "down" cell in the row below via edge 2
    on both sides.
    """
    neighbors = {coord: {} for coord in ALL_COORDS}
    for (r, p), coord in ROWPOS_TO_COORD.items():
        if (r, p + 1) in ROWPOS_TO_COORD:
            right_coord = ROWPOS_TO_COORD[(r, p + 1)]
            neighbors[coord][1] = right_coord
            neighbors[right_coord][0] = coord
        if p % 2 == 0 and (r + 1, p + 1) in ROWPOS_TO_COORD:
            below_coord = ROWPOS_TO_COORD[(r + 1, p + 1)]
            neighbors[coord][2] = below_coord
            neighbors[below_coord][2] = coord
    return neighbors


CELL_EDGE_NEIGHBORS = build_edge_neighbors()


def cell_polygon(coord):
    """3 pixel vertices for a cell, ordered so index matches its edge convention."""
    r, p = COORD_TO_ROWPOS[coord]
    u = BOARD_SIZE / 4
    h = u * math.sqrt(3) / 2
    cx, top_y = BOARD_TOP
    y_top = top_y + r * h
    y_bot = top_y + (r + 1) * h
    l_top = cx - r * u / 2
    l_bot = cx - (r + 1) * u / 2
    k = p // 2
    if p % 2 == 0:  # up: [apex, bottom-left, bottom-right]
        apex = (l_top + k * u, y_top)
        bl = (l_bot + k * u, y_bot)
        br = (l_bot + (k + 1) * u, y_bot)
        return [apex, bl, br]
    else:  # down: [top-left, top-right, bottom-apex]
        tl = (l_top + k * u, y_top)
        tr = (l_top + (k + 1) * u, y_top)
        bapex = (l_bot + (k + 1) * u, y_bot)
        return [tl, tr, bapex]


def cell_centroid(coord):
    poly = cell_polygon(coord)
    return (sum(v[0] for v in poly) / 3, sum(v[1] for v in poly) / 3)


EDGE_VERTEX_PAIRS = {
    True: {0: (0, 1), 1: (0, 2), 2: (1, 2)},  # up:   apex-bl, apex-br, bl-br
    False: {0: (0, 2), 1: (1, 2), 2: (0, 1)},  # down: tl-bapex, tr-bapex, tl-tr
}


def edge_endpoints(poly, edge_index, is_up):
    i, j = EDGE_VERTEX_PAIRS[is_up][edge_index]
    return poly[i], poly[j]


def edge_midpoint(poly, edge_index, is_up):
    a, b = edge_endpoints(poly, edge_index, is_up)
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def point_in_triangle(pt, tri):
    def sign(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

    d1 = sign(pt, tri[0], tri[1])
    d2 = sign(pt, tri[1], tri[2])
    d3 = sign(pt, tri[2], tri[0])
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_neg and has_pos)


def cell_at_pixel(pos):
    for coord in ALL_COORDS:
        if point_in_triangle(pos, cell_polygon(coord)):
            return coord
    return None


def edge_key(coord_a, coord_b):
    return tuple(sorted((coord_a, coord_b)))


def find_hexagons():
    """A circuit is the hexagonal ring of 6 cells around one shared vertex.

    This board's side-4 triangle has exactly 3 interior vertices (where 6
    cells meet), found here from shared polygon corners rather than by
    hardcoding cell coordinates. Each hexagon is returned as its pixel
    center and its 6 consecutive (coord_a, coord_b) edges, in order around
    the vertex.
    """
    vertex_cells = {}
    for coord in ALL_COORDS:
        for vx, vy in cell_polygon(coord):
            key = (round(vx, 2), round(vy, 2))
            vertex_cells.setdefault(key, set()).add(coord)
    hexagons = []
    for (vx, vy), coords in vertex_cells.items():
        if len(coords) != 6:
            continue
        ordered = sorted(coords, key=lambda c: math.atan2(cell_centroid(c)[1] - vy, cell_centroid(c)[0] - vx))
        edges = [edge_key(ordered[i], ordered[(i + 1) % 6]) for i in range(6)]
        hexagons.append({"center": (vx, vy), "edges": edges})
    return hexagons


HEXAGONS = find_hexagons()


# ---------------------------------------------------------------------------
# Game model
# ---------------------------------------------------------------------------


class Tile:
    def __init__(self, color, numbers):
        self.color = color
        self.numbers = numbers  # fixed cyclic order of the 3 face values
        self.rotation = 0
        self.flipped = False  # display only: which way the hand icon points

    def edge_number(self, edge_index):
        # edge_index already has a consistent 0=left/1=right/2=third meaning
        # for both up and down cells (see cell_polygon/CELL_EDGE_NEIGHBORS),
        # so this must NOT vary with orientation - only rotation changes
        # which number lands on which edge.
        return self.numbers[(edge_index + self.rotation) % 3]

    def rotate(self):
        self.rotation = (self.rotation + 1) % 3

    def flip(self):
        self.flipped = not self.flipped


class Player:
    def __init__(self, index, bridge_color):
        self.index = index
        self.name = f"Player {index + 1}"
        self.bridge_color = bridge_color
        self.hand = []
        self.pool = []  # solo mode only: tiles not yet drawn into hand
        self.tokens = 0
        self.priority_tile = None
        self.priority_excluded = set()
        self.first_turn_pending = True


class Bridge:
    def __init__(self, coord_a, coord_b, color, tokens):
        self.coord_a = coord_a
        self.coord_b = coord_b
        self.color = color
        self.tokens = tokens


class CircuitEvent:
    def __init__(self, hexagon_index, completing_bridge, owned_count, bonus_bridge):
        self.hexagon_index = hexagon_index
        self.completing_bridge = completing_bridge
        self.owned_count = owned_count
        self.bonus_bridge = bonus_bridge


class Board:
    def __init__(self):
        self.cells = {coord: None for coord in ALL_COORDS}
        self.bridges = []
        self.color_points = {}
        self.completed_circuits = set()
        self.circuit_bonus = {}

    def is_full(self):
        return all(tile is not None for tile in self.cells.values())

    def place_tile(self, coord, tile, bridge_color):
        """Place tile at coord, create bridges against any filled neighbors
        whose matching edge number the placed tile beats, and award any
        circuit (hexagon) bonuses those new bridges complete. A strictly
        higher number always wins, regardless of color. A tied number is
        broken by color priority instead (the tile whose color has more
        priority points wins); if both tiles share a color too, the tie is
        simply unresolved and no bridge forms. A bridge's token value
        depends only on the two tiles' color-priority points (3/2/1, set by
        the priority mini-game), never on the numbers themselves. Returns
        (new_bridges, circuit_events).
        """
        self.cells[coord] = tile
        new_bridges = []
        for edge_index, neighbor_coord in CELL_EDGE_NEIGHBORS[coord].items():
            neighbor_tile = self.cells[neighbor_coord]
            if neighbor_tile is None:
                continue
            neighbor_edge_index = _shared_edge_on_neighbor(coord, neighbor_coord)
            placed_value = tile.edge_number(edge_index)
            neighbor_value = neighbor_tile.edge_number(neighbor_edge_index)
            if placed_value > neighbor_value:
                placed_wins = True
            elif placed_value == neighbor_value:
                placed_wins = self.color_points[tile.color] > self.color_points[neighbor_tile.color]
            else:
                placed_wins = False
            if placed_wins:
                tokens = self.color_points[tile.color] + self.color_points[neighbor_tile.color]
                bridge = Bridge(coord, neighbor_coord, bridge_color, tokens)
                self.bridges.append(bridge)
                new_bridges.append(bridge)
        circuit_events = self._check_circuits(new_bridges, bridge_color)
        return new_bridges, circuit_events

    def _edge_bridge(self, coord_a, coord_b):
        key = edge_key(coord_a, coord_b)
        for bridge in self.bridges:
            if edge_key(bridge.coord_a, bridge.coord_b) == key:
                return bridge
        return None

    def _check_circuits(self, new_bridges, bridge_color):
        new_edge_keys = {edge_key(b.coord_a, b.coord_b) for b in new_bridges}
        events = []
        for hexagon_index, hexagon in enumerate(HEXAGONS):
            if hexagon_index in self.completed_circuits:
                continue
            edges = hexagon["edges"]
            if not any(edge in new_edge_keys for edge in edges):
                continue
            edge_bridges = [self._edge_bridge(a, b) for a, b in edges]
            if any(b is None for b in edge_bridges):
                continue
            self.completed_circuits.add(hexagon_index)
            completing_bridge = next(b for b in edge_bridges if edge_key(b.coord_a, b.coord_b) in new_edge_keys)
            completing_bridge.tokens += 6
            owned_count = sum(1 for b in edge_bridges if b.color == bridge_color)
            bonus_bridge = None
            if owned_count > 3:
                bonus_bridge = Bridge(completing_bridge.coord_a, completing_bridge.coord_b, bridge_color, owned_count)
                self.bridges.append(bonus_bridge)
            self.circuit_bonus[hexagon_index] = 6 + (bonus_bridge.tokens if bonus_bridge else 0)
            events.append(CircuitEvent(hexagon_index, completing_bridge, owned_count, bonus_bridge))
        return events


def _shared_edge_on_neighbor(coord, neighbor_coord):
    for edge_index, other in CELL_EDGE_NEIGHBORS[neighbor_coord].items():
        if other == coord:
            return edge_index
    raise ValueError(f"{neighbor_coord} does not border {coord}")


def build_deck():
    deck = [Tile(color, numbers) for color in SET_COLORS for numbers in NUMBER_SETS]
    random.shuffle(deck)
    return deck


SOLO_VISIBLE_TILES = 6


def deal(players, deck):
    if len(players) == 1:
        player = players[0]
        player.hand = deck[:SOLO_VISIBLE_TILES]
        player.pool = deck[SOLO_VISIBLE_TILES:]
        return
    per_player = 9 if len(players) == 2 else 6
    for player in players:
        player.hand, deck = deck[:per_player], deck[per_player:]


def resolve_priority(players):
    """Rank players by the highest number on their face-down priority tile.

    Returns (turn_order, color_points). turn_order is a list of player
    indices from first to last. color_points maps each of the 3 tile colors
    to the points a bridge earns for touching a tile of that color: 3 for
    the highest-priority color, 2 for second, 1 for lowest - this is the
    only thing bridge scoring cares about; the tiles' printed numbers only
    decide whether a bridge forms, never how many tokens it's worth.
    Colors not settled by a priority pick (always true with fewer than 3
    players, and possible with 3 if two players pick the same color) get
    whatever points are left over, assigned at random.

    Returns None if every player tied and the whole round must be redone
    with different tiles (per Rules.md). A tie between some but not all
    players is broken by random assignment in place of the Rock/Paper/
    Scissors match Rules.md describes, per project decision.
    """
    values = [max(p.priority_tile.numbers) for p in players]
    if len(players) > 1 and len(set(values)) == 1:
        return None
    groups = {}
    for index, value in enumerate(values):
        groups.setdefault(value, []).append(index)
    turn_order = []
    for value in sorted(groups, reverse=True):
        group = groups[value]
        random.shuffle(group)
        turn_order.extend(group)

    points_remaining = [3, 2, 1]
    color_points = {}
    for player_index in turn_order:
        color = players[player_index].priority_tile.color
        if color not in color_points:
            color_points[color] = points_remaining.pop(0)
    leftover_colors = [color for color in SET_COLORS if color not in color_points]
    random.shuffle(leftover_colors)
    for color in leftover_colors:
        color_points[color] = points_remaining.pop(0)

    return turn_order, color_points


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def draw_cell_number(surface, font, poly, edge_index, value, is_up):
    a, b = edge_endpoints(poly, edge_index, is_up)
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1
    perp = (-dy / length, dx / length)
    cx = sum(v[0] for v in poly) / 3
    cy = sum(v[1] for v in poly) / 3
    if perp[0] * (cx - mx) + perp[1] * (cy - my) < 0:
        perp = (-perp[0], -perp[1])
    # Move straight in from the edge (perpendicular to it) rather than
    # toward the centroid, so a two-digit label clears a slanted edge by
    # the same margin regardless of that edge's angle. Scaled off the
    # edge's own length so this works for board cells, hand tiles, and the
    # small priority-reveal icons alike.
    inset = length * 0.17
    x = mx + perp[0] * inset
    y = my + perp[1] * inset
    label = font.render(str(value), True, (255, 255, 255))
    surface.blit(label, (x - label.get_width() / 2, y - label.get_height() / 2))


def draw_smooth_polygon_outline(surface, poly, color, width):
    """An anti-aliased polygon outline. Plain pygame.draw.polygon outlines
    aren't anti-aliased and look jagged along the triangle's diagonal
    edges, so this instead stacks several concentric pygame.gfxdraw
    outlines (which are anti-aliased) to build up a smooth, thick border.
    """
    cx = sum(v[0] for v in poly) / len(poly)
    cy = sum(v[1] for v in poly) / len(poly)
    layers = max(1, round(width))
    for i in range(layers):
        inset = i - (layers - 1) / 2
        ring = []
        for x, y in poly:
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy) or 1
            factor = (dist + inset) / dist
            ring.append((round(cx + dx * factor), round(cy + dy * factor)))
        pygame.gfxdraw.aapolygon(surface, ring, color)


def draw_smooth_line(surface, color, a, b, width):
    """An anti-aliased line of arbitrary width, built from parallel
    pygame.draw.aaline passes since pygame.draw.line's width>1 mode isn't
    anti-aliased and looks jagged."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1
    perp = (-dy / length, dx / length)
    layers = max(1, round(width))
    for i in range(layers):
        offset = i - (layers - 1) / 2
        pa = (a[0] + perp[0] * offset, a[1] + perp[1] * offset)
        pb = (b[0] + perp[0] * offset, b[1] + perp[1] * offset)
        pygame.draw.aaline(surface, color, pa, pb)


def draw_smooth_filled_polygon(surface, poly, color):
    """A polygon fill with an anti-aliased boundary. A plain filled
    polygon's outer edge is just as jagged as an unaliased stroke, so this
    blends one anti-aliased pass of the same color exactly on the true
    boundary on top of the hard-edged fill."""
    points = [(round(x), round(y)) for x, y in poly]
    pygame.gfxdraw.filled_polygon(surface, points, color)
    pygame.gfxdraw.aapolygon(surface, points, color)


def draw_board(surface, board, font):
    for coord in ALL_COORDS:
        poly = cell_polygon(coord)
        tile = board.cells[coord]
        if tile is None:
            draw_smooth_filled_polygon(surface, poly, EMPTY_CELL_COLOR)
            draw_smooth_polygon_outline(surface, poly, EMPTY_OUTLINE, 3)
        else:
            draw_smooth_filled_polygon(surface, poly, SET_COLORS[tile.color])
            draw_smooth_polygon_outline(surface, poly, (10, 10, 10), 3)
            _, position = COORD_TO_ROWPOS[coord]
            is_up = position % 2 == 0
            for edge_index in range(3):
                draw_cell_number(surface, font, poly, edge_index, tile.edge_number(edge_index), is_up)

    circuit_edges = set()
    for hexagon_index in board.completed_circuits:
        circuit_edges.update(HEXAGONS[hexagon_index]["edges"])

    bridges_by_edge = {}
    for bridge in board.bridges:
        bridges_by_edge.setdefault(edge_key(bridge.coord_a, bridge.coord_b), []).append(bridge)

    badge_radius = 11
    for edge, stacked in bridges_by_edge.items():
        a = cell_centroid(edge[0])
        b = cell_centroid(edge[1])
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1
        direction = (dx / length, dy / length)
        perp = (-dy / length, dx / length)
        for i, bridge in enumerate(stacked):
            offset = (i - (len(stacked) - 1) / 2) * 22
            shift = (perp[0] * offset, perp[1] * offset)
            pa = (a[0] + shift[0], a[1] + shift[1])
            pb = (b[0] + shift[0], b[1] + shift[1])
            color = BRIDGE_COLORS[bridge.color]
            draw_smooth_line(surface, color, pa, pb, 6)
            mid = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
            if edge in circuit_edges:
                gap = badge_radius + 3
                seg1_end = (mid[0] - direction[0] * gap, mid[1] - direction[1] * gap)
                seg2_start = (mid[0] + direction[0] * gap, mid[1] + direction[1] * gap)
                draw_smooth_line(surface, (0, 0, 0), pa, seg1_end, 3)
                draw_smooth_line(surface, (0, 0, 0), seg2_start, pb, 3)
            label = font.render(str(bridge.tokens), True, (255, 255, 255))
            pygame.draw.circle(surface, color, mid, badge_radius)
            surface.blit(label, (mid[0] - label.get_width() / 2, mid[1] - label.get_height() / 2))

    for hexagon_index in board.completed_circuits:
        hexagon = HEXAGONS[hexagon_index]
        cx, cy = hexagon["center"]
        bonus_label = font.render(f"+{board.circuit_bonus[hexagon_index]}", True, (255, 255, 255))
        bonus_radius = max(14, bonus_label.get_width() / 2 + 4)
        pygame.draw.circle(surface, (0, 0, 0), (cx, cy), bonus_radius)
        surface.blit(bonus_label, (cx - bonus_label.get_width() / 2, cy - bonus_label.get_height() / 2))


def hand_tile_polygon(x, flipped):
    h = HAND_TILE_SIZE * math.sqrt(3) / 2
    if not flipped:
        apex = (x + HAND_TILE_SIZE / 2, HAND_Y)
        bl = (x, HAND_Y + h)
        br = (x + HAND_TILE_SIZE, HAND_Y + h)
        return [apex, bl, br]
    tl = (x, HAND_Y)
    tr = (x + HAND_TILE_SIZE, HAND_Y)
    bapex = (x + HAND_TILE_SIZE / 2, HAND_Y + h)
    return [tl, tr, bapex]


def draw_hand(surface, font, player, selected_index):
    label = font.render(f"{player.name} ({player.bridge_color})", True, BRIDGE_COLORS[player.bridge_color])
    label_rect = label.get_rect(topleft=(46, HAND_Y - 30))
    box_rect = label_rect.inflate(16, 10)
    pygame.draw.rect(surface, BRIDGE_COLORS[player.bridge_color], box_rect, width=2, border_radius=5)
    surface.blit(label, label_rect)
    for i, tile in enumerate(player.hand):
        x = 40 + i * (HAND_TILE_SIZE + HAND_TILE_GAP)
        poly = hand_tile_polygon(x, tile.flipped)
        draw_smooth_filled_polygon(surface, poly, SET_COLORS[tile.color])
        outline_color = (255, 230, 90) if i == selected_index else (10, 10, 10)
        draw_smooth_polygon_outline(surface, poly, outline_color, 4 if i == selected_index else 2)
        for edge_index in range(3):
            draw_cell_number(surface, font, poly, edge_index, tile.edge_number(edge_index), not tile.flipped)
        if player.first_turn_pending and tile is player.priority_tile:
            star = font.render("*", True, (255, 255, 255))
            surface.blit(star, (x + HAND_TILE_SIZE / 2 - star.get_width() / 2, HAND_Y - 18))


def hand_tile_at_pixel(pos, hand):
    for i, tile in enumerate(hand):
        x = 40 + i * (HAND_TILE_SIZE + HAND_TILE_GAP)
        if point_in_triangle(pos, hand_tile_polygon(x, tile.flipped)):
            return i
    return None


def compute_live_tokens(players, board):
    """Current token count per player, tallied live from bridges already on
    the board (unlike tally_tokens, this doesn't mutate player.tokens, so it
    can be called every frame during play without disturbing the end-game
    tally).
    """
    tokens = {player.bridge_color: 0 for player in players}
    for bridge in board.bridges:
        tokens[bridge.color] += bridge.tokens
    return tokens


def draw_scoreboard(surface, font, players, board):
    tokens = compute_live_tokens(players, board)
    row_h = 24
    pad = 14
    width = 170
    height = pad * 2 + 10 + row_h * len(players)
    panel = pygame.Surface((width, height), pygame.SRCALPHA)
    panel_rect = panel.get_rect()
    pygame.draw.rect(panel, (40, 42, 48, 215), panel_rect, border_radius=8)
    pygame.draw.rect(panel, (90, 92, 100, 255), panel_rect, width=1, border_radius=8)
    surface.blit(panel, (10, 10))

    title = font.render("Score", True, TEXT_COLOR)
    surface.blit(title, (10 + pad, 10 + pad - 4))
    y = 10 + pad + 22
    for player in players:
        color = BRIDGE_COLORS[player.bridge_color]
        pygame.draw.rect(surface, color, (10 + pad, y + 3, 14, 14), border_radius=3)
        label = font.render(f"{player.name}: {tokens[player.bridge_color]}", True, TEXT_COLOR)
        surface.blit(label, (10 + pad + 22, y))
        y += row_h


def draw_color_points_hud(surface, font, color_points):
    row_h = 20
    pad = 14
    width = 170
    height = pad * 2 + 10 + row_h * len(color_points)
    x = WINDOW_SIZE[0] - 10 - width
    y = 10
    panel = pygame.Surface((width, height), pygame.SRCALPHA)
    panel_rect = panel.get_rect()
    pygame.draw.rect(panel, (40, 42, 48, 215), panel_rect, border_radius=8)
    pygame.draw.rect(panel, (90, 92, 100, 255), panel_rect, width=1, border_radius=8)
    surface.blit(panel, (x, y))

    title = font.render("Color priority", True, TEXT_COLOR)
    surface.blit(title, (x + pad, y + pad - 4))
    row_y = y + pad + 22
    for color in sorted(color_points, key=lambda c: -color_points[c]):
        text = f"{color}: {color_points[color]} pts"
        label = font.render(text, True, SET_COLORS[color])
        surface.blit(label, (x + pad, row_y))
        row_y += row_h


ROYGBIV = [
    (237, 28, 36),  # red
    (255, 127, 39),  # orange
    (255, 242, 0),  # yellow
    (34, 177, 76),  # green
    (0, 114, 198),  # blue
    (63, 72, 204),  # indigo
    (163, 73, 164),  # violet
]


def draw_rainbow_arcs(surface, center, outer_radius, band_width):
    """Seven concentric ROYGBIV bands, drawn as the top half of circles
    sharing one center, so they read as a rainbow arching over whatever
    sits at the center point. Each band is a filled ring polygon (an outer
    semicircle arc joined to an inner one) rather than a stroked arc -
    pygame.draw.arc gets visibly speckled at large widths, and even
    stacking many 1px gfxdraw arcs leaves a dotted moire pattern since
    adjacent integer radii don't fully tile a curve this shallow.
    """
    cx, cy = center
    steps = 120
    angles = [math.pi + math.pi * t / steps for t in range(steps + 1)]
    for i, color in enumerate(ROYGBIV):
        r_outer = outer_radius - i * band_width
        r_inner = r_outer - band_width
        ring = [(cx + r_outer * math.cos(a), cy + r_outer * math.sin(a)) for a in angles]
        ring += [(cx + r_inner * math.cos(a), cy + r_inner * math.sin(a)) for a in reversed(angles)]
        draw_smooth_filled_polygon(surface, ring, color)


def draw_title_frame(surface, big_font, text, center):
    title = big_font.render(text, True, TEXT_COLOR)
    title_rect = title.get_rect(center=center)
    frame_rect = title_rect.inflate(64, 34)
    pygame.draw.rect(surface, (30, 32, 38), frame_rect, border_radius=12)
    pygame.draw.rect(surface, (200, 170, 90), frame_rect, width=3, border_radius=12)
    inner_rect = frame_rect.inflate(-10, -10)
    pygame.draw.rect(surface, (200, 170, 90), inner_rect, width=1, border_radius=8)
    surface.blit(title, title_rect)
    return frame_rect


def play_button_rect():
    rect = pygame.Rect(0, 0, 200, 46)
    rect.center = (WINDOW_SIZE[0] / 2, 470)
    return rect


def how_to_play_button_rect():
    rect = pygame.Rect(0, 0, 200, 46)
    rect.center = (WINDOW_SIZE[0] / 2, 530)
    return rect


def draw_setup_screen(surface, font, big_font):
    title_center = (WINDOW_SIZE[0] / 2, 340)
    draw_rainbow_arcs(surface, title_center, outer_radius=260, band_width=16)
    draw_title_frame(surface, big_font, "Rainbow Connections", title_center)
    draw_button(surface, font, play_button_rect(), "Play", color=(70, 150, 90))
    draw_button(surface, font, how_to_play_button_rect(), "How to Play", color=(90, 90, 100))


def draw_choose_players_screen(surface, font, big_font):
    title = big_font.render("Choose Number of Players", True, TEXT_COLOR)
    surface.blit(title, (WINDOW_SIZE[0] / 2 - title.get_width() / 2, 300))
    prompt = font.render("Press 1, 2, or 3 to choose the number of players", True, TEXT_COLOR)
    surface.blit(prompt, (WINDOW_SIZE[0] / 2 - prompt.get_width() / 2, 360))


# ---------------------------------------------------------------------------
# How to Play tutorial
# ---------------------------------------------------------------------------

_GAMEPLAY_SCREENSHOT_IMAGE = None


def _scaled_image_blit(surface, rect, image):
    scale = min(rect.width / image.get_width(), rect.height / image.get_height())
    size = (round(image.get_width() * scale), round(image.get_height() * scale))
    scaled = pygame.transform.smoothscale(image, size)
    surface.blit(scaled, scaled.get_rect(center=rect.center))


def draw_tutorial_goal_diagram(surface, rect, font):
    """An actual screenshot of play in progress - bridges, tokens, hand,
    and score panel all at once - illustrates the goal far better than a
    schematic ever could.
    """
    global _GAMEPLAY_SCREENSHOT_IMAGE
    if _GAMEPLAY_SCREENSHOT_IMAGE is None:
        image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "GameplayScreenshot.png")
        _GAMEPLAY_SCREENSHOT_IMAGE = pygame.image.load(image_path).convert_alpha()
    _scaled_image_blit(surface, rect, _GAMEPLAY_SCREENSHOT_IMAGE)


def draw_tutorial_board_diagram(surface, rect, font):
    """Renders the same empty board draw_board() shows in real play (rather
    than the separate GridLayoutDiagram.png reference image), cropped to
    its triangular bounding box and scaled to fit the diagram area.
    """
    board_surface = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
    draw_board(board_surface, Board(), font)
    board_box = pygame.Rect(
        round(BOARD_TOP[0] - BOARD_SIZE / 2),
        BOARD_TOP[1],
        BOARD_SIZE,
        round(BOARD_SIZE * math.sqrt(3) / 2),
    )
    cropped = board_surface.subsurface(board_box).copy()
    _scaled_image_blit(surface, rect, cropped)


def draw_tutorial_tiles_diagram(surface, rect, font):
    size = 84
    gap = 26
    total_w = size * 3 + gap * 2
    x = rect.centerx - total_w / 2
    y = rect.centery - size * math.sqrt(3) / 2 / 2
    sample_numbers = [(1, 10, 18), (5, 8, 16), (6, 7, 15)]
    for i, color in enumerate(SET_COLORS):
        poly = small_tile_icon_polygon(x + i * (size + gap), y, size)
        draw_smooth_filled_polygon(surface, poly, SET_COLORS[color])
        draw_smooth_polygon_outline(surface, poly, (10, 10, 10), 2)
        tile = Tile(color, sample_numbers[i])
        for edge_index in range(3):
            draw_cell_number(surface, font, poly, edge_index, tile.edge_number(edge_index), True)


def draw_tutorial_priority_diagram(surface, rect, font):
    size = 84
    tile = Tile("red", (2, 9, 17))
    x = rect.centerx - 230
    y = rect.centery - size * math.sqrt(3) / 2 / 2
    poly = small_tile_icon_polygon(x, y, size)
    draw_smooth_filled_polygon(surface, poly, SET_COLORS[tile.color])
    draw_smooth_polygon_outline(surface, poly, (255, 230, 90), 3)
    for edge_index in range(3):
        draw_cell_number(surface, font, poly, edge_index, tile.edge_number(edge_index), True)

    label_x = x + size + 50
    label_y = rect.centery - 38
    sample_points = {"red": 3, "yellow": 2, "blue": 1}
    for color in sorted(sample_points, key=lambda c: -sample_points[c]):
        text = f"{color}: {sample_points[color]} pts per bridge"
        label = font.render(text, True, SET_COLORS[color])
        surface.blit(label, (label_x, label_y))
        label_y += 26


def draw_tutorial_bridge_diagram(surface, rect, font):
    size = 100
    y = rect.centery - size * math.sqrt(3) / 2 / 2
    left_x = rect.centerx - size - 40
    right_x = rect.centerx + 40
    left_tile = Tile("blue", (5, 8, 16))
    right_tile = Tile("red", (6, 7, 15))
    left_poly = small_tile_icon_polygon(left_x, y, size)
    right_poly = small_tile_icon_polygon(right_x, y, size)
    for poly, tile in ((left_poly, left_tile), (right_poly, right_tile)):
        draw_smooth_filled_polygon(surface, poly, SET_COLORS[tile.color])
        draw_smooth_polygon_outline(surface, poly, (10, 10, 10), 2)
        for edge_index in range(3):
            draw_cell_number(surface, font, poly, edge_index, tile.edge_number(edge_index), True)

    tile_h = size * math.sqrt(3) / 2
    a = (left_x + size, y + tile_h / 2)
    b = (right_x, y + tile_h / 2)
    draw_smooth_line(surface, BRIDGE_COLORS["orange"], a, b, 6)
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    pygame.draw.circle(surface, BRIDGE_COLORS["orange"], mid, 11)
    label = font.render("6", True, (255, 255, 255))
    surface.blit(label, (mid[0] - label.get_width() / 2, mid[1] - label.get_height() / 2))

    caption = font.render("red's 6 beats blue's 5 - a bridge forms!", True, TEXT_COLOR)
    surface.blit(caption, (rect.centerx - caption.get_width() / 2, y + tile_h + 20))


def draw_tutorial_circuit_diagram(surface, rect, font):
    cx, cy = rect.center
    radius = 80
    points = [
        (cx + radius * math.cos(math.radians(60 * i - 90)), cy + radius * math.sin(math.radians(60 * i - 90))) for i in range(6)
    ]
    for i in range(6):
        color = BRIDGE_COLORS[BRIDGE_ORDER[i % 3]]
        draw_smooth_line(surface, color, points[i], points[(i + 1) % 6], 6)
    badge_label = font.render("+6", True, (255, 255, 255))
    badge_radius = max(16, badge_label.get_width() / 2 + 6)
    pygame.draw.circle(surface, (0, 0, 0), (cx, cy), badge_radius)
    surface.blit(badge_label, (cx - badge_label.get_width() / 2, cy - badge_label.get_height() / 2))


def draw_tutorial_scoring_diagram(surface, rect, font):
    sample = [("Player 1", "orange", 14), ("Player 2", "green", 9), ("Player 3", "purple", 17)]
    best = max(tokens for _, _, tokens in sample)
    row_h = 30
    width = 240
    height = len(sample) * row_h + 20
    panel_rect = pygame.Rect(0, 0, width, height)
    panel_rect.center = rect.center
    panel = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.rect(panel, (40, 42, 48, 220), panel.get_rect(), border_radius=8)
    pygame.draw.rect(panel, (90, 92, 100, 255), panel.get_rect(), width=1, border_radius=8)
    surface.blit(panel, panel_rect.topleft)
    y = panel_rect.top + 10
    for name, color, tokens in sample:
        pygame.draw.rect(surface, BRIDGE_COLORS[color], (panel_rect.left + 14, y + 5, 14, 14), border_radius=3)
        text_color = (255, 215, 0) if tokens == best else TEXT_COLOR
        label = font.render(f"{name}: {tokens} tokens", True, text_color)
        surface.blit(label, (panel_rect.left + 36, y))
        y += row_h


TUTORIAL_STEPS = [
    {
        "title": "Goal",
        "body": [
            "Rainbow Connections is a board game for 1-3 players.",
            "Place tiles to form bridges, earn tokens on those bridges,",
            "and finish with the most tokens on your color to win.",
        ],
        "diagram": draw_tutorial_goal_diagram,
    },
    {
        "title": "The Board",
        "body": [
            "16 triangular cells make up one large triangle board.",
            "Every cell will eventually hold one tile.",
        ],
        "diagram": draw_tutorial_board_diagram,
    },
    {
        "title": "Tiles & Colors",
        "body": [
            "Tiles are red, yellow, or blue, with a number along each edge.",
            "A tile's numbers are compared to whatever tile is placed next door.",
        ],
        "diagram": draw_tutorial_tiles_diagram,
    },
    {
        "title": "Setting Priority",
        "body": [
            "Before play, each player secretly picks one tile.",
            "The highest number revealed goes first, and that tile's color",
            "becomes worth the most points per bridge (3/2/1).",
        ],
        "diagram": draw_tutorial_priority_diagram,
    },
    {
        "title": "Placing Tiles & Bridges",
        "body": [
            "On your turn, place a tile on any empty cell.",
            "If your tile's edge number beats the matching number on a",
            "neighboring tile, a bridge forms there and earns tokens.",
        ],
        "diagram": draw_tutorial_bridge_diagram,
    },
    {
        "title": "Circuits",
        "body": [
            "Complete a hexagonal ring of six bridges to finish a circuit:",
            "+6 bonus tokens, plus another bridge if you own more than",
            "half of that ring's six bridges.",
        ],
        "diagram": draw_tutorial_circuit_diagram,
    },
    {
        "title": "Scoring & Winning",
        "body": [
            "Once the board is full, tokens are tallied up by bridge color.",
            "Whoever's color holds the most tokens wins the game!",
        ],
        "diagram": draw_tutorial_scoring_diagram,
    },
]


def tutorial_button_rects():
    back_rect = pygame.Rect(40, WINDOW_SIZE[1] - 70, 120, 42)
    next_rect = pygame.Rect(WINDOW_SIZE[0] - 160, WINDOW_SIZE[1] - 70, 120, 42)
    return back_rect, next_rect


def tutorial_exit_button_rect():
    return pygame.Rect(30, 30, 140, 40)


def draw_how_to_play_screen(surface, font, big_font, step_index):
    step = TUTORIAL_STEPS[step_index]
    title = big_font.render(step["title"], True, TEXT_COLOR)
    surface.blit(title, (WINDOW_SIZE[0] / 2 - title.get_width() / 2, 30))

    draw_button(surface, font, tutorial_exit_button_rect(), "Exit Rules", color=(120, 60, 60))

    progress = font.render(f"Step {step_index + 1} of {len(TUTORIAL_STEPS)}", True, (150, 150, 155))
    surface.blit(progress, (WINDOW_SIZE[0] / 2 - progress.get_width() / 2, 86))

    body_y = 120
    for line in step["body"]:
        label = font.render(line, True, TEXT_COLOR)
        surface.blit(label, (WINDOW_SIZE[0] / 2 - label.get_width() / 2, body_y))
        body_y += 24

    diagram_rect = pygame.Rect(0, 0, 640, 360)
    diagram_rect.center = (WINDOW_SIZE[0] / 2, 480)
    step["diagram"](surface, diagram_rect, font)

    back_rect, next_rect = tutorial_button_rects()
    back_color = (70, 130, 180) if step_index > 0 else (60, 60, 65)
    draw_button(surface, font, back_rect, "Back", color=back_color)
    next_label = "Done" if step_index == len(TUTORIAL_STEPS) - 1 else "Next"
    draw_button(surface, font, next_rect, next_label)


def draw_priority_pass_screen(surface, font, big_font, player, redo_message):
    title = big_font.render(f"Pass the device to {player.name}", True, TEXT_COLOR)
    surface.blit(title, (WINDOW_SIZE[0] / 2 - title.get_width() / 2, 300))
    prompt = font.render("Click anywhere to choose your priority tile face-down.", True, TEXT_COLOR)
    surface.blit(prompt, (WINDOW_SIZE[0] / 2 - prompt.get_width() / 2, 360))
    if redo_message:
        note = font.render(redo_message, True, (240, 180, 90))
        surface.blit(note, (WINDOW_SIZE[0] / 2 - note.get_width() / 2, 390))


def draw_priority_select_screen(surface, font, big_font, player):
    title = big_font.render(f"{player.name}: pick a priority tile", True, TEXT_COLOR)
    surface.blit(title, (WINDOW_SIZE[0] / 2 - title.get_width() / 2, 120))
    prompt = font.render(
        "Whoever reveals the highest number goes first and must play that tile first.",
        True,
        TEXT_COLOR,
    )
    surface.blit(prompt, (WINDOW_SIZE[0] / 2 - prompt.get_width() / 2, 170))
    draw_hand(surface, font, player, None)


def small_tile_icon_polygon(x, y, size):
    h = size * math.sqrt(3) / 2
    apex = (x + size / 2, y)
    bl = (x, y + h)
    br = (x + size, y + h)
    return [apex, bl, br]


def draw_priority_tile_icon(surface, font, x, y, size, tile):
    """A priority-tile icon styled like a draw_hand tile: smooth
    anti-aliased fill and outline instead of a plain pygame.draw.polygon.
    """
    poly = small_tile_icon_polygon(x, y, size)
    draw_smooth_filled_polygon(surface, poly, SET_COLORS[tile.color])
    draw_smooth_polygon_outline(surface, poly, (10, 10, 10), 2)
    for edge_index in range(3):
        draw_cell_number(surface, font, poly, edge_index, tile.edge_number(edge_index), True)


def draw_priority_reveal_screen(surface, font, big_font, players, turn_order, color_points, redo_message, tie_pending):
    """Shown after every priority comparison - both when it produces a
    final turn order and, so players can see what tied, when it doesn't.
    """
    icon_size = 56
    row_height = 68
    icon_h = icon_size * math.sqrt(3) / 2

    if tie_pending:
        title = big_font.render("Tile Tie!", True, (240, 180, 90))
        surface.blit(title, (WINDOW_SIZE[0] / 2 - title.get_width() / 2, 40))
        lines_shown = 0
        for player in players:
            if player.priority_tile is None:
                continue
            tile = player.priority_tile
            text = f"{player.name} - {tile.color} tile"
            label = font.render(text, True, SET_COLORS[tile.color])
            row_width = icon_size + 12 + label.get_width()
            row_x = WINDOW_SIZE[0] / 2 - row_width / 2
            row_y = 110 + lines_shown * row_height
            draw_priority_tile_icon(surface, font, row_x, row_y, icon_size, tile)
            surface.blit(label, (row_x + icon_size + 12, row_y + icon_h / 2 - label.get_height() / 2))
            lines_shown += 1
        y = 110 + lines_shown * row_height + 10
        if redo_message:
            note = font.render(redo_message, True, (240, 180, 90))
            surface.blit(note, (WINDOW_SIZE[0] / 2 - note.get_width() / 2, y))
            y += 26
        prompt = font.render("Click anywhere to choose again.", True, TEXT_COLOR)
        surface.blit(prompt, (WINDOW_SIZE[0] / 2 - prompt.get_width() / 2, y + 10))
        return

    title = big_font.render("Priority Results", True, TEXT_COLOR)
    surface.blit(title, (WINDOW_SIZE[0] / 2 - title.get_width() / 2, 40))
    lines_shown = 0
    for rank, player_index in enumerate(turn_order):
        player = players[player_index]
        if player.priority_tile is None:
            continue
        tile = player.priority_tile
        text = f"{rank + 1}. {player.name} - {tile.color} tile chosen for priority"
        label = font.render(text, True, SET_COLORS[tile.color])
        row_width = icon_size + 12 + label.get_width()
        row_x = WINDOW_SIZE[0] / 2 - row_width / 2
        row_y = 110 + lines_shown * row_height
        draw_priority_tile_icon(surface, font, row_x, row_y, icon_size, tile)
        surface.blit(label, (row_x + icon_size + 12, row_y + icon_h / 2 - label.get_height() / 2))
        lines_shown += 1
    y = 110 + lines_shown * row_height + 20
    for color in sorted(color_points, key=lambda c: -color_points[c]):
        text = f"{color}: {color_points[color]} points per tile in a bridge"
        label = font.render(text, True, SET_COLORS[color])
        surface.blit(label, (WINDOW_SIZE[0] / 2 - label.get_width() / 2, y))
        y += 26
    prompt = font.render("Click anywhere to begin play.", True, TEXT_COLOR)
    surface.blit(prompt, (WINDOW_SIZE[0] / 2 - prompt.get_width() / 2, y + 10))


def draw_button(surface, font, rect, label_text, color=(70, 130, 180)):
    pygame.draw.rect(surface, color, rect, border_radius=6)
    label = font.render(label_text, True, (255, 255, 255))
    surface.blit(label, (rect.centerx - label.get_width() / 2, rect.centery - label.get_height() / 2))


def draw_gameover_screen(surface, font, big_font, players):
    title = big_font.render("Game Over", True, TEXT_COLOR)
    surface.blit(title, (WINDOW_SIZE[0] / 2 - title.get_width() / 2, 40))
    if len(players) == 1:
        player = players[0]
        text = f"You scored {player.tokens} tokens!"
        label = font.render(text, True, BRIDGE_COLORS[player.bridge_color])
        surface.blit(label, (WINDOW_SIZE[0] / 2 - label.get_width() / 2, 110))
    else:
        best = max(p.tokens for p in players)
        for i, player in enumerate(players):
            text = f"{player.name} ({player.bridge_color}): {player.tokens} tokens"
            color = BRIDGE_COLORS[player.bridge_color]
            label = font.render(text, True, color)
            surface.blit(label, (WINDOW_SIZE[0] / 2 - label.get_width() / 2, 110 + i * 32))
        winners = [p.name for p in players if p.tokens == best]
        result = "Tie between " + " and ".join(winners) if len(winners) > 1 else f"{winners[0]} wins!"
        label = font.render(result, True, TEXT_COLOR)
        surface.blit(label, (WINDOW_SIZE[0] / 2 - label.get_width() / 2, 110 + len(players) * 32 + 20))

    draw_button(surface, font, new_game_button_rect(players), "New Game")


def new_game_button_rect(players):
    bottom_y = 110 + 32 if len(players) == 1 else 110 + len(players) * 32 + 20 + 32
    width, height = 160, 40
    return pygame.Rect(WINDOW_SIZE[0] / 2 - width / 2, bottom_y + 20, width, height)


def tally_tokens(players, board):
    by_color = {player.bridge_color: player for player in players}
    for player in players:
        player.tokens = 0
    for bridge in board.bridges:
        by_color[bridge.color].tokens += bridge.tokens


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


class Game:
    def __init__(self):
        self.state = "setup"
        self.players = []
        self.board = Board()
        self.selected_hand_index = None
        self.priority_index = 0
        self.redo_message = None
        self.hint = None
        self.message = None
        self.turn_order = []
        self.turn_pointer = 0
        self.color_points = {}
        self.priority_tie_pending = False
        self.tutorial_step = 0

    def open_how_to_play(self):
        self.tutorial_step = 0
        self.state = "how_to_play"

    def exit_how_to_play(self):
        self.state = "setup"

    def advance_tutorial(self):
        if self.tutorial_step < len(TUTORIAL_STEPS) - 1:
            self.tutorial_step += 1
        else:
            self.state = "setup"

    def retreat_tutorial(self):
        if self.tutorial_step > 0:
            self.tutorial_step -= 1

    def start(self, num_players):
        self.players = [Player(i, BRIDGE_ORDER[i]) for i in range(num_players)]
        deal(self.players, build_deck())
        self.board = Board()
        self.selected_hand_index = None
        self.priority_index = 0
        self.redo_message = None
        self.hint = None
        self.message = None
        self.priority_tie_pending = False
        if num_players == 1:
            self._resolve_solo_priority()
        else:
            self.state = "priority_pass"

    def _resolve_solo_priority(self):
        """Solo play skips the face-down mini-game (no one to hide it from)
        and just picks color priority at random, per project decision.
        There's also no mandatory first tile: that rule exists to give the
        other players useful information about what you're forced to play,
        which is meaningless with no other players.
        """
        player = self.players[0]
        player.first_turn_pending = False
        colors = list(SET_COLORS)
        random.shuffle(colors)
        self.turn_order = [0]
        self.color_points = {colors[0]: 3, colors[1]: 2, colors[2]: 1}
        self.board.color_points = self.color_points
        self.turn_pointer = 0
        self.selected_hand_index = None
        self.state = "priority_reveal"

    def choose_priority_tile(self, hand_index):
        player = self.players[self.priority_index]
        tile = player.hand[hand_index]
        if tile in player.priority_excluded:
            return
        player.priority_tile = tile
        self.priority_index += 1
        if self.priority_index < len(self.players):
            self.state = "priority_pass"
        else:
            self._resolve_priority_round()

    def _resolve_priority_round(self):
        result = resolve_priority(self.players)
        if result is None:
            # Show the tied tiles before clearing them - clearing is
            # deferred to acknowledge_priority_reveal() so players actually
            # get to see what tied instead of it vanishing immediately.
            self.redo_message = "Every player tied - choose a different tile each."
            self.priority_tie_pending = True
            self.state = "priority_reveal"
            return
        self.turn_order, self.color_points = result
        self.board.color_points = self.color_points
        self.turn_pointer = 0
        self.selected_hand_index = None
        self.priority_tie_pending = False
        # Only the player who actually won priority (goes first) is bound to
        # play their priority tile as their opening move - everyone else's
        # priority pick was just their entry in the comparison, and they're
        # free to open with whatever tile they like.
        for player in self.players:
            player.first_turn_pending = False
        self.players[self.turn_order[0]].first_turn_pending = True
        self.state = "priority_reveal"

    def acknowledge_priority_reveal(self):
        if self.priority_tie_pending:
            for player in self.players:
                player.priority_excluded.add(player.priority_tile)
                player.priority_tile = None
            self.priority_tie_pending = False
            self.priority_index = 0
            self.state = "priority_pass"
        else:
            self.begin_playing()

    def begin_playing(self):
        self.state = "playing"

    @property
    def current_player(self):
        return self.players[self.turn_order[self.turn_pointer]]

    def advance_turn(self):
        self.selected_hand_index = None
        for _ in range(len(self.players)):
            self.turn_pointer = (self.turn_pointer + 1) % len(self.turn_order)
            if self.current_player.hand:
                break

    def place_selected_tile(self, coord):
        if self.selected_hand_index is None:
            return
        if self.board.cells[coord] is not None:
            return
        player = self.current_player
        tile = player.hand[self.selected_hand_index]
        if player.first_turn_pending and tile is not player.priority_tile:
            self.hint = "You won priority - you must play your starred priority tile first."
            return
        self.hint = None
        player.hand.pop(self.selected_hand_index)
        player.first_turn_pending = False
        if len(self.players) == 1 and player.pool:
            player.hand.append(player.pool.pop())
        _, circuit_events = self.board.place_tile(coord, tile, player.bridge_color)
        self.message = self._circuit_message(player, circuit_events)
        if self.board.is_full():
            tally_tokens(self.players, self.board)
            self.state = "gameover"
        else:
            self.advance_turn()

    @staticmethod
    def _circuit_message(player, circuit_events):
        if not circuit_events:
            return None
        parts = []
        for event in circuit_events:
            text = f"{player.name} completed a circuit! +6 tokens"
            if event.bonus_bridge is not None:
                text += f", plus a bonus bridge worth {event.bonus_bridge.tokens} (owned {event.owned_count}/6 bridges)"
            parts.append(text)
        return " ".join(parts)

    def reset_to_setup(self):
        self.__init__()


async def main():
    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("Rainbow Connections")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 20)
    big_font = pygame.font.SysFont(None, 48)

    game = Game()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif game.state == "choose_players" and event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    num_players = event.key - pygame.K_0
                    game.start(num_players)
                elif game.state == "playing" and event.key == pygame.K_r:
                    if game.selected_hand_index is not None:
                        game.current_player.hand[game.selected_hand_index].rotate()
                elif game.state == "playing" and event.key == pygame.K_f:
                    if game.selected_hand_index is not None:
                        game.current_player.hand[game.selected_hand_index].flip()
            elif event.type == pygame.MOUSEBUTTONDOWN and game.state == "setup":
                if play_button_rect().collidepoint(event.pos):
                    game.state = "choose_players"
                elif how_to_play_button_rect().collidepoint(event.pos):
                    game.open_how_to_play()
            elif event.type == pygame.MOUSEBUTTONDOWN and game.state == "how_to_play":
                back_rect, next_rect = tutorial_button_rects()
                if tutorial_exit_button_rect().collidepoint(event.pos):
                    game.exit_how_to_play()
                elif back_rect.collidepoint(event.pos):
                    game.retreat_tutorial()
                elif next_rect.collidepoint(event.pos):
                    game.advance_tutorial()
            elif event.type == pygame.MOUSEBUTTONDOWN and game.state == "playing":
                hand_index = hand_tile_at_pixel(event.pos, game.current_player.hand)
                if hand_index is not None:
                    game.selected_hand_index = hand_index
                    game.hint = None
                else:
                    coord = cell_at_pixel(event.pos)
                    if coord is not None:
                        game.place_selected_tile(coord)
            elif event.type == pygame.MOUSEBUTTONDOWN and game.state == "priority_pass":
                game.state = "priority_select"
            elif event.type == pygame.MOUSEBUTTONDOWN and game.state == "priority_select":
                player = game.players[game.priority_index]
                hand_index = hand_tile_at_pixel(event.pos, player.hand)
                if hand_index is not None:
                    game.choose_priority_tile(hand_index)
            elif event.type == pygame.MOUSEBUTTONDOWN and game.state == "priority_reveal":
                game.acknowledge_priority_reveal()
            elif event.type == pygame.MOUSEBUTTONDOWN and game.state == "gameover":
                if new_game_button_rect(game.players).collidepoint(event.pos):
                    game.reset_to_setup()

        screen.fill(BG_COLOR)
        if game.state == "setup":
            draw_setup_screen(screen, font, big_font)
        elif game.state == "choose_players":
            draw_choose_players_screen(screen, font, big_font)
        elif game.state == "how_to_play":
            draw_how_to_play_screen(screen, font, big_font, game.tutorial_step)
        elif game.state == "priority_pass":
            draw_priority_pass_screen(screen, font, big_font, game.players[game.priority_index], game.redo_message)
        elif game.state == "priority_select":
            draw_priority_select_screen(screen, font, big_font, game.players[game.priority_index])
        elif game.state == "priority_reveal":
            draw_priority_reveal_screen(
                screen,
                font,
                big_font,
                game.players,
                game.turn_order,
                game.color_points,
                game.redo_message,
                game.priority_tie_pending,
            )
        elif game.state == "playing":
            draw_board(screen, game.board, font)
            draw_hand(screen, font, game.current_player, game.selected_hand_index)
            draw_color_points_hud(screen, font, game.color_points)
            draw_scoreboard(screen, font, game.players, game.board)
            help_text = font.render(
                "Click a tile, R to rotate, F to flip up/down, click a board cell to place. Esc to quit.",
                True,
                TEXT_COLOR,
            )
            screen.blit(help_text, (40, HAND_Y + HAND_TILE_SIZE * math.sqrt(3) / 2 + 20))
            if game.hint:
                hint_label = font.render(game.hint, True, (240, 120, 90))
                screen.blit(hint_label, (40, HAND_Y + HAND_TILE_SIZE * math.sqrt(3) / 2 + 44))
            if game.message:
                message_label = font.render(game.message, True, (255, 215, 0))
                screen.blit(message_label, (WINDOW_SIZE[0] / 2 - message_label.get_width() / 2, 10))
        elif game.state == "gameover":
            draw_gameover_screen(screen, font, big_font, game.players)

        pygame.display.flip()
        clock.tick(60)
        # Yields to the browser's event loop each frame - required for
        # pygbag/WASM builds, since the browser can't tolerate a blocking
        # synchronous loop on the main thread. A harmless no-op on desktop.
        await asyncio.sleep(0)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    asyncio.run(main())
