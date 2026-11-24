#!/usr/bin/env python3
"""
scripts/generate_snake.py
Procedural SVG & SMIL Interactive Snake and Terminal Generator for UAM Virtual Moodle.

Visual Composition:
- ViewBox: 0 0 750 400 with 100% transparent root background.
- Upper Section (Terminal Window): Crisp monospace console styling, window buttons,
  pure SMIL typewriter animation displaying confirmed user profile & UAM Virtual commands.
  Prompt and command share a single <text> run, so nothing overlaps whatever monospace
  font the viewer ends up with.
- Middle Section (HUD Bar): Retro score counter updating +100 per apple and live status badge.
- Lower Section (Snake Arena): 30x7 grid, up to 15 snake segments with directional eyes,
  procedural apples, burst shockwaves, and 2 patrolling neon sentinel drones. The whole
  body (not just the head) is planned around the drones, so they never touch the snake.

Zero JavaScript, Pure W3C SMIL Animation (<animate>, <animateTransform>, <clipPath>).
"""

import argparse
from collections import deque
import datetime
import heapq
import itertools
import os
import random
import sys
import xml.etree.ElementTree as ET

# --- Grid & Arena Geometry ---
VIEW_W = 750
VIEW_H = 400

GRID_W = 30
GRID_H = 7
CELL_SIZE = 23
SEG_SIZE = 19
OFFSET = (CELL_SIZE - SEG_SIZE) / 2 # 2.0px

ARENA_X = 20
ARENA_Y = 219
ARENA_W = 710
ARENA_H = 171
GRID_ORIGIN_X = ARENA_X + (ARENA_W - GRID_W * CELL_SIZE) / 2 # 30.0 px
GRID_ORIGIN_Y = ARENA_Y + (ARENA_H - GRID_H * CELL_SIZE) / 2 # 224.0 px

DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]

# Drones have periods 8 and 12 -> the arena state repeats every 24 steps.
DRONE_PERIOD = 24
MAX_MATCH_ATTEMPTS = 60
MAX_SEARCH_EXPANSIONS = 40000

FONT = 'font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"'

APPLE_PALETTE = [
    "#ff5f56", # Neon Red
    "#ffa657", # Cyber Amber
    "#d2a8ff", # Neon Purple
    "#58a6ff", # Cyber Blue
    "#56d364", # Bright Emerald
    "#f778ba", # Neon Rose
    "#e3b341", # Radiant Gold
]

# --- Drone Motion Generators ---
def drone_alpha_pos(step, col=9, min_r=1, max_r=5):
    """Drone Alpha: Vertical patrol at `col` between rows `min_r` and `max_r`."""
    span = max_r - min_r
    cycle = 2 * span
    rem = step % cycle
    r = min_r + rem if rem <= span else max_r - (rem - span)
    return (col, r)

def drone_beta_pos(step, row=3, min_c=18, max_c=24):
    """Drone Beta: Horizontal patrol at `row` between columns `min_c` and `max_c`."""
    span = max_c - min_c
    cycle = 2 * span
    rem = step % cycle
    c = min_c + rem if rem <= span else max_c - (rem - span)
    return (c, row)

def get_drone_obstacles(step, d_alpha_col, d_beta_row):
    return {
        drone_alpha_pos(step, col=d_alpha_col),
        drone_beta_pos(step, row=d_beta_row),
    }

# --- Snake Mechanics ---
def in_arena(cell):
    return 0 <= cell[0] < GRID_W and 0 <= cell[1] < GRID_H

def advance(body, cell, growth):
    """Moves the snake one cell. Returns (new_body, new_growth)."""
    if growth > 0:
        return (cell,) + body, growth - 1
    return (cell,) + body[:-1], growth

def move_is_clear(body, new_body, step, d_alpha_col, d_beta_row):
    """
    True if no drone touches any snake segment while moving from `step` to `step + 1`.
    Segments interpolate linearly between cells, so a drone must neither land on a cell the
    snake occupies before or after the move, nor leave a cell the snake is moving into.
    """
    drones_now = get_drone_obstacles(step, d_alpha_col, d_beta_row)
    drones_next = get_drone_obstacles(step + 1, d_alpha_col, d_beta_row)
    old_cells = set(body)
    new_cells = set(new_body)
    return not (drones_next & (old_cells | new_cells)) and not (drones_now & new_cells)

def free_space(body, limit):
    """Flood-fill reach from the head, capped at `limit`, treating the body as walls."""
    head = body[0]
    walls = set(body[1:])
    seen = {head}
    queue = deque([head])
    while queue and len(seen) < limit:
        cx, cy = queue.popleft()
        for dx, dy in DIRS:
            nxt = (cx + dx, cy + dy)
            if in_arena(nxt) and nxt not in seen and nxt not in walls:
                seen.add(nxt)
                queue.append(nxt)
    return len(seen)

def can_survive(body, growth, step, depth, d_alpha_col, d_beta_row, budget=None):
    """True if the snake has `depth` collision-free moves ahead of it (bounded DFS)."""
    budget = budget if budget is not None else [3000]
    if depth == 0:
        return True
    if budget[0] <= 0:
        return False
    budget[0] -= 1
    hx, hy = body[0]
    for dx, dy in DIRS:
        cell = (hx + dx, hy + dy)
        if not in_arena(cell):
            continue
        new_body, new_growth = advance(body, cell, growth)
        if cell in new_body[1:] or not move_is_clear(body, new_body, step, d_alpha_col, d_beta_row):
            continue
        if can_survive(new_body, new_growth, step + 1, depth - 1, d_alpha_col, d_beta_row, budget):
            return True
    return False

