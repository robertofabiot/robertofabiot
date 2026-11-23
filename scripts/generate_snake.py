#!/usr/bin/env python3
"""
scripts/generate_snake.py
Procedural SVG & SMIL Interactive Snake and Terminal Generator for UAM Virtual Moodle.

Visual Composition:
- ViewBox: 0 0 750 400 with 100% transparent root background.
- Upper Section (Terminal Window): Crisp monospace console styling, window buttons,
  pure SMIL typewriter animation displaying confirmed user profile & UAM Virtual commands.
- Middle Section (HUD Bar): Retro score counter updating +100 per apple, live status telemetry badge,
  and match seed indicator.
- Lower Section (Snake Arena): 30x7 grid, 15 snake segments with directional eyes, procedural apples,
  burst shockwaves, and 2 patrolling neon sentinel drones with spatio-temporal BFS evasion.

Zero JavaScript, Pure W3C SMIL Animation (<animate>, <animateTransform>, <clipPath>).
"""

import argparse
from collections import deque
import datetime
import math
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
ARENA_Y = 202
ARENA_W = 710
ARENA_H = 186
GRID_ORIGIN_X = ARENA_X + (ARENA_W - GRID_W * CELL_SIZE) / 2 # 30.0 px
GRID_ORIGIN_Y = ARENA_Y + (ARENA_H - GRID_H * CELL_SIZE) / 2 # 214.5 px

DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]

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

