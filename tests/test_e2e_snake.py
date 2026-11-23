#!/usr/bin/env python3
"""
test_e2e_snake.py — Automated Opaque-Box E2E Test Verification Suite
Comprehensive 4-Tier verification covering Requirements R1, R2, R3, R4:
- Tier 1: Format, XML Well-Formedness, Strict Security & 100% Transparency
- Tier 2: Visual Elements, Monospace Typewriter, Confirmed Text, HUD & Drones
- Tier 3: CLI Generator Arguments, Determinism, Entropy & Mechanics
- Tier 4: GitHub Actions Workflow Automation & Deployment Safety
"""

import os
import sys
import re
import shutil
import hashlib
import tempfile
import subprocess
import unittest
import xml.etree.ElementTree as ET

try:
    import yaml
except ImportError:
    yaml = None

try:
    from PIL import Image
except ImportError:
    Image = None

# Base directories
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SVG_PATH = os.path.join(REPO_ROOT, "snake-uam.svg")
GENERATOR_PATH = os.path.join(REPO_ROOT, "scripts", "generate_snake.py")
WORKFLOW_PATH = os.path.join(REPO_ROOT, ".github", "workflows", "update-snake.yml")

# Scratch directory for disk hygiene compliance
SCRATCH_DIR = os.environ.get(
    "TEAMWORK_SCRATCH_DIR",
    "/home/ro/.gemini/antigravity-cli/scratch/teamwork_tmp/6759a864-4376-4185-873b-948094813462"
)


class BaseE2ETestCase(unittest.TestCase):
    """Base test case providing shared helpers and isolated test directories."""

    temp_dir = None

    @classmethod
    def setUpClass(cls):
        os.makedirs(SCRATCH_DIR, exist_ok=True)
        cls.temp_dir = tempfile.mkdtemp(prefix="snake_e2e_", dir=SCRATCH_DIR)

    @classmethod
    def tearDownClass(cls):
        if cls.temp_dir and os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def parse_svg(self, path=SVG_PATH):
        self.assertTrue(os.path.isfile(path), f"SVG file not found at {path}")
        tree = ET.parse(path)
        return tree, tree.getroot()

    def read_svg_text(self, path=SVG_PATH):
        self.assertTrue(os.path.isfile(path), f"SVG file not found at {path}")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def strip_ns(tag):
        return tag.split("}")[-1] if "}" in tag else tag