# --- Spatio-Temporal Pathfinder ---
def plan_route(body, step, growth, is_goal, heuristic, d_alpha_col, d_beta_row, allow_offscreen=False):
    """
    A* in (body, t mod 24, growth) state space.
    Every move is validated against both drones for the full body, not just the head.
    With `allow_offscreen`, the head may slide off the right edge (exit phase) but only
    keeps moving straight once it is out.
    Returns the list of (body, growth) states after each move, or None.
    """
    tie = itertools.count()
    start = (tuple(body), growth)
    heap = [(heuristic(start[0]), next(tie), start, step, None)]
    seen = {(start[0], step % DRONE_PERIOD, growth)}
    expansions = 0

    while heap and expansions < MAX_SEARCH_EXPANSIONS:
        _, _, state, t, parent = heapq.heappop(heap)
        node = (state, parent)
        expansions += 1
        cur_body, cur_growth = state
        g = t - step

        if g > 0 and is_goal(cur_body, cur_growth, t):
            route = []
            while node[1] is not None:
                route.append(node[0])
                node = node[1]
            return route[::-1]

        hx, hy = cur_body[0]
        moves = [(1, 0)] if not in_arena(cur_body[0]) else DIRS
        for dx, dy in moves:
            cell = (hx + dx, hy + dy)
            if not in_arena(cell) and not (allow_offscreen and cell[0] >= GRID_W and 0 <= cell[1] < GRID_H):
                continue
            new_body, new_growth = advance(cur_body, cell, cur_growth)
            if cell in new_body[1:]:
                continue
            if not move_is_clear(cur_body, new_body, t, d_alpha_col, d_beta_row):
                continue
            key = (new_body, (t + 1) % DRONE_PERIOD, new_growth)
            if key in seen:
                continue
            seen.add(key)
            heapq.heappush(heap, (g + 1 + heuristic(new_body), next(tie), (new_body, new_growth), t + 1, node))

    return None

# --- Procedural Apple Generator ---
def generate_apples(rng, d_alpha_col, d_beta_row, count=7):
    """Generates `count` strategic apples across distinct board sectors."""
    regions = [
        (3, 6, 1, 5),    # Sector 0: Entry corridor
        (10, 13, 1, 5),  # Sector 1: Past Alpha Sentinel
        (15, 17, 1, 3),  # Sector 2: Upper Central
        (20, 24, 4, 6),  # Sector 3: Below Beta Sentinel
        (14, 18, 4, 6),  # Sector 4: Lower Central
        (7, 9, 0, 2),    # Sector 5: High Northwest
        (25, 27, 2, 4),  # Sector 6: Exit approach
    ]

    apples = []
    chosen_coords = set()

    for i in range(min(count, len(regions))):
        c_min, c_max, r_min, r_max = regions[i]
        candidates = []
        for c in range(c_min, c_max + 1):
            for r in range(r_min, r_max + 1):
                if (c, r) in chosen_coords or c == d_alpha_col or (r == d_beta_row and 18 <= c <= 24):
                    continue
                candidates.append((c, r))
        pos = rng.choice(candidates) if candidates else (c_min, r_min)
        chosen_coords.add(pos)
        apples.append({
            "idx": i,
            "pos": pos,
            "color": APPLE_PALETTE[i % len(APPLE_PALETTE)],
        })

    return apples

# --- Match Simulation ---
def find_drone_contacts(history, d_alpha_col, d_beta_row):
    """Returns every step at which a drone touches any snake segment (empty list = clean match)."""
    contacts = []
    for k in range(len(history) - 1):
        if not move_is_clear(tuple(history[k]), tuple(history[k + 1]), k, d_alpha_col, d_beta_row):
            contacts.append(k)
    return contacts

def status_for(head, step, apple_idx, d_alpha_col, d_beta_row):
    d_alpha = drone_alpha_pos(step, d_alpha_col)
    d_beta = drone_beta_pos(step, d_beta_row)
    dist_alpha = abs(head[0] - d_alpha[0]) + abs(head[1] - d_alpha[1])
    dist_beta = abs(head[0] - d_beta[0]) + abs(head[1] - d_beta[1])
    if dist_alpha <= 2 or dist_beta <= 2:
        return ("EVADE", "EVADING NEON DRONE")
    return ("HUNT", f"HUNTING APPLE #{apple_idx + 1}")