# --- Spatio-Temporal Pathfinder ---
def find_path_spatiotemporal(start_pos, goal_pos, initial_body, start_step, d_alpha_col, d_beta_row, max_depth=350):
    """
    Spatio-temporal BFS in (x, y, t) state space.
    Avoids moving drones at time t+1 and snake body segments at time t+1.
    """
    # queue elements: (current_pos, step, path, body)
    queue = deque([(start_pos, start_step, [start_pos], list(initial_body))])
    # Drones have periods 8 and 12 -> LCM is 24.
    visited = {(start_pos, start_step % 24)}

    while queue:
        curr, step, path, body = queue.popleft()
        if curr == goal_pos:
            return path

        if step - start_step > max_depth:
            break

        next_step = step + 1
        d_obs = get_drone_obstacles(next_step, d_alpha_col, d_beta_row)
        body_obs = set(body[:-1])

        # Try neighbors; prioritize moves reducing Manhattan distance to goal
        neighbors = []
        for dx, dy in DIRS:
            nx, ny = curr[0] + dx, curr[1] + dy
            if 0 <= nx < GRID_W and 0 <= ny < GRID_H:
                if (nx, ny) not in d_obs and (nx, ny) not in body_obs:
                    dist = abs(nx - goal_pos[0]) + abs(ny - goal_pos[1])
                    neighbors.append((dist, (nx, ny)))

        neighbors.sort(key=lambda item: item[0])

        for _, next_cell in neighbors:
            state_key = (next_cell, next_step % 24)
            if state_key not in visited:
                visited.add(state_key)
                new_body = [next_cell] + body[:-1]
                queue.append((next_cell, next_step, path + [next_cell], new_body))

    # Fallback heuristic: choose move maximizing free space if direct path blocked
    best_next = None
    best_score = -1
    curr = start_pos
    next_step = start_step + 1
    d_obs = get_drone_obstacles(next_step, d_alpha_col, d_beta_row)
    body_obs = set(initial_body[:-1])

    for dx, dy in DIRS:
        nx, ny = curr[0] + dx, curr[1] + dy
        if 0 <= nx < GRID_W and 0 <= ny < GRID_H and (nx, ny) not in d_obs and (nx, ny) not in body_obs:
            # Measure flood fill reach
            q = deque([(nx, ny)])
            v = {curr, (nx, ny)} | body_obs | d_obs
            score = 0
            while q and score < 50:
                cx, cy = q.popleft()
                score += 1
                for ddx, ddy in DIRS:
                    nnx, nny = cx + ddx, cy + ddy
                    if 0 <= nnx < GRID_W and 0 <= nny < GRID_H and (nnx, nny) not in v:
                        v.add((nnx, nny))
                        q.append((nnx, nny))
            if score > best_score:
                best_score = score
                best_next = (nx, ny)

    if best_next is not None:
        return [start_pos, best_next]

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
                if (c, r) not in chosen_coords and (c, r) != (d_alpha_col, 3) and (c, r) != (21, d_beta_row):
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
def simulate_match(seed, apple_count=7):
    """
    Simulates a full deterministic match:
    1. Snake enters from off-screen left.
    2. Navigates past Drone Alpha and Beta eating procedural apples.
    3. Snake length dynamically grows up to 15 segments.
    4. Snake gracefully exits off-screen right.
    """
    rng = random.Random(seed)
    d_alpha_col = rng.choice([9, 10])
    d_beta_row = rng.choice([3, 4])

    apples_spec = generate_apples(rng, d_alpha_col, d_beta_row, count=apple_count)

    # Initial snake off-screen to the left facing east
    start_row = apples_spec[0]["pos"][1]
    snake = [(-1, start_row), (-2, start_row), (-3, start_row), (-4, start_row)]
    history = [list(snake)]
    apple_events = []
    status_timeline = [] # (step, status_type, extra_text)

    current_step = 0
    spawn_step = 0
    growth_pending = 0

    # Total growth needed: 15 - 4 = 11 segments
    # Apples: 7 apples -> [2, 2, 2, 1, 1, 1, 2] = 11
    growth_schedule = [2, 2, 2, 1, 1, 1, 2]

    for apple_idx, apple in enumerate(apples_spec):
        apple_pos = apple["pos"]
        color = apple["color"]
        grow_amount = growth_schedule[apple_idx % len(growth_schedule)]

        # Hunt current apple until head reaches it
        while snake[0] != apple_pos:
            head = snake[0]

            # Determine live status: check proximity to any drone
            d_alpha = drone_alpha_pos(current_step, d_alpha_col)
            d_beta = drone_beta_pos(current_step, d_beta_row)
            dist_alpha = abs(head[0] - d_alpha[0]) + abs(head[1] - d_alpha[1])
            dist_beta = abs(head[0] - d_beta[0]) + abs(head[1] - d_beta[1])

            if dist_alpha <= 2 or dist_beta <= 2:
                status_timeline.append((current_step, "EVADE", "EVADING NEON DRONE ⚠️"))
            else:
                status_timeline.append((current_step, "HUNT", f"HUNTING APPLE #{apple_idx + 1}"))

            if head[0] < 0:
                # Entering from left
                next_cell = (head[0] + 1, head[1])
            else:
                # Spatio-temporal search
                path = find_path_spatiotemporal(head, apple_pos, snake, current_step, d_alpha_col, d_beta_row)
                if path and len(path) >= 2:
                    next_cell = path[1]
                else:
                    # Fallback straight move
                    next_cell = (head[0] + 1, head[1])

            snake.insert(0, next_cell)
            current_step += 1

            if growth_pending > 0:
                growth_pending -= 1
            else:
                snake.pop()

            if next_cell == apple_pos:
                # Apple eaten!
                history.append(list(snake))
                eat_step = current_step
                apple_events.append({
                    "idx": apple_idx,
                    "spawn_step": spawn_step,
                    "eat_step": eat_step,
                    "pos": apple_pos,
                    "color": color,
                })
                spawn_step = current_step + 1
                status_timeline.append((current_step, "EAT", "TARGET SECURED (+100)"))
                growth_pending += grow_amount
                break
            else:
                history.append(list(snake))

    # Exit phase: Snake navigates off-screen to the right (x >= 31)
    exit_row = snake[0][1]
    while any(pt[0] < 31 for pt in snake):
        hx, hy = snake[0]
        status_timeline.append((current_step, "EXIT", "MISSION COMPLETE"))

        # Guide smoothly towards exit lane without reversing into neck/body
        neck = snake[1] if len(snake) > 1 else None
        candidates = []
        if hy < 3:
            candidates.append((hx, hy + 1))
        elif hy > 3:
            candidates.append((hx, hy - 1))
        candidates.append((hx + 1, hy))

        chosen = None
        for nx, ny in candidates:
            if (nx, ny) != neck and (nx, ny) not in snake[1:]:
                chosen = (nx, ny)
                break
        if chosen is None:
            chosen = (hx + 1, hy)
        nx, ny = chosen

        snake.insert(0, (nx, ny))
        if growth_pending > 0:
            growth_pending -= 1
        else:
            snake.pop()
        current_step += 1
        history.append(list(snake))

    # Append terminal status for final step
    status_timeline.append((current_step, "EXIT", "MISSION COMPLETE"))

    return {
        "seed": seed,
        "history": history,
        "apple_events": apple_events,
        "status_timeline": status_timeline,
        "d_alpha_col": d_alpha_col,
        "d_beta_row": d_beta_row,
    }