class TestTier1FormatAndSecurity(BaseE2ETestCase):
    """Tier 1: Syntactic validation, strict security checks and background transparency."""

    def test_01_svg_file_exists(self):
        """Verify snake-uam.svg exists in repository root."""
        self.assertTrue(
            os.path.isfile(SVG_PATH),
            f"Expected snake-uam.svg to exist at {SVG_PATH}"
        )
        self.assertGreater(
            os.path.getsize(SVG_PATH),
            100,
            "snake-uam.svg file is unexpectedly small or empty"
        )

    def test_02_xml_well_formedness_etree(self):
        """Verify snake-uam.svg is well-formed XML and has valid SVG root & viewBox."""
        tree, root = self.parse_svg(SVG_PATH)
        tag_name = self.strip_ns(root.tag).lower()
        self.assertEqual(tag_name, "svg", f"Expected root tag to be <svg>, got <{root.tag}>")
        viewbox = root.attrib.get("viewBox", "")
        self.assertEqual(
            viewbox,
            "0 0 750 400",
            f"Expected viewBox='0 0 750 400' according to PROJECT.md, got '{viewbox}'"
        )

    def test_03_xml_well_formedness_xmllint(self):
        """Verify XML well-formedness using xmllint binary."""
        xmllint_bin = shutil.which("xmllint")
        if not xmllint_bin:
            self.skipTest("xmllint binary not available on system")

        proc = subprocess.run(
            [xmllint_bin, "--noout", SVG_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"xmllint validation failed on {SVG_PATH}:\n{proc.stderr}"
        )

    def test_04_strict_security_no_script_tags(self):
        """Assert zero <script> elements anywhere in the SVG document."""
        tree, root = self.parse_svg(SVG_PATH)
        for elem in root.iter():
            tag = self.strip_ns(elem.tag).lower()
            self.assertNotEqual(
                tag,
                "script",
                f"STRICT SECURITY VIOLATION: Found <script> tag in SVG: {elem.attrib}"
            )

        # Raw string scanning
        content = self.read_svg_text(SVG_PATH)
        self.assertFalse(
            re.search(r"<\s*script[\s>]", content, re.IGNORECASE),
            "STRICT SECURITY VIOLATION: Raw text matches '<script' tag pattern"
        )

    def test_05_strict_security_no_javascript_urls(self):
        """Assert zero 'javascript:' protocol URLs in any attributes or text."""
        tree, root = self.parse_svg(SVG_PATH)
        for elem in root.iter():
            for attr_name, attr_val in elem.attrib.items():
                clean_val = attr_val.strip().lower()
                self.assertNotIn(
                    "javascript:",
                    clean_val,
                    f"STRICT SECURITY VIOLATION: 'javascript:' found in attribute {attr_name}='{attr_val}'"
                )

        content = self.read_svg_text(SVG_PATH)
        self.assertFalse(
            re.search(r"javascript\s*:", content, re.IGNORECASE),
            "STRICT SECURITY VIOLATION: Raw text contains 'javascript:' protocol"
        )

    def test_06_strict_security_no_inline_event_handlers(self):
        """Assert zero inline JavaScript event handlers (e.g. onload, onclick, onmouseover)."""
        tree, root = self.parse_svg(SVG_PATH)
        for elem in root.iter():
            for attr_name, attr_val in elem.attrib.items():
                local_attr = self.strip_ns(attr_name).lower()
                self.assertFalse(
                    local_attr.startswith("on"),
                    f"STRICT SECURITY VIOLATION: Inline event handler '{attr_name}' found on <{elem.tag}>"
                )

        content = self.read_svg_text(SVG_PATH)
        # Match word boundaries for on[a-z]+= like onclick=, onload=
        matches = re.findall(r"\bon[a-z]{3,}\s*=", content, re.IGNORECASE)
        self.assertEqual(
            matches,
            [],
            f"STRICT SECURITY VIOLATION: Raw text matches inline event handlers: {matches}"
        )

    def test_07_transparency_no_solid_background_rect(self):
        """Assert root SVG does not contain a solid background <rect> covering the viewBox."""
        tree, root = self.parse_svg(SVG_PATH)
        for elem in root.iter():
            if self.strip_ns(elem.tag).lower() == "rect":
                w = elem.attrib.get("width", "")
                h = elem.attrib.get("height", "")
                fill = elem.attrib.get("fill", "").strip().lower()
                # Check if it covers 100% or 750x400
                covers_width = w in ("100%", "750", "750.0")
                covers_height = h in ("100%", "400", "400.0")
                if covers_width and covers_height:
                    self.assertIn(
                        fill,
                        ("", "none", "transparent"),
                        f"TRANSPARENCY VIOLATION: Canvas-covering <rect> found with fill='{fill}'"
                    )

    def test_08_transparency_corner_pixels_alpha_zero(self):
        """Render SVG to PNG via rsvg-convert and assert corner pixels have alpha channel == 0."""
        rsvg_bin = shutil.which("rsvg-convert")
        if not rsvg_bin:
            self.skipTest("rsvg-convert binary not available on system")
        if Image is None:
            self.skipTest("PIL (Pillow) library not available")

        png_output = os.path.join(self.temp_dir, "raster_corner_check.png")
        proc = subprocess.run(
            [rsvg_bin, SVG_PATH, "-o", png_output],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"rsvg-convert failed to rasterize SVG:\n{proc.stderr}"
        )
        self.assertTrue(os.path.isfile(png_output))

        with Image.open(png_output) as img:
            rgba = img.convert("RGBA")
            width, height = rgba.size
            corners = {
                "top-left (5, 5)": (5, 5),
                "top-right (w-5, 5)": (width - 5, 5),
                "bottom-left (5, h-5)": (5, height - 5),
                "bottom-right (w-5, h-5)": (width - 5, height - 5),
            }
            for corner_name, (cx, cy) in corners.items():
                pixel = rgba.getpixel((cx, cy))
                alpha = pixel[3]
                self.assertEqual(
                    alpha,
                    0,
                    f"TRANSPARENCY VIOLATION: Corner {corner_name} at ({cx}, {cy}) has alpha={alpha} (pixel={pixel}), expected 0"
                )

    def test_09_adversarial_encoding_and_entity_integrity(self):
        """Assert SVG is clean UTF-8 without mojibake (e.g. Ã, ) and XML entities are valid."""
        with open(SVG_PATH, "rb") as f:
            raw_bytes = f.read()
        try:
            decoded = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            self.fail(f"SVG is not valid UTF-8: {e}")

        # Check for common mojibake sequences
        mojibake_tokens = ["Ã¡", "Ã©", "Ã­", "Ã³", "Ãº", "Ã±", "\ufffd"]
        for token in mojibake_tokens:
            self.assertNotIn(
                token,
                decoded,
                f"Mojibake token '{token}' detected in SVG, indicating encoding corruption"
            )

    def test_10_smil_keytimes_values_cardinality(self):
        """Verify that for all SMIL animation elements with keyTimes, the values count matches keyTimes count."""
        tree, root = self.parse_svg(SVG_PATH)
        for elem in root.iter():
            tag = self.strip_ns(elem.tag).lower()
            if tag in ("animate", "animatetransform", "animatemotion"):
                key_times = elem.attrib.get("keyTimes")
                values = elem.attrib.get("values")
                if key_times and values:
                    kt_list = [k.strip() for k in key_times.strip().split(";") if k.strip()]
                    val_list = [v.strip() for v in values.strip().split(";") if v.strip()]
                    self.assertEqual(
                        len(kt_list),
                        len(val_list),
                        f"SMIL SPEC VIOLATION in <{tag}> id='{elem.attrib.get('id', '')}': keyTimes count ({len(kt_list)}) != values count ({len(val_list)})"
                    )
                    # Verify keyTimes starts with 0 and ends with 1
                    try:
                        self.assertAlmostEqual(float(kt_list[0]), 0.0, places=4)
                        self.assertAlmostEqual(float(kt_list[-1]), 1.0, places=4)
                    except ValueError:
                        self.fail(f"Invalid non-numeric keyTime in {key_times}")



class TestTier2VisualElementsAndComposition(BaseE2ETestCase):
    """Tier 2: Visual Elements, Monospace Styling, Typewriter Animation & Confirmed Content."""

    def test_01_upper_terminal_window_buttons(self):
        """Verify upper terminal window buttons (circles/dots with red, yellow, green hues)."""
        tree, root = self.parse_svg(SVG_PATH)
        # Red (#ff5f56), Yellow (#ffbd2e/#febc2e), Green (#27c93f/#28c840)
        red_pattern = re.compile(r"#(ff5f56|ea4335|e06c75)", re.IGNORECASE)
        yellow_pattern = re.compile(r"#(ffbd2e|febc2e|fbbc05|e5c07b)", re.IGNORECASE)
        green_pattern = re.compile(r"#(27c93f|28c840|34a853|98c379|39d353)", re.IGNORECASE)

        found_red = False
        found_yellow = False
        found_green = False

        for elem in root.iter():
            tag = self.strip_ns(elem.tag).lower()
            if tag not in ("circle", "ellipse", "rect"):
                continue
            fill = elem.attrib.get("fill", "")
            cy_str = elem.attrib.get("cy", elem.attrib.get("y", ""))
            try:
                cy = float(cy_str.replace("px", "").strip())
            except (ValueError, TypeError):
                continue
            # Window buttons must be in upper header area (y <= 60)
            if cy <= 60:
                if red_pattern.search(fill):
                    found_red = True
                elif yellow_pattern.search(fill):
                    found_yellow = True
                elif green_pattern.search(fill):
                    found_green = True

        self.assertTrue(found_red, "Upper terminal red window button not found (expected y<=60, red fill)")
        self.assertTrue(found_yellow, "Upper terminal yellow window button not found (expected y<=60, yellow fill)")
        self.assertTrue(found_green, "Upper terminal green window button not found (expected y<=60, green fill)")

    def test_02_upper_terminal_monospace_styling(self):
        """Verify monospace styling is used for terminal text elements."""
        content = self.read_svg_text(SVG_PATH)
        monospace_pattern = re.compile(r"monospace|SFMono|Consolas|Courier|Liberation Mono", re.IGNORECASE)
        self.assertTrue(
            monospace_pattern.search(content),
            "Monospace font-family styling not detected in SVG terminal styles"
        )

    def test_03_smil_typewriter_clip_path_and_cursor(self):
        """Verify pure SMIL typewriter animation mechanism (clipPath or animated reveal) and blinking cursor."""
        tree, root = self.parse_svg(SVG_PATH)

        # 1. Search for typewriter mechanism (clipPath with animated width or rect reveal)
        clip_paths = root.findall(".//{http://www.w3.org/2000/svg}clipPath") + root.findall(".//clipPath")
        has_typewriter_clip = False
        for cp in clip_paths:
            for child in cp.iter():
                child_tag = self.strip_ns(child.tag).lower()
                if child_tag in ("animate", "animatetransform"):
                    attr = child.attrib.get("attributeName", "").lower()
                    if attr in ("width", "x", "transform", "clip-path"):
                        has_typewriter_clip = True
                        break
            if has_typewriter_clip:
                break

        # Fallback check: animated text reveal or width animation anywhere
        content = self.read_svg_text(SVG_PATH)
        has_animated_reveal = bool(re.search(r'<animate[^>]+attributeName="(width|x|opacity)"', content, re.IGNORECASE))
        self.assertTrue(
            has_typewriter_clip or has_animated_reveal,
            "SMIL typewriter mechanism (animated clipPath width or text reveal) not found"
        )

        # 2. Search for blinking cursor element (animated opacity with discrete or periodic pulses)
        has_blinking_cursor = bool(
            re.search(r'<animate[^>]+attributeName="opacity"[^>]+values="[^"]*(1;0|0;1|1;0;1|0;1;0)', content, re.IGNORECASE)
            or re.search(r'cursor', content, re.IGNORECASE)
        )
        self.assertTrue(
            has_blinking_cursor,
            "Blinking SMIL cursor animation not detected in SVG"
        )

    def test_04_terminal_confirmed_text_content(self):
        """
        Verify exact monospace terminal text matches user-approved content in PROJECT.md:
        - whoami
        - Roberto Fabio Tercero · @robertofabiot · UAM
        - uam-virtual --status (uamvirtual.uam.edu.ni/grado)
        - fastfetch --stack (Arch Linux, Niri, Rust, Python, Java, Linux)
        """
        content = self.read_svg_text(SVG_PATH)

        required_strings = [
            ("Command 1", "whoami"),
            ("Profile Name", "Roberto Fabio"),
            ("GitHub Handle", "@robertofabiot"),
            ("UAM Affiliation", "Universidad Americana"),
            ("Command 2", "uam-virtual --status"),
            ("UAM Virtual URL", "uamvirtual.uam.edu.ni/grado"),
            ("Active Courses", "Cursos activos"),
            ("Command 3", "fastfetch --stack"),
            ("OS", "Arch Linux"),
            ("Window Manager", "Niri"),
            ("Stack: Rust", "Rust"),
            ("Stack: Python", "Python"),
            ("Stack: Java", "Java"),
            ("Stack: Linux", "Linux"),
        ]

        for label, req_str in required_strings:
            self.assertIn(
                req_str,
                content,
                f"Missing confirmed terminal text [{label}]: '{req_str}' not found in {SVG_PATH}"
            )

    def test_05_middle_hud_score_and_status(self):
        """Verify Middle HUD displays score counter (+100 increments) and status badge."""
        content = self.read_svg_text(SVG_PATH)

        # HUD Score label / format
        self.assertTrue(
            re.search(r"SCORE|Score|PTS", content),
            "HUD score counter label ('SCORE') not found"
        )

        # Score increments (+100 per apple eaten synchronized)
        self.assertTrue(
            re.search(r"0100|100|0200|200|\+100", content),
            "HUD score +100 increments not found in score values or tspan elements"
        )

        # Status badge
        self.assertTrue(
            re.search(r"STATUS|HUNTING|EVADING|ONLINE|ACTIVE", content, re.IGNORECASE),
            "HUD status badge (e.g. 'STATUS', 'HUNTING APPLES', 'EVADING') not found"
        )

    def test_06_lower_arena_drones_and_apples(self):
        """Verify lower snake arena has 1-2 neon patrol drones with radar rings and snake elements."""
        tree, root = self.parse_svg(SVG_PATH)
        content = self.read_svg_text(SVG_PATH)

        # Check for drones (identified by drone id, class, or patrol elements)
        has_drone = bool(
            re.search(r'(drone|patrol|radar|obstacle)', content, re.IGNORECASE)
            or re.search(r'id="drone', content)
        )
        self.assertTrue(has_drone, "Neon patrol drones or obstacle elements not found in SVG")

        # Check for radar rings (animated circles with attributeName='r' or stroke pulsating)
        has_radar = bool(
            re.search(r'<animate[^>]+attributeName="(r|stroke-width|transform)"', content, re.IGNORECASE)
        )
        self.assertTrue(has_radar, "Radar rings / pulse animations for patrol drones not found")

        # Check for apple targets
        has_apples = bool(re.search(r'apple', content, re.IGNORECASE))
        self.assertTrue(has_apples, "Procedural apples not found in snake arena")


class TestTier3CLIGeneratorAndMechanics(BaseE2ETestCase):
    """Tier 3: Standalone CLI procedural generator, determinism, entropy and argument validation."""

    def test_01_generator_script_exists_and_runnable(self):
        """Verify scripts/generate_snake.py exists."""
        self.assertTrue(
            os.path.isfile(GENERATOR_PATH),
            f"Expected generator script to exist at {GENERATOR_PATH}"
        )

    def test_02_generator_cli_flags_support(self):
        """Verify CLI supports --seed, --hourly, and --output flags via --help."""
        self.assertTrue(os.path.isfile(GENERATOR_PATH), "Generator script does not exist yet")
        proc = subprocess.run(
            [sys.executable, GENERATOR_PATH, "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        self.assertEqual(proc.returncode, 0, f"Generator --help failed:\n{proc.stderr}")
        help_text = proc.stdout.lower()
        self.assertIn("--seed", help_text, "CLI --help does not mention --seed flag")
        self.assertIn("--hourly", help_text, "CLI --help does not mention --hourly flag")
        self.assertIn("--output", help_text, "CLI --help does not mention --output flag")

    def test_03_generator_seed_determinism(self):
        """Verify same seed produces byte-identical SVG outputs."""
        self.assertTrue(os.path.isfile(GENERATOR_PATH), "Generator script does not exist yet")
        out1 = os.path.join(self.temp_dir, "seed42_a.svg")
        out2 = os.path.join(self.temp_dir, "seed42_b.svg")

        cmd1 = [sys.executable, GENERATOR_PATH, "--seed", "42", "--output", out1]
        cmd2 = [sys.executable, GENERATOR_PATH, "--seed", "42", "--output", out2]

        proc1 = subprocess.run(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc1.returncode, 0, f"Generator run 1 failed:\n{proc1.stderr}")

        proc2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc2.returncode, 0, f"Generator run 2 failed:\n{proc2.stderr}")

        with open(out1, "rb") as f1, open(out2, "rb") as f2:
            hash1 = hashlib.sha256(f1.read()).hexdigest()
            hash2 = hashlib.sha256(f2.read()).hexdigest()

        self.assertEqual(
            hash1,
            hash2,
            f"DETERMINISM FAILED: Identical seed 42 produced differing byte hashes:\n{hash1} != {hash2}"
        )

    def test_04_generator_seed_entropy(self):
        """Verify different seeds produce distinct SVG outputs (route / apple / seed variation)."""
        self.assertTrue(os.path.isfile(GENERATOR_PATH), "Generator script does not exist yet")
        out1 = os.path.join(self.temp_dir, "seed_alpha.svg")
        out2 = os.path.join(self.temp_dir, "seed_beta.svg")

        proc1 = subprocess.run(
            [sys.executable, GENERATOR_PATH, "--seed", "111", "--output", out1],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        self.assertEqual(proc1.returncode, 0, f"Generator run 1 failed:\n{proc1.stderr}")

        proc2 = subprocess.run(
            [sys.executable, GENERATOR_PATH, "--seed", "999", "--output", out2],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        self.assertEqual(proc2.returncode, 0, f"Generator run 2 failed:\n{proc2.stderr}")

        with open(out1, "rb") as f1, open(out2, "rb") as f2:
            content1 = f1.read()
            content2 = f2.read()

        self.assertNotEqual(
            content1,
            content2,
            "ENTROPY FAILED: Seeds 111 and 999 produced identical byte output"
        )

    def test_05_generator_hourly_flag(self):
        """Verify --hourly flag executes successfully and outputs valid SVG."""
        self.assertTrue(os.path.isfile(GENERATOR_PATH), "Generator script does not exist yet")
        hourly_out = os.path.join(self.temp_dir, "hourly_test.svg")

        proc = subprocess.run(
            [sys.executable, GENERATOR_PATH, "--hourly", "--output", hourly_out],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        self.assertEqual(proc.returncode, 0, f"Generator --hourly failed:\n{proc.stderr}")
        self.assertTrue(os.path.isfile(hourly_out))

        # Check well-formedness of hourly output
        tree = ET.parse(hourly_out)
        self.assertEqual(self.strip_ns(tree.getroot().tag).lower(), "svg")

    def test_06_generator_invalid_arguments_fails(self):
        """Verify generator exits with non-zero exit code on invalid arguments."""
        self.assertTrue(os.path.isfile(GENERATOR_PATH), "Generator script does not exist yet")
        proc = subprocess.run(
            [sys.executable, GENERATOR_PATH, "--seed", "not_an_int"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        self.assertNotEqual(
            proc.returncode,
            0,
            "Expected generator to fail on invalid --seed argument, but exited with code 0"
        )


class TestTier4WorkflowAutomation(BaseE2ETestCase):
    """Tier 4: GitHub Actions Workflow Automation, Cron Schedule & Safety."""

    def test_01_workflow_file_exists(self):
        """Verify .github/workflows/update-snake.yml exists."""
        self.assertTrue(
            os.path.isfile(WORKFLOW_PATH),
            f"Expected workflow file to exist at {WORKFLOW_PATH}"
        )

    def test_02_workflow_yaml_syntax(self):
        """Verify .github/workflows/update-snake.yml is valid YAML."""
        self.assertTrue(os.path.isfile(WORKFLOW_PATH), "Workflow file does not exist yet")
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        if yaml:
            parsed = yaml.safe_load(content)
            self.assertIsInstance(
                parsed,
                dict,
                "Workflow YAML did not parse to a dictionary"
            )
        else:
            self.assertIn("name:", content)
            self.assertIn("jobs:", content)

    def test_03_workflow_cron_schedule(self):
        """Verify workflow has cron schedule configured for hourly execution ('0 * * * *')."""
        self.assertTrue(os.path.isfile(WORKFLOW_PATH), "Workflow file does not exist yet")
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertTrue(
            re.search(r"cron:\s*['\"]?0\s+\*\s+\*\s+\*\s+\*['\"]?", content),
            "Workflow does not contain required hourly cron: '0 * * * *'"
        )

    def test_04_workflow_permissions(self):
        """Verify workflow grants contents: write permission for committing."""
        self.assertTrue(os.path.isfile(WORKFLOW_PATH), "Workflow file does not exist yet")
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertTrue(
            re.search(r"permissions:[\s\S]*?contents:\s*write", content),
            "Workflow does not grant 'permissions: contents: write'"
        )

    def test_05_workflow_commit_skip_ci(self):
        """Verify commit step contains '[skip ci]' to prevent recursive CI loops."""
        self.assertTrue(os.path.isfile(WORKFLOW_PATH), "Workflow file does not exist yet")
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(
            "[skip ci]",
            content,
            "Workflow git commit command does not contain '[skip ci]'"
        )

    def test_06_workflow_invokes_generator(self):
        """Verify workflow executes scripts/generate_snake.py with snake-uam.svg output."""
        self.assertTrue(os.path.isfile(WORKFLOW_PATH), "Workflow file does not exist yet")
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertTrue(
            re.search(r"python3?\s+scripts/generate_snake\.py", content),
            "Workflow does not invoke scripts/generate_snake.py"
        )
        self.assertIn(
            "snake-uam.svg",
            content,
            "Workflow does not specify snake-uam.svg as target output"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