def play_match(apples_spec, d_alpha_col, d_beta_row):
    """
    Plays one deterministic match:
    1. Snake enters from off-screen left.
    2. Navigates past Drone Alpha and Beta eating procedural apples.
    3. Snake length dynamically grows up to 15 segments.
    4. Snake exits off-screen right, then drones keep patrolling until their cycle closes
       so the loop restarts seamlessly.
    Returns None if the snake cannot finish cleanly.
    """
    # Initial snake off-screen to the left facing east
    start_row = apples_spec[0]["pos"][1]
    body = tuple((-1 - i, start_row) for i in range(4))
    growth = 0
    history = [list(body)]
    apple_events = []
    status_timeline = [] # (step, status_type, extra_text)
    spawn_step = 0

    # Total growth needed: 15 - 4 = 11 segments
    # Apples: 7 apples -> [2, 2, 2, 1, 1, 1, 2] = 11
    growth_schedule = [2, 2, 2, 1, 1, 1, 2]

    def record(route, apple_idx, label=None):
        for new_body, new_growth in route:
            step = len(history) - 1
            if label:
                status_timeline.append((step, "EXIT", label))
            else:
                status_timeline.append((step,) + status_for(history[-1][0], step, apple_idx, d_alpha_col, d_beta_row))
            history.append(list(new_body))
        return route[-1]

    for apple_idx, apple in enumerate(apples_spec):
        goal = apple["pos"]
        grow_amount = growth_schedule[apple_idx % len(growth_schedule)]

        def reached(b, gr, t, goal=goal, grow_amount=grow_amount):
            # Only accept the apple if the snake can still get its whole body out of the drones' way
            if b[0] != goal:
                return False
            needed = len(b) + gr + grow_amount
            return (free_space(b, needed) >= needed
                    and can_survive(b, gr + grow_amount, t, needed, d_alpha_col, d_beta_row))

        def toward(b, goal=goal):
            return abs(b[0][0] - goal[0]) + abs(b[0][1] - goal[1])

        route = plan_route(body, len(history) - 1, growth, reached, toward, d_alpha_col, d_beta_row)
        if route is None:
            return None
        body, growth = record(route, apple_idx)

        eat_step = len(history) - 1
        apple_events.append({
            "idx": apple_idx,
            "spawn_step": spawn_step,
            "eat_step": eat_step,
            "pos": goal,
            "color": apple["color"],
        })
        spawn_step = eat_step + 1
        status_timeline.append((eat_step, "EAT", "TARGET SECURED (+100)"))
        growth += grow_amount

    # Exit phase: Snake navigates off-screen to the right
    def fully_out(b, gr, t):
        return all(x >= GRID_W for x, _ in b)

    def to_exit(b):
        return max(0, GRID_W + len(b) - 1 - b[0][0])

    route = plan_route(body, len(history) - 1, growth, fully_out, to_exit,
                       d_alpha_col, d_beta_row, allow_offscreen=True)
    if route is None:
        return None
    body, growth = record(route, len(apples_spec), label="MISSION COMPLETE")

    # Let the drones finish their patrol cycle so the loop seam is invisible
    while (len(history) - 1) % DRONE_PERIOD != 0:
        status_timeline.append((len(history) - 1, "EXIT", "MISSION COMPLETE"))
        history.append(list(body))

    # Append terminal status for final step
    status_timeline.append((len(history) - 1, "EXIT", "MISSION COMPLETE"))

    if find_drone_contacts(history, d_alpha_col, d_beta_row):
        return None

    return history, apple_events, status_timeline

def simulate_match(seed, apple_count=7):
    """Simulates a full deterministic match for `seed`, re-rolling the layout until it plays cleanly."""
    rng = random.Random(seed)
    for _ in range(MAX_MATCH_ATTEMPTS):
        d_alpha_col = rng.choice([9, 10])
        d_beta_row = rng.choice([3, 4])
        apples_spec = generate_apples(rng, d_alpha_col, d_beta_row, count=apple_count)

        result = play_match(apples_spec, d_alpha_col, d_beta_row)
        if result is None:
            continue

        history, apple_events, status_timeline = result
        return {
            "seed": seed,
            "history": history,
            "apple_events": apple_events,
            "status_timeline": status_timeline,
            "d_alpha_col": d_alpha_col,
            "d_beta_row": d_beta_row,
        }

    raise RuntimeError(f"Could not build a collision-free match for seed {seed}")

# --- SMIL Helpers ---
# Terminal script timing, in seconds of an 18s reference loop (scaled to --duration).
TERM_REF = 18.0
TERM_RESET = 17.5

def fmt_kt(values):
    return ";".join(f"{v:.5f}" for v in values)

def window_keys(start, end, on, off):
    """keyTimes/values for something shown from `start` to `end` seconds of the terminal script.
    Items shown at t=0 are shown again after the reset, so the loop seam matches the first frame."""
    kt = [0.0]
    vals = [on if start <= 0 else off]
    if start > 0:
        kt.append(start / TERM_REF)
        vals.append(on)
    if end < TERM_RESET:
        kt.append(end / TERM_REF)
        vals.append(off)
    kt.append(TERM_RESET / TERM_REF)
    vals.append(on if start <= 0 else off)
    kt.append(1.0)
    vals.append(vals[-1])
    return fmt_kt(kt), ";".join(vals)

def discrete_anim(attr, total_time, start, end, on, off):
    kt, vals = window_keys(start, end, on, off)
    return (f'<animate attributeName="{attr}" dur="{total_time:.2f}s" repeatCount="indefinite" '
            f'calcMode="discrete" keyTimes="{kt}" values="{vals}"/>')