# --- SMIL SVG Builder ---
def build_svg(sim_data, total_duration=18.0):
    seed = sim_data["seed"]
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

    # Typewriter ClipPaths for Commands
    # Prompt is at x=36. Length of prompt "[ro@archlinux ~]$ " is ~134px. Command starts at x=170.
    # Command 1: "whoami" (w ~ 48px)
    svg.append('    <clipPath id="clip-cmd1">')
    svg.append(f'      <rect x="170" y="36" width="0" height="15">')
    svg.append(f'        <animate attributeName="width" dur="{total_time:.2f}s" repeatCount="indefinite" ')
    svg.append(f'                 keyTimes="0.00000;0.01667;0.06667;0.97222;1.00000" values="0;0;50;50;0"/>')
    svg.append('      </rect>')
    svg.append('    </clipPath>')

    # Command 2: "uam-virtual --status" (w ~ 158px)
    svg.append('    <clipPath id="clip-cmd2">')
    svg.append(f'      <rect x="170" y="75" width="0" height="15">')
    svg.append(f'        <animate attributeName="width" dur="{total_time:.2f}s" repeatCount="indefinite" ')
    svg.append(f'                 keyTimes="0.00000;0.19444;0.28889;0.97222;1.00000" values="0;0;160;160;0"/>')
    svg.append('      </rect>')
    svg.append('    </clipPath>')

    # Command 3: "fastfetch --stack" (w ~ 138px)
    svg.append('    <clipPath id="clip-cmd3">')
    svg.append(f'      <rect x="170" y="114" width="0" height="15">')
    svg.append(f'        <animate attributeName="width" dur="{total_time:.2f}s" repeatCount="indefinite" ')
    svg.append(f'                 keyTimes="0.00000;0.43333;0.52222;0.97222;1.00000" values="0;0;140;140;0"/>')
    svg.append('      </rect>')
    svg.append('    </clipPath>')
    svg.append('  </defs>')

    # ==========================================
    # SECTION 1: UPPER TERMINAL WINDOW (y=10..158)
    # 100% Transparent Canvas: Floating dark translucent console window
    # ==========================================
    svg.append('  <!-- ================= TERMINAL SECTION ================= -->')
    svg.append('  <g id="terminal-window">')
    # Terminal Window Container
    svg.append('    <rect x="20" y="10" width="710" height="148" rx="8" ry="8" '
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
    svg.append('    <text x="375" y="25" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="11" fill="#8b949e" text-anchor="middle">robertofabiot@uam-virtual:~</text>')

    # --- Line 1: whoami ---
    # Prompt 1
    svg.append('    <text x="36" y="47" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="11.5" xml:space="preserve">')
    svg.append('      <tspan fill="#58a6ff">[ro@archlinux</tspan><tspan fill="#8b949e"> </tspan>'
               '<tspan fill="#3fb950">~</tspan><tspan fill="#8b949e">]$ </tspan>')
    svg.append('    </text>')
    # Typed Command 1
    svg.append('    <g clip-path="url(#clip-cmd1)">')
    svg.append('      <text x="170" y="47" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="11.5" font-weight="bold" fill="#f0f6fc">whoami</text>')
    svg.append('    </g>')
    # Output 1 (Discrete opacity transition at t=1.3s / 18.0s = 0.07222)
    svg.append('    <g opacity="0">')
    svg.append(f'      <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" calcMode="discrete" '
               f'keyTimes="0.00000;0.07222;0.97222;1.00000" values="0;1;0;0"/>')
    svg.append('      <text x="36" y="59" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="11.5" fill="#f0f6fc">Roberto Fabio Tercero <tspan fill="#58a6ff">· @robertofabiot</tspan></text>')
    svg.append('      <text x="36" y="71" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="11.5" fill="#8b949e"><tspan fill="#3fb950">↳</tspan> Ingeniería en Sistemas @ '
               '<tspan fill="#e6edf3">Universidad Americana (UAM)</tspan></text>')
    svg.append('    </g>')

    # --- Line 2: uam-virtual --status ---
    # Prompt 2 appears at t=3.2s / 18.0s = 0.17778
    svg.append('    <g opacity="0">')
    svg.append(f'      <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" calcMode="discrete" '
               f'keyTimes="0.00000;0.17778;0.97222;1.00000" values="0;1;0;0"/>')
    svg.append('      <text x="36" y="86" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="11.5" xml:space="preserve">')
    svg.append('        <tspan fill="#58a6ff">[ro@archlinux</tspan><tspan fill="#8b949e"> </tspan>'
               '<tspan fill="#3fb950">~</tspan><tspan fill="#8b949e">]$ </tspan>')
    svg.append('      </text>')
    svg.append('    </g>')
    # Typed Command 2
    svg.append('    <g clip-path="url(#clip-cmd2)">')
    svg.append('      <text x="170" y="86" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="11.5" font-weight="bold" fill="#f0f6fc">uam-virtual --status</text>')
    svg.append('    </g>')
    # Output 2 appears at t=5.4s / 18.0s = 0.30000
    svg.append('    <g opacity="0">')
    svg.append(f'      <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" calcMode="discrete" '
               f'keyTimes="0.00000;0.30000;0.97222;1.00000" values="0;1;0;0"/>')
    svg.append('      <text x="36" y="98" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="11.5" fill="#f0f6fc"><tspan fill="#3fb950">● Conectado:</tspan> '
               '<tspan fill="#79c0ff">uamvirtual.uam.edu.ni/grado</tspan></text>')
    svg.append('      <text x="36" y="110" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="11.5" fill="#8b949e"><tspan fill="#3fb950">↳</tspan> Cursos activos: '
               '<tspan fill="#ffa657">BD2</tspan> · <tspan fill="#ffa657">Prog. Escritorio</tspan> · '
               '<tspan fill="#ffa657">Redes II</tspan> · <tspan fill="#ffa657">Ed. Ambiental</tspan></text>')
    svg.append('    </g>')

    # --- Line 3: fastfetch --stack ---
    # Prompt 3 appears at t=7.5s / 18.0s = 0.41667
    svg.append('    <g opacity="0">')
    svg.append(f'      <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" calcMode="discrete" '
               f'keyTimes="0.00000;0.41667;0.97222;1.00000" values="0;1;0;0"/>')
    svg.append('      <text x="36" y="125" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="11.5" xml:space="preserve">')
    svg.append('        <tspan fill="#58a6ff">[ro@archlinux</tspan><tspan fill="#8b949e"> </tspan>'
               '<tspan fill="#3fb950">~</tspan><tspan fill="#8b949e">]$ </tspan>')
    svg.append('      </text>')
    svg.append('    </g>')
    # Typed Command 3
    svg.append('    <g clip-path="url(#clip-cmd3)">')
    svg.append('      <text x="170" y="125" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="11.5" font-weight="bold" fill="#f0f6fc">fastfetch --stack</text>')
    svg.append('    </g>')
    # Output 3 appears at t=9.6s / 18.0s = 0.53333
    svg.append('    <g opacity="0">')
    svg.append(f'      <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" calcMode="discrete" '
               f'keyTimes="0.00000;0.53333;0.97222;1.00000" values="0;1;0;0"/>')
    svg.append('      <text x="36" y="137" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="11.5" fill="#f0f6fc"><tspan fill="#d2a8ff">OS:</tspan> Arch Linux x86_64 · '
               '<tspan fill="#d2a8ff">WM:</tspan> Niri (Wayland)</text>')
    svg.append('      <text x="36" y="149" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="11.5" fill="#8b949e"><tspan fill="#58a6ff">Stack:</tspan> '
               '<tspan fill="#ff7b72">Rust</tspan> · <tspan fill="#3fb950">Python</tspan> · '
               '<tspan fill="#ffa657">Java</tspan> · <tspan fill="#58a6ff">Linux</tspan></text>')
    svg.append('    </g>')

    # Synchronized Blinking Monospace Cursor
    # Travels across commands 1, 2, and 3
    cursor_kt = [
        0.00000, 0.01667, 0.06667, 0.17777,
        0.17778, 0.19444, 0.28889, 0.41666,
        0.41667, 0.43333, 0.52222, 0.97222,
        1.00000
    ]
    cursor_x = [
        170, 170, 218, 218,
        170, 170, 328, 328,
        170, 170, 308, 308,
        170
    ]
    cursor_y = [
        36, 36, 36, 36,
        75, 75, 75, 75,
        114, 114, 114, 114,
        36
    ]
    c_kt_str = ";".join(f"{t:.5f}" for t in cursor_kt)
    c_x_str = ";".join(str(x) for x in cursor_x)
    c_y_str = ";".join(str(y) for y in cursor_y)

    svg.append('    <!-- Terminal Blinking Cursor -->')
    svg.append('    <rect x="170" y="36" width="7.5" height="13.5" rx="1" fill="#58a6ff" opacity="0.9">')
    svg.append(f'      <animate attributeName="x" dur="{total_time:.2f}s" repeatCount="indefinite" '
               f'calcMode="linear" keyTimes="{c_kt_str}" values="{c_x_str}"/>')
    svg.append(f'      <animate attributeName="y" dur="{total_time:.2f}s" repeatCount="indefinite" '
               f'calcMode="discrete" keyTimes="{c_kt_str}" values="{c_y_str}"/>')
    svg.append('      <animate attributeName="opacity" dur="0.75s" repeatCount="indefinite" '
               'values="1;1;0;0;1" keyTimes="0;0.48;0.52;0.96;1"/>')
    svg.append('    </rect>')
    svg.append('  </g>')

    # ==========================================
    # SECTION 2: MIDDLE RETRO HUD BAR (y=164..196)
    # 100% Transparent Canvas: Floating retro displays
    # ==========================================
    svg.append('  <!-- ================= RETRO HUD BAR ================= -->')
    svg.append('  <g id="hud-bar">')
    # Score label
    svg.append('    <text x="24" y="184" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="12" font-weight="bold" fill="#8b949e">SCORE:</text>')

    # Score Value Multi-state (+100 per apple)
    # Render discrete score nodes for 0000, 0100, 0200, ...
    eat_steps = [app["eat_step"] for app in apple_events]
    total_apples = len(apple_events)

    for score_idx in range(total_apples + 1):
        score_val = f"{score_idx * 100:04d}"
        if score_idx == 0:
            t_start = 0.0
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

        s_kt_str = ";".join(f"{t:.5f}" for t in s_kt)
        s_op_str = ";".join(s_op)

        svg.append(f'    <text x="82" y="184" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
                   f'font-size="13" font-weight="bold" fill="#39d353" opacity="0">')
        svg.append(f'      <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'calcMode="discrete" keyTimes="{s_kt_str}" values="{s_op_str}"/>')
        svg.append(f'      {score_val}')
        svg.append('    </text>')

    # Dynamic Status Telemetry Badge
    svg.append('    <!-- Status Telemetry Badge Container -->')
    svg.append('    <rect x="235" y="169" width="280" height="22" rx="4" ry="4" '
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

    for idx, (int_start, int_end, st_type, st_label) in enumerate(intervals):
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

        st_kt_str = ";".join(f"{t:.5f}" for t in st_kt)
        st_op_str = ";".join(st_op)

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

        svg.append(f'    <g opacity="0">')
        svg.append(f'      <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'calcMode="discrete" keyTimes="{st_kt_str}" values="{st_op_str}"/>')
        svg.append(f'      <text x="375" y="184" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
                   f'font-size="10.5" font-weight="bold" fill="{txt_color}" text-anchor="middle">'
                   f'{badge_icon}{st_label}</text>')
        svg.append('    </g>')

    # Match Seed Indicator
    svg.append(f'    <text x="725" y="184" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               f'font-size="11" text-anchor="end">')
    svg.append(f'      <tspan fill="#8b949e">SEED: </tspan><tspan fill="#58a6ff" font-weight="bold">#{seed}</tspan>')
    svg.append('    </text>')
    svg.append('  </g>')

    # ==========================================
    # SECTION 3: LOWER SNAKE ARENA (y=202..388)
    # 100% Transparent Canvas: Grid dots and frame border with fill="none"
    # ==========================================
    svg.append('  <!-- ================= SNAKE ARENA ================= -->')
    svg.append(f'  <g id="snake-arena">')
    # Arena Border (fill="none" ensures full background transparency)
    svg.append(f'    <rect x="{ARENA_X}" y="{ARENA_Y}" width="{ARENA_W}" height="{ARENA_H}" rx="8" ry="8" '
               f'fill="none" stroke="#30363d" stroke-width="1"/>')

    # Subtle Grid Crosses / Dots
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

        app_kt_str = ";".join(f"{t:.5f}" for t in app_kt)
        app_op_str = ";".join(app_op)

        svg.append(f'      <!-- Apple #{idx} ({color}) at ({ax}, {ay}) -->')
        svg.append(f'      <g id="apple-{idx}" opacity="0">')
        svg.append(f'        <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'calcMode="discrete" keyTimes="{app_kt_str}" values="{app_op_str}"/>')
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

        b_kt = [0.0, max(0.0, b_start - eps), b_start, b_end, 1.0]
        b_kt_str = ";".join(f"{t:.5f}" for t in b_kt)

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
        svg.append(f'      <text x="{cx:.1f}" y="{cy:.1f}" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
                   f'font-size="10.5" font-weight="bold" fill="{color}" text-anchor="middle" opacity="0">')
        svg.append(f'        <animate attributeName="y" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'keyTimes="{b_kt_str}" values="{cy:.1f};{cy:.1f};{cy:.1f};{cy-14.0:.1f};{cy-14.0:.1f}"/>')
        svg.append(f'        <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'keyTimes="{b_kt_str}" values="0;0;1.0;0;0"/>')
        svg.append(f'        +100')
        svg.append('      </text>')

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
    # Drone Alpha: Vertical sentinel
    d_alpha_coords = []
    for k in range(total_steps + 1):
        col, row = drone_alpha_pos(k, d_alpha_col)
        px = GRID_ORIGIN_X + col * CELL_SIZE + CELL_SIZE / 2
        py = GRID_ORIGIN_Y + row * CELL_SIZE + CELL_SIZE / 2
        d_alpha_coords.append(f"{px:.1f},{py:.1f}")
    d_alpha_trans_str = ";".join(d_alpha_coords)

    svg.append('      <!-- Drone Alpha (Vertical Sentinel) -->')
    svg.append(f'      <g id="drone-alpha" filter="url(#glow-drone-alpha)">')
    svg.append(f'        <animateTransform attributeName="transform" type="translate" dur="{total_time:.2f}s" '
               f'repeatCount="indefinite" calcMode="linear" keyTimes="{key_times_str}" values="{d_alpha_trans_str}"/>')
    # Radar Pulsing Ring
    svg.append('        <circle cx="0" cy="0" r="14" fill="none" stroke="#ff5f56" stroke-width="1.2" '
               'stroke-dasharray="3,3" opacity="0.6">')
    svg.append('          <animate attributeName="r" values="9;19;9" dur="1.8s" repeatCount="indefinite"/>')
    svg.append('          <animate attributeName="opacity" values="0.8;0.1;0.8" dur="1.8s" repeatCount="indefinite"/>')
    svg.append('        </circle>')
    # Drone Hull & Wings
    svg.append('        <polygon points="0,-8 8,0 0,8 -8,0" fill="#161b22" stroke="#ff5f56" stroke-width="1.6"/>')
    svg.append('        <circle cx="0" cy="0" r="2.8" fill="#ff7b72"/>')
    svg.append('        <line x1="-12" y1="0" x2="12" y2="0" stroke="#ff5f56" stroke-width="1.2" stroke-linecap="round"/>')
    svg.append('        <circle cx="-12" cy="0" r="2.2" fill="#ff5f56"/>')
    svg.append('        <circle cx="12" cy="0" r="2.2" fill="#ff5f56"/>')
    svg.append('        <text x="0" y="-11" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="7.5" font-weight="bold" fill="#ff7b72" text-anchor="middle">DRONE-α</text>')
    svg.append('      </g>')

    # Drone Beta: Horizontal sentinel
    d_beta_coords = []
    for k in range(total_steps + 1):
        col, row = drone_beta_pos(k, d_beta_row)
        px = GRID_ORIGIN_X + col * CELL_SIZE + CELL_SIZE / 2
        py = GRID_ORIGIN_Y + row * CELL_SIZE + CELL_SIZE / 2
        d_beta_coords.append(f"{px:.1f},{py:.1f}")
    d_beta_trans_str = ";".join(d_beta_coords)

    svg.append('      <!-- Drone Beta (Horizontal Sentinel) -->')
    svg.append(f'      <g id="drone-beta" filter="url(#glow-drone-beta)">')
    svg.append(f'        <animateTransform attributeName="transform" type="translate" dur="{total_time:.2f}s" '
               f'repeatCount="indefinite" calcMode="linear" keyTimes="{key_times_str}" values="{d_beta_trans_str}"/>')
    # Radar Pulsing Ring
    svg.append('        <circle cx="0" cy="0" r="14" fill="none" stroke="#58a6ff" stroke-width="1.2" '
               'stroke-dasharray="3,3" opacity="0.6">')
    svg.append('          <animate attributeName="r" values="9;19;9" dur="1.8s" repeatCount="indefinite"/>')
    svg.append('          <animate attributeName="opacity" values="0.8;0.1;0.8" dur="1.8s" repeatCount="indefinite"/>')
    svg.append('        </circle>')
    # Drone Hull & Wings
    svg.append('        <polygon points="-8,-4 0,-8 8,-4 8,4 0,8 -8,4" fill="#161b22" stroke="#58a6ff" stroke-width="1.6"/>')
    svg.append('        <circle cx="0" cy="0" r="2.8" fill="#79c0ff"/>')
    svg.append('        <line x1="0" y1="-12" x2="0" y2="12" stroke="#58a6ff" stroke-width="1.2" stroke-linecap="round"/>')
    svg.append('        <circle cx="0" cy="-12" r="2.2" fill="#58a6ff"/>')
    svg.append('        <circle cx="0" cy="12" r="2.2" fill="#58a6ff"/>')
    svg.append('        <text x="0" y="-11" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" '
               'font-size="7.5" font-weight="bold" fill="#58a6ff" text-anchor="middle">DRONE-β</text>')
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
            if s < len(snake_k):
                cell_x, cell_y = snake_k[s]
                px_x = GRID_ORIGIN_X + cell_x * CELL_SIZE + OFFSET
                px_y = GRID_ORIGIN_Y + cell_y * CELL_SIZE + OFFSET
                x_vals.append(f"{px_x:.1f}")
                y_vals.append(f"{px_y:.1f}")
                opac_vals.append("1")
            else:
                cell_x, cell_y = snake_k[-1]
                px_x = GRID_ORIGIN_X + cell_x * CELL_SIZE + OFFSET
                px_y = GRID_ORIGIN_Y + cell_y * CELL_SIZE + OFFSET
                x_vals.append(f"{px_x:.1f}")
                y_vals.append(f"{px_y:.1f}")
                opac_vals.append("0")

        x_str = ";".join(x_vals)
        y_str = ";".join(y_vals)
        opac_str = ";".join(opac_vals)
        rx = "6" if s == 0 else "4.5"

        svg.append(f'      <!-- Snake Segment #{s} ({seg_color}) -->')
        svg.append(f'      <rect width="{SEG_SIZE}" height="{SEG_SIZE}" rx="{rx}" ry="{rx}" '
                   f'fill="{seg_color}" filter="url(#glow-snake)">')
        svg.append(f'        <animate attributeName="x" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'calcMode="linear" keyTimes="{key_times_str}" values="{x_str}"/>')
        svg.append(f'        <animate attributeName="y" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'calcMode="linear" keyTimes="{key_times_str}" values="{y_str}"/>')
        svg.append(f'        <animate attributeName="opacity" dur="{total_time:.2f}s" repeatCount="indefinite" '
                   f'calcMode="discrete" keyTimes="{key_times_str}" values="{opac_str}"/>')
        svg.append('      </rect>')

    # --- 4. SNAKE DIRECTIONAL EYES & PUPILS ---
    eye1_x, eye1_y = [], []
    eye2_x, eye2_y = [], []
    pup1_x, pup1_y = [], []
    pup2_x, pup2_y = [], []

    for k in range(total_steps + 1):
        snake_k = history[k]
        hx, hy = snake_k[0]
        if k < total_steps:
            nhx, nhy = history[k + 1][0]
            dx, dy = nhx - hx, nhy - hy
        else:
            dx, dy = 1, 0 # exiting right

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

    # Eye 1 & Pupil 1
    svg.append('      <!-- Snake Eye 1 & Pupil 1 -->')
    svg.append('      <circle r="2.4" fill="#ffffff">')
    svg.append(f'        <animate attributeName="cx" dur="{total_time:.2f}s" repeatCount="indefinite" '
               f'calcMode="linear" keyTimes="{key_times_str}" values="{";".join(eye1_x)}"/>')
    svg.append(f'        <animate attributeName="cy" dur="{total_time:.2f}s" repeatCount="indefinite" '
               f'calcMode="linear" keyTimes="{key_times_str}" values="{";".join(eye1_y)}"/>')
    svg.append('      </circle>')
    svg.append('      <circle r="1.3" fill="#0d1117">')
    svg.append(f'        <animate attributeName="cx" dur="{total_time:.2f}s" repeatCount="indefinite" '
               f'calcMode="linear" keyTimes="{key_times_str}" values="{";".join(pup1_x)}"/>')
    svg.append(f'        <animate attributeName="cy" dur="{total_time:.2f}s" repeatCount="indefinite" '
               f'calcMode="linear" keyTimes="{key_times_str}" values="{";".join(pup1_y)}"/>')
    svg.append('      </circle>')

    # Eye 2 & Pupil 2
    svg.append('      <!-- Snake Eye 2 & Pupil 2 -->')
    svg.append('      <circle r="2.4" fill="#ffffff">')
    svg.append(f'        <animate attributeName="cx" dur="{total_time:.2f}s" repeatCount="indefinite" '
               f'calcMode="linear" keyTimes="{key_times_str}" values="{";".join(eye2_x)}"/>')
    svg.append(f'        <animate attributeName="cy" dur="{total_time:.2f}s" repeatCount="indefinite" '
               f'calcMode="linear" keyTimes="{key_times_str}" values="{";".join(eye2_y)}"/>')
    svg.append('      </circle>')
    svg.append('      <circle r="1.3" fill="#0d1117">')
    svg.append(f'        <animate attributeName="cx" dur="{total_time:.2f}s" repeatCount="indefinite" '
               f'calcMode="linear" keyTimes="{key_times_str}" values="{";".join(pup2_x)}"/>')
    svg.append(f'        <animate attributeName="cy" dur="{total_time:.2f}s" repeatCount="indefinite" '
               f'calcMode="linear" keyTimes="{key_times_str}" values="{";".join(pup2_y)}"/>')
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
        if (w in ["100%", "750", "600"] or h in ["100%", "400", "200"]) and fill not in ["none", ""]:
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
    if args.hourly:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        seed = int(now_utc.strftime("%Y%m%d%H"))
    elif args.seed is not None:
        seed = args.seed
    else:
        # Fallback to current UTC hour seed
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        seed = int(now_utc.strftime("%Y%m%d%H"))

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