def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# --- SMIL SVG Builder ---
def build_terminal(total_time):
    svg = []
    svg.append('  <!-- ================= TERMINAL SECTION ================= -->')
    svg.append('  <g id="terminal-window">')
    # Terminal Window Container
    svg.append('    <rect x="20" y="10" width="710" height="176" rx="8" ry="8" '
               'fill="#0d1117" fill-opacity="0.80" stroke="#30363d" stroke-width="1"/>')
    # Window Title Bar
    svg.append('    <path d="M 20 18 A 8 8 0 0 1 28 10 L 722 10 A 8 8 0 0 1 730 18 L 730 32 L 20 32 Z" '
               'fill="#161b22" fill-opacity="0.85"/>')
    svg.append('    <line x1="20" y1="32" x2="730" y2="32" stroke="#30363d" stroke-width="1"/>')

    # Window Controls (Red, Yellow, Green)
    svg.append('    <circle cx="36" cy="21" r="4.2" fill="#ff5f56"/>')
    svg.append('    <circle cx="50" cy="21" r="4.2" fill="#ffbd2e"/>')
    svg.append('    <circle cx="64" cy="21" r="4.2" fill="#27c93f"/>')

    # Title Bar Text
    svg.append(f'    <text x="375" y="25" {FONT} font-size="11" fill="#8b949e" text-anchor="middle">'
               'robertofabiot@uam-virtual:~</text>')

    prompt_text = "[ro@archlinux ~]$ "
    prompt = ('<tspan fill="#58a6ff">[ro@archlinux</tspan><tspan fill="#8b949e"> </tspan>'
              '<tspan fill="#3fb950">~</tspan><tspan fill="#8b949e">]$ </tspan>')

    # (command, prompt_at, type_start, type_end, output_at, output lines)
    script = [
        ("whoami", 0.0, 0.3, 1.2, 1.5, [
            ('#f0f6fc', 'Roberto Fabio Tercero <tspan fill="#58a6ff">· @robertofabiot</tspan>'),
            ('#8b949e', '<tspan fill="#3fb950">↳</tspan> Ingeniería en Sistemas @ '
                        '<tspan fill="#e6edf3">Universidad Americana (UAM)</tspan>'),
        ]),
        ("uam-virtual --status", 3.2, 3.5, 5.2, 5.4, [
            ('#f0f6fc', '<tspan fill="#3fb950">● Conectado:</tspan> '
                        '<tspan fill="#79c0ff">uamvirtual.uam.edu.ni/grado</tspan>'),
            ('#8b949e', '<tspan fill="#3fb950">↳</tspan> Cursos activos: '
                        '<tspan fill="#ffa657">BD2</tspan> · <tspan fill="#ffa657">Prog. Escritorio</tspan> · '
                        '<tspan fill="#ffa657">Redes II</tspan> · <tspan fill="#ffa657">Ed. Ambiental</tspan>'),
        ]),
        ("fastfetch --stack", 7.5, 7.8, 9.4, 9.6, [
            ('#f0f6fc', '<tspan fill="#d2a8ff">OS:</tspan> Arch Linux x86_64 · '
                        '<tspan fill="#d2a8ff">WM:</tspan> Niri (Wayland)'),
            ('#8b949e', '<tspan fill="#58a6ff">Stack:</tspan> '
                        '<tspan fill="#ff7b72">Rust</tspan> · <tspan fill="#3fb950">Python</tspan> · '
                        '<tspan fill="#ffa657">Java</tspan> · <tspan fill="#58a6ff">Linux</tspan>'),
        ]),
        # Idle prompt waiting for the next command
        ("", 10.2, 10.2, 10.2, None, []),
    ]

    line_h = 13.0
    block_gap = 3.0
    y = 48.0
    for i, (cmd, prompt_at, type_start, type_end, output_at, outputs) in enumerate(script):
        next_prompt = script[i + 1][1] if i + 1 < len(script) else TERM_RESET

        # Command characters are revealed one by one with `display`, so the cursor that
        # follows them in the same text run always sits right after the last typed char.
        typed = []
        for c_idx, ch in enumerate(cmd):
            t_char = type_start + (type_end - type_start) * c_idx / max(1, len(cmd) - 1)
            typed.append(f'<tspan display="none">{discrete_anim("display", total_time, t_char, TERM_RESET, "inline", "none")}'
                         f'{esc(ch)}</tspan>')
        cursor = (f'<tspan fill="#58a6ff" display="none">'
                  f'{discrete_anim("display", total_time, prompt_at, next_prompt, "inline", "none")}'
                  '<animate attributeName="fill-opacity" values="1;0" calcMode="discrete" dur="1s" repeatCount="indefinite"/>'
                  '▋</tspan>')

        svg.append(f'    <!-- Prompt {i + 1} -->')
        prompt_visibility = "" if prompt_at <= 0 else ' opacity="0"'
        svg.append(f'    <text x="36" y="{y:.1f}" {FONT} font-size="11.5" xml:space="preserve" '
                   f'aria-label="{esc(prompt_text + cmd).strip()}"{prompt_visibility}>'
                   + ("" if prompt_at <= 0 else discrete_anim("opacity", total_time, prompt_at, TERM_RESET, "1", "0"))
                   + prompt
                   + f'<tspan font-weight="bold" fill="#f0f6fc">{"".join(typed)}</tspan>'
                   + cursor
                   + '</text>')
        y += line_h

        if outputs:
            svg.append('    <g opacity="0">')
            svg.append('      ' + discrete_anim("opacity", total_time, output_at, TERM_RESET, "1", "0"))
            for fill, markup in outputs:
                svg.append(f'      <text x="36" y="{y:.1f}" {FONT} font-size="11.5" fill="{fill}">{markup}</text>')
                y += line_h
            svg.append('    </g>')
        y += block_gap

    svg.append('  </g>')
    return svg

def build_svg(sim_data, total_duration=18.0):
    history = sim_data["history"]
    apple_events = sim_data["apple_events"]
    status_timeline = sim_data["status_timeline"]
    d_alpha_col = sim_data["d_alpha_col"]
    d_beta_row = sim_data["d_beta_row"]

    total_steps = len(history) - 1
    total_time = total_duration

    # KeyTimes sequence for step increments
    key_times = [f"{i / total_steps:.5f}" for i in range(total_steps + 1)]
    key_times[-1] = "1"
    key_times_str = ";".join(key_times)

    svg = []
    svg.append('<?xml version="1.0" encoding="UTF-8"?>')
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW_W} {VIEW_H}" width="100%" height="100%">')

    # ==========================================
    # DEFS & FILTERS
    # ==========================================
    svg.append('  <defs>')
    # Board clip
    svg.append(f'    <clipPath id="arena-clip">')
    svg.append(f'      <rect x="{ARENA_X}" y="{ARENA_Y}" width="{ARENA_W}" height="{ARENA_H}" rx="8" ry="8"/>')
    svg.append('    </clipPath>')

    # Neon glow filters
    svg.append('    <filter id="glow-snake" x="-20%" y="-20%" width="140%" height="140%">')
    svg.append('      <feDropShadow dx="0" dy="0" stdDeviation="1.5" flood-color="#39d353" flood-opacity="0.6"/>')
    svg.append('    </filter>')
    svg.append('    <filter id="glow-drone-alpha" x="-30%" y="-30%" width="160%" height="160%">')
    svg.append('      <feDropShadow dx="0" dy="0" stdDeviation="2.0" flood-color="#ff5f56" flood-opacity="0.7"/>')
    svg.append('    </filter>')
    svg.append('    <filter id="glow-drone-beta" x="-30%" y="-30%" width="160%" height="160%">')
    svg.append('      <feDropShadow dx="0" dy="0" stdDeviation="2.0" flood-color="#58a6ff" flood-opacity="0.7"/>')
    svg.append('    </filter>')
    svg.append('  </defs>')

    # ==========================================
    # SECTION 1: UPPER TERMINAL WINDOW (y=10..186)
    # ==========================================
    svg.extend(build_terminal(total_time))

    # ==========================================
    # SECTION 2: MIDDLE RETRO HUD BAR (y=192..213)
    # ==========================================
    hud_y = 207
    svg.append('  <!-- ================= RETRO HUD BAR ================= -->')
    svg.append('  <g id="hud-bar">')
    # Score label
    svg.append(f'    <text x="24" y="{hud_y}" {FONT} font-size="12" font-weight="bold" fill="#8b949e">SCORE:</text>')

    # Score Value Multi-state (+100 per apple)
    eat_steps = [app["eat_step"] for app in apple_events]
    total_apples = len(apple_events)

    for score_idx in range(total_apples + 1):
        score_val = f"{score_idx * 100:04d}"
        if score_idx == 0:
            t_end = eat_steps[0] / total_steps
            s_kt = [0.0, t_end, 1.0]
            s_op = ["1", "0", "0"]
        elif score_idx < total_apples:
            t_start = eat_steps[score_idx - 1] / total_steps
            t_end = eat_steps[score_idx] / total_steps
            s_kt = [0.0, t_start, t_end, 1.0]
            s_op = ["0", "1", "0", "0"]
        else:
            t_start = eat_steps[-1] / total_steps
            s_kt = [0.0, t_start, 1.0]
            s_op = ["0", "1", "1"]

        svg.append(f'    <text x="82" y="{hud_y}" {FONT} font-size="13" font-weight="bold" fill="#39d353" opacity="0">'
                   f'<animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'calcMode="discrete" keyTimes="{fmt_kt(s_kt)}" values="{";".join(s_op)}"/>{score_val}</text>')

    # Dynamic Status Telemetry Badge (right-aligned with the arena edge)
    badge_w = 240
    badge_x = ARENA_X + ARENA_W - badge_w
    svg.append('    <!-- Status Telemetry Badge Container -->')
    svg.append(f'    <rect x="{badge_x}" y="{hud_y - 15}" width="{badge_w}" height="21" rx="4" ry="4" '
               'fill="#161b22" fill-opacity="0.85" stroke="#30363d" stroke-width="1"/>')

    # Compress status intervals
    intervals = []
    curr_status = None
    start_s = 0

    for step_num, st_type, st_label in status_timeline:
        key = (st_type, st_label)
        if key != curr_status:
            if curr_status is not None:
                intervals.append((start_s, step_num, curr_status[0], curr_status[1]))
            curr_status = key
            start_s = step_num
    if curr_status is not None:
        intervals.append((start_s, total_steps, curr_status[0], curr_status[1]))

    for int_start, int_end, st_type, st_label in intervals:
        if int_end <= int_start:
            continue
        f_start = int_start / total_steps
        f_end = int_end / total_steps

        if f_start <= 0.00001:
            st_kt = [0.0, f_end, 1.0]
            st_op = ["1", "0", "0"]
        elif f_end >= 0.99999:
            st_kt = [0.0, f_start, 1.0]
            st_op = ["0", "1", "1"]
        else:
            st_kt = [0.0, f_start, f_end, 1.0]
            st_op = ["0", "1", "0", "0"]

        # Theme color per status
        if st_type == "EVADE":
            txt_color = "#ffa657"
            badge_icon = "▲ "
        elif st_type == "EAT":
            txt_color = "#58a6ff"
            badge_icon = "★ "
        elif st_type == "EXIT":
            txt_color = "#39d353"
            badge_icon = "✔ "
        else:
            txt_color = "#3fb950"
            badge_icon = "● "

        svg.append(f'    <text x="{badge_x + badge_w / 2:.1f}" y="{hud_y - 1}" {FONT} font-size="10.5" font-weight="bold" '
                   f'fill="{txt_color}" text-anchor="middle" opacity="0">'
                   f'<animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'calcMode="discrete" keyTimes="{fmt_kt(st_kt)}" values="{";".join(st_op)}"/>'
                   f'{badge_icon}{st_label}</text>')
    svg.append('  </g>')

    # ==========================================
    # SECTION 3: LOWER SNAKE ARENA (y=219..390)
    # 100% Transparent Canvas: Grid dots and frame border with fill="none"
    # ==========================================
    svg.append('  <!-- ================= SNAKE ARENA ================= -->')
    svg.append(f'  <g id="snake-arena">')
    # Arena Border (fill="none" ensures full background transparency)
    svg.append(f'    <rect x="{ARENA_X}" y="{ARENA_Y}" width="{ARENA_W}" height="{ARENA_H}" rx="8" ry="8" '
               f'fill="none" stroke="#30363d" stroke-width="1"/>')

    # Subtle Grid Dots
    svg.append('    <g id="grid-dots" fill="#30363d" opacity="0.35">')
    for c in range(1, GRID_W):
        for r in range(1, GRID_H):
            gx = GRID_ORIGIN_X + c * CELL_SIZE
            gy = GRID_ORIGIN_Y + r * CELL_SIZE
            svg.append(f'      <circle cx="{gx:.1f}" cy="{gy:.1f}" r="0.8"/>')
    svg.append('    </g>')

    # Arena Clipped Area for Game Entities
    svg.append('    <g clip-path="url(#arena-clip)">')

    # --- 1. PROCEDURAL APPLES & EAT BURSTS ---
    for apple in apple_events:
        idx = apple["idx"]
        ax, ay = apple["pos"]
        color = apple["color"]
        cx = GRID_ORIGIN_X + ax * CELL_SIZE + CELL_SIZE / 2
        cy = GRID_ORIGIN_Y + ay * CELL_SIZE + CELL_SIZE / 2

        sp_f = apple["spawn_step"] / total_steps
        et_f = apple["eat_step"] / total_steps

        # Discrete visibility: visible from spawn to eat
        if sp_f <= 0.00001:
            app_kt = [0.0, et_f, 1.0]
            app_op = ["1", "0", "0"]
        else:
            app_kt = [0.0, sp_f, et_f, 1.0]
            app_op = ["0", "1", "0", "0"]

        svg.append(f'      <!-- Apple #{idx} ({color}) at ({ax}, {ay}) -->')
        svg.append(f'      <g id="apple-{idx}" opacity="0">')
        svg.append(f'        <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'calcMode="discrete" keyTimes="{fmt_kt(app_kt)}" values="{";".join(app_op)}"/>')
        # Apple Body with Pulsing SMIL
        svg.append(f'        <circle cx="{cx:.1f}" cy="{cy:.1f}" r="7.0" fill="{color}">')
        svg.append(f'          <animate attributeName="r" values="6.4;7.8;6.4" dur="0.85s" repeatCount="indefinite"/>')
        svg.append('        </circle>')
        # Apple Stem & Leaf
        svg.append(f'        <path d="M {cx-0.5:.1f} {cy-6.5:.1f} Q {cx+1.0:.1f} {cy-9.5:.1f} {cx+3.8:.1f} {cy-8.8:.1f}" '
                   f'fill="none" stroke="#56d364" stroke-width="1.3" stroke-linecap="round"/>')
        # Specular Highlight
        svg.append(f'        <circle cx="{cx-2.2:.1f}" cy="{cy-2.2:.1f}" r="1.8" fill="#ffffff" opacity="0.65"/>')
        svg.append('      </g>')

        # Eating Shockwave & Burst Effect
        burst_dur = 0.35 / total_time
        b_start = et_f
        b_end = min(1.0, b_start + burst_dur)
        eps = 0.00001

        b_kt_str = fmt_kt([0.0, max(0.0, b_start - eps), b_start, b_end, 1.0])

        # Expanding Shockwave Ring
        svg.append(f'      <!-- Burst Ring Apple #{idx} -->')
        svg.append(f'      <circle cx="{cx:.1f}" cy="{cy:.1f}" fill="none" stroke="{color}" stroke-width="2" opacity="0">')
        svg.append(f'        <animate attributeName="r" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'keyTimes="{b_kt_str}" values="2;2;2;16;16"/>')
        svg.append(f'        <animate attributeName="stroke-width" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'keyTimes="{b_kt_str}" values="2.5;2.5;2.5;0.5;0.5"/>')
        svg.append(f'        <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'keyTimes="{b_kt_str}" values="0;0;0.95;0;0"/>')
        svg.append('      </circle>')

        # Floating +100 Score Popup at Apple coordinates
        svg.append(f'      <text x="{cx:.1f}" y="{cy:.1f}" {FONT} font-size="10.5" font-weight="bold" '
                   f'fill="{color}" text-anchor="middle" opacity="0">')
        svg.append(f'        <animate attributeName="y" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'keyTimes="{b_kt_str}" values="{cy:.1f};{cy:.1f};{cy:.1f};{cy-14.0:.1f};{cy-14.0:.1f}"/>')
        svg.append(f'        <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'keyTimes="{b_kt_str}" values="0;0;1.0;0;0"/>+100</text>')

        # 4 Kinetic Spark Particles
        particle_vectors = [(13, 0), (-13, 0), (0, 13), (0, -13)]
        for pdx, pdy in particle_vectors:
            cx_vals = f"{cx:.1f};{cx:.1f};{cx:.1f};{cx+pdx:.1f};{cx+pdx:.1f}"
            cy_vals = f"{cy:.1f};{cy:.1f};{cy:.1f};{cy+pdy:.1f};{cy+pdy:.1f}"
            svg.append(f'      <circle r="1.8" fill="{color}" opacity="0">')
            svg.append(f'        <animate attributeName="cx" dur="{total_time:.2f}s" repeatCount="indefinite" '
                       f'keyTimes="{b_kt_str}" values="{cx_vals}"/>')
            svg.append(f'        <animate attributeName="cy" dur="{total_time:.2f}s" repeatCount="indefinite" '
                       f'keyTimes="{b_kt_str}" values="{cy_vals}"/>')
            svg.append(f'        <animate attributeName="r" dur="{total_time:.2f}s" repeatCount="indefinite" '
                       f'keyTimes="{b_kt_str}" values="2;2;2;0.5;0.5"/>')
            svg.append(f'        <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" '
                       f'keyTimes="{b_kt_str}" values="0;0;0.95;0;0"/>')
            svg.append('      </circle>')

    # --- 2. NEON PATROL DRONES (Alpha & Beta) ---
    # Wings stay within 12.2px of the centre, so they never reach a neighbouring cell's segment.
    drones = [
        ("alpha", "Vertical", "#ff5f56", "#ff7b72", lambda k: drone_alpha_pos(k, d_alpha_col),
         '<polygon points="0,-8 8,0 0,8 -8,0" fill="#161b22" stroke="#ff5f56" stroke-width="1.6"/>',
         [(-10, 0), (10, 0)]),
        ("beta", "Horizontal", "#58a6ff", "#79c0ff", lambda k: drone_beta_pos(k, d_beta_row),
         '<polygon points="-8,-4 0,-8 8,-4 8,4 0,8 -8,4" fill="#161b22" stroke="#58a6ff" stroke-width="1.6"/>',
         [(0, -10), (0, 10)]),
    ]
    for name, kind, color, core, pos_fn, hull, wings in drones:
        coords = []
        for k in range(total_steps + 1):
            col, row = pos_fn(k)
            px = GRID_ORIGIN_X + col * CELL_SIZE + CELL_SIZE / 2
            py = GRID_ORIGIN_Y + row * CELL_SIZE + CELL_SIZE / 2
            coords.append(f"{px:.1f},{py:.1f}")

        (w1x, w1y), (w2x, w2y) = wings
        svg.append(f'      <!-- Drone {name.capitalize()} ({kind} Sentinel) -->')
        svg.append(f'      <g id="drone-{name}" filter="url(#glow-drone-{name})">')
        svg.append(f'        <animateTransform attributeName="transform" type="translate" dur="{total_time:.2f}s" '
                   f'repeatCount="indefinite" calcMode="linear" keyTimes="{key_times_str}" values="{";".join(coords)}"/>')
        # Radar Pulsing Ring
        svg.append(f'        <circle cx="0" cy="0" r="14" fill="none" stroke="{color}" stroke-width="1.2" '
                   'stroke-dasharray="3,3" opacity="0.6">')
        svg.append('          <animate attributeName="r" values="9;17;9" dur="1.8s" repeatCount="indefinite"/>')
        svg.append('          <animate attributeName="opacity" values="0.8;0.1;0.8" dur="1.8s" repeatCount="indefinite"/>')
        svg.append('        </circle>')
        # Drone Hull & Wings
        svg.append(f'        {hull}')
        svg.append(f'        <circle cx="0" cy="0" r="2.8" fill="{core}"/>')
        svg.append(f'        <line x1="{w1x}" y1="{w1y}" x2="{w2x}" y2="{w2y}" stroke="{color}" stroke-width="1.2" '
                   'stroke-linecap="round"/>')
        svg.append(f'        <circle cx="{w1x}" cy="{w1y}" r="2.2" fill="{color}"/>')
        svg.append(f'        <circle cx="{w2x}" cy="{w2y}" r="2.2" fill="{color}"/>')
        svg.append('      </g>')

    # --- 3. SNAKE BODY SEGMENTS (Rendered Tail to Head) ---
    max_segments = max(len(s) for s in history)
    # Head (#39d353 RGB: 57, 211, 83) -> Tail (#14532d RGB: 20, 83, 45)
    for s in range(max_segments - 1, -1, -1):
        ratio = s / (max_segments - 1) if max_segments > 1 else 0
        r_col = int(57 + (20 - 57) * ratio)
        g_col = int(211 + (83 - 211) * ratio)
        b_col = int(83 + (45 - 83) * ratio)
        seg_color = f"#{r_col:02x}{g_col:02x}{b_col:02x}"

        x_vals = []
        y_vals = []
        opac_vals = []

        for k in range(total_steps + 1):
            snake_k = history[k]
            # Not-yet-grown segments wait hidden on the tail
            cell_x, cell_y = snake_k[s] if s < len(snake_k) else snake_k[-1]
            x_vals.append(f"{GRID_ORIGIN_X + cell_x * CELL_SIZE + OFFSET:.1f}")
            y_vals.append(f"{GRID_ORIGIN_Y + cell_y * CELL_SIZE + OFFSET:.1f}")
            opac_vals.append("1" if s < len(snake_k) else "0")

        rx = "6" if s == 0 else "4.5"

        svg.append(f'      <!-- Snake Segment #{s} ({seg_color}) -->')
        svg.append(f'      <rect width="{SEG_SIZE}" height="{SEG_SIZE}" rx="{rx}" ry="{rx}" '
                   f'fill="{seg_color}" filter="url(#glow-snake)">')
        svg.append(f'        <animate attributeName="x" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'calcMode="linear" keyTimes="{key_times_str}" values="{";".join(x_vals)}"/>')
        svg.append(f'        <animate attributeName="y" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'calcMode="linear" keyTimes="{key_times_str}" values="{";".join(y_vals)}"/>')
        svg.append(f'        <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'calcMode="discrete" keyTimes="{key_times_str}" values="{";".join(opac_vals)}"/>')
        svg.append('      </rect>')

    # --- 4. SNAKE DIRECTIONAL EYES & PUPILS ---
    eye1_x, eye1_y = [], []
    eye2_x, eye2_y = [], []
    pup1_x, pup1_y = [], []
    pup2_x, pup2_y = [], []

    for k in range(total_steps + 1):
        hx, hy = history[k][0]
        nhx, nhy = history[k + 1][0] if k < total_steps else (hx + 1, hy)
        dx, dy = nhx - hx, nhy - hy
        if (dx, dy) == (0, 0):
            dx, dy = 1, 0 # parked off-screen after exiting right

        bx = GRID_ORIGIN_X + hx * CELL_SIZE
        by = GRID_ORIGIN_Y + hy * CELL_SIZE

        if dx == 1 and dy == 0: # Facing Right
            e1 = (bx + 15.0, by + 6.5)
            e2 = (bx + 15.0, by + 16.5)
            p1 = (bx + 16.0, by + 6.5)
            p2 = (bx + 16.0, by + 16.5)
        elif dx == -1 and dy == 0: # Facing Left
            e1 = (bx + 8.0, by + 6.5)
            e2 = (bx + 8.0, by + 16.5)
            p1 = (bx + 7.0, by + 6.5)
            p2 = (bx + 7.0, by + 16.5)
        elif dx == 0 and dy == 1: # Facing Down
            e1 = (bx + 6.5, by + 15.0)
            e2 = (bx + 16.5, by + 15.0)
            p1 = (bx + 6.5, by + 16.0)
            p2 = (bx + 16.5, by + 16.0)
        else: # Facing Up
            e1 = (bx + 6.5, by + 8.0)
            e2 = (bx + 16.5, by + 8.0)
            p1 = (bx + 6.5, by + 7.0)
            p2 = (bx + 16.5, by + 7.0)

        eye1_x.append(f"{e1[0]:.1f}")
        eye1_y.append(f"{e1[1]:.1f}")
        eye2_x.append(f"{e2[0]:.1f}")
        eye2_y.append(f"{e2[1]:.1f}")
        pup1_x.append(f"{p1[0]:.1f}")
        pup1_y.append(f"{p1[1]:.1f}")
        pup2_x.append(f"{p2[0]:.1f}")
        pup2_y.append(f"{p2[1]:.1f}")

    for n, (xs, ys, r, fill) in enumerate([
        (eye1_x, eye1_y, "2.4", "#ffffff"), (pup1_x, pup1_y, "1.3", "#0d1117"),
        (eye2_x, eye2_y, "2.4", "#ffffff"), (pup2_x, pup2_y, "1.3", "#0d1117"),
    ]):
        if n % 2 == 0:
            svg.append(f'      <!-- Snake Eye {n // 2 + 1} & Pupil {n // 2 + 1} -->')
        svg.append(f'      <circle r="{r}" fill="{fill}">')
        svg.append(f'        <animate attributeName="cx" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'calcMode="linear" keyTimes="{key_times_str}" values="{";".join(xs)}"/>')
        svg.append(f'        <animate attributeName="cy" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'calcMode="linear" keyTimes="{key_times_str}" values="{";".join(ys)}"/>')
        svg.append('      </circle>')

    svg.append('    </g>') # End arena clip
    svg.append('  </g>')   # End snake arena

    svg.append('</svg>')
    return "\n".join(svg)

# --- Validation Engine ---
def validate_svg(svg_content):
    """Rigorous internal integrity validation before saving."""
    # 1. XML Well-formedness
    try:
        tree = ET.fromstring(svg_content)
    except ET.ParseError as e:
        raise ValueError(f"XML ParseError: {e}")

    # 2. Assert Pure SMIL (Zero <script> tags)
    if "<script" in svg_content.lower():
        raise ValueError("Security violation: <script> tag detected in SVG output!")

    scripts = tree.findall(".//{http://www.w3.org/2000/svg}script")
    if len(scripts) > 0:
        raise ValueError("Security violation: XML namespaced <script> detected!")

    # 3. Assert Zero Inline JS Event Handlers
    for event in ["onload", "onclick", "onmouseover", "onerror"]:
        if f"{event}=" in svg_content.lower():
            raise ValueError(f"Security violation: Inline event handler '{event}' detected!")

    # 4. Assert 100% Canvas Transparency (No root solid background rect)
    for elem in tree.findall(".//{http://www.w3.org/2000/svg}rect"):
        w = elem.get("width", "")
        h = elem.get("height", "")
        fill = elem.get("fill", "")
        if (w in ["100%", str(VIEW_W)] or h in ["100%", str(VIEW_H)]) and fill not in ["none", ""]:
            raise ValueError(f"Transparency violation: Found canvas-filling rect with fill='{fill}'!")

    return True

# --- Main CLI Entrypoint ---
def main():
    parser = argparse.ArgumentParser(
        description="Generate interactive procedural SMIL Snake & Terminal SVG for UAM Virtual."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="snake-uam.svg",
        help="Path for generated SVG output (default: snake-uam.svg)",
    )
    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        default=None,
        help="Deterministic integer seed for procedural generation",
    )
    parser.add_argument(
        "--hourly",
        action="store_true",
        help="Compute deterministic seed based on UTC YYYYMMDDHH",
    )
    parser.add_argument(
        "--duration",
        "-d",
        type=float,
        default=18.0,
        help="Total animation loop duration in seconds (default: 18.0)",
    )
    parser.add_argument(
        "--apples",
        "-a",
        type=int,
        default=7,
        help="Number of procedural apples to spawn (default: 7)",
    )

    args = parser.parse_args()

    # CLI validation
    if args.duration <= 0:
        parser.error("--duration must be positive (> 0)")
    if args.apples < 1:
        parser.error("--apples must be at least 1")

    # Determine seed
    if args.hourly or args.seed is None:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        seed = int(now_utc.strftime("%Y%m%d%H"))
    else:
        seed = args.seed

    print(f"[*] Simulating procedural match (Seed: #{seed}, Apples: {args.apples}, Loop: {args.duration:.1f}s)...")
    sim_data = simulate_match(seed, apple_count=args.apples)

    print(f"[*] Compiling pure W3C SMIL SVG animation (Frames: {len(sim_data['history'])})...")
    svg_content = build_svg(sim_data, total_duration=args.duration)

    print("[*] Performing strict W3C XML & security validation...")
    validate_svg(svg_content)

    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(svg_content)

    print(f"[✓] Successfully generated {args.output} ({len(svg_content):,} bytes) with 0 scripts & 100% transparent background.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
