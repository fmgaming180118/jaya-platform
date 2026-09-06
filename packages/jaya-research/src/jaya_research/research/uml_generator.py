import re
import zlib
from typing import Tuple

from jaya_research.teacher import Teacher

UML_SYSTEM_INSTRUCTION = (
    "You are a strict UML designer. Output only valid PlantUML code enclosed "
    "in @startuml and @enduml."
)


class UMLValidationError(Exception):
    """Exception raised when a UML diagram violates formal guidelines."""

    pass


class UMLGenerator:
    """
    Generates, validates, and renders formal UML diagrams (PlantUML)
    using the reasoning NIM LLM and Python-level structural verification.
    """

    def __init__(self):
        self.agent = Teacher(model_type="reasoning")

    def generate_diagram(self, spec: str, diagram_type: str) -> Tuple[str, str]:
        """
        Generates a validated UML diagram based on user requirements.
        Uses a self-correction loop if rules are violated.

        Args:
            spec: User request / specification
            diagram_type: one of 'usecase', 'class', 'sequence', 'activity'

        Returns:
            Tuple[str, str]: (PlantUML code, Rendered SVG URL)
        """
        prompt = self._build_prompt(spec, diagram_type)

        max_attempts = 3
        last_error = ""

        for attempt in range(max_attempts):
            if last_error:
                correction_prompt = (
                    f"{prompt}\n\n"
                    "PERINGATAN: Percobaan sebelumnya gagal karena "
                    "kesalahan berikut:\n"
                    f"{last_error}\n\n"
                    "Perbaiki kode PlantUML agar memenuhi semua aturan UML."
                )
                print(
                    f"[UML] Attempt {attempt + 1}: "
                    "requesting correction from Teacher..."
                )
                code = self.agent.ask(
                    correction_prompt,
                    system_instruction=UML_SYSTEM_INSTRUCTION,
                )
            else:
                print(
                    f"[UML] Attempt {attempt + 1}: Generating {diagram_type} diagram..."
                )
                code = self.agent.ask(
                    prompt,
                    system_instruction=UML_SYSTEM_INSTRUCTION,
                )

            code = self._clean_code(code)

            # Validate code
            try:
                self.validate_diagram(code, diagram_type)
                print(
                    f"[UML] ✅ Diagram successfully validated on attempt {attempt + 1}."
                )
                url = self.get_render_url(code)
                return code, url
            except UMLValidationError as e:
                print(f"[UML] ❌ Validation failed on attempt {attempt + 1}: {e}")
                last_error = str(e)

        raise UMLValidationError(
            "Gagal menghasilkan diagram UML yang valid setelah "
            f"{max_attempts} percobaan. Error terakhir: {last_error}"
        )

    def validate_diagram(self, code: str, diagram_type: str):
        """
        Enforces strict academic UML guidelines on the PlantUML source code.
        """
        if "@startuml" not in code or "@enduml" not in code:
            raise UMLValidationError(
                "Diagram harus memiliki penanda @startuml dan @enduml."
            )

        # Strip comments
        lines = []
        for line in code.splitlines():
            line_strip = line.strip()
            if (
                line_strip
                and not line_strip.startswith("'")
                and not line_strip.startswith("/'")
            ):
                lines.append(line_strip)

        clean_code = "\n".join(lines)

        if diagram_type == "usecase":
            self._validate_usecase(clean_code)
        elif diagram_type == "class":
            self._validate_class(clean_code)
        elif diagram_type == "sequence":
            self._validate_sequence(clean_code)
        elif diagram_type == "activity":
            self._validate_activity(clean_code)
        else:
            raise ValueError(f"Tipe diagram tidak dikenal: {diagram_type}")

    def _validate_usecase(self, code: str):
        """
        Validates Use Case diagrams:
        1. Actors cannot associate with other actors directly.
        2. Use Cases must have at least one direct or indirect actor connection.
        3. Standard connections only.
        """
        lines = code.splitlines()
        actors = set()
        usecases = set()
        aliases = {}

        # 1. Parse entities (actors and usecases) with alias support
        for line in lines:
            # actor syntax: actor Name or actor "Name" as Alias
            act_match = re.search(
                r'actor\s+("([^"]+)"|[\w\-]+)(?:\s+as\s+(\w+))?', line
            )
            if act_match:
                disp_name = act_match.group(2) or act_match.group(1)
                actors.add(self._clean_entity_name(disp_name))
                if act_match.group(3):
                    actors.add(act_match.group(3))
                continue

            inline_act = re.search(r":([^:]+):(?:\s+as\s+(\w+))?", line)
            if inline_act:
                disp_name = inline_act.group(1)
                actors.add(self._clean_entity_name(disp_name))
                if inline_act.group(2):
                    actors.add(inline_act.group(2))
                continue

            # usecase syntax: usecase UC or usecase "UC" as Alias
            uc_match = re.search(
                r'usecase\s+("([^"]+)"|[\w\-]+)(?:\s+as\s+(\w+))?', line
            )
            if uc_match:
                disp_name = uc_match.group(2) or uc_match.group(1)
                disp_name_clean = self._clean_entity_name(disp_name)
                usecases.add(disp_name_clean)
                if uc_match.group(3):
                    alias = uc_match.group(3)
                    usecases.add(alias)
                    aliases[alias] = disp_name_clean
                continue

            inline_uc = re.search(r"\(([^)]+)\)(?:\s+as\s+(\w+))?", line)
            if inline_uc:
                disp_name = inline_uc.group(1)
                disp_name_clean = self._clean_entity_name(disp_name)
                usecases.add(disp_name_clean)
                if inline_uc.group(2):
                    alias = inline_uc.group(2)
                    usecases.add(alias)
                    aliases[alias] = disp_name_clean
                continue

        # Fallback inline parse for actors and usecases in associations
        for line in lines:
            if "--" in line or "->" in line or "<-" in line:
                if "<<include>>" in line or "<<extend>>" in line:
                    continue
                parts = re.split(r"[-<>]", line)
                parts = [p.strip() for p in parts if p.strip()]
                for p in parts:
                    if p.startswith(":") and p.endswith(":"):
                        actors.add(self._clean_entity_name(p))
                    elif p.startswith("(") and p.endswith(")"):
                        usecases.add(self._clean_entity_name(p))

        # 2. Check actor-to-actor direct association
        for line in lines:
            if "--" in line or "->" in line or "<-" in line:
                # Exclude <<include>> and <<extend>> stereotype relations.
                if "<<include>>" in line or "<<extend>>" in line:
                    continue
                # Split relation
                parts = re.split(r"--+|->+|<-+", line)
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) >= 2:
                    p1 = self._clean_entity_name(parts[0])
                    p2 = self._clean_entity_name(parts[1])
                    if p1 in actors and p2 in actors:
                        raise UMLValidationError(
                            f"Pelanggaran UML: Aktor '{p1}' tidak boleh "
                            f"terhubung langsung ke Aktor '{p2}'."
                        )

        # 3. Check every use case has a direct or indirect actor connection.
        # Construct graph of usecase relationships
        connections = {u: set() for u in usecases}

        # Link aliases to their canonical use case names in the graph
        for alias, disp_name in aliases.items():
            if alias in connections and disp_name in connections:
                connections[alias].add(disp_name)
                connections[disp_name].add(alias)

        connected_to_actor = set()

        for line in lines:
            if "--" in line or "->" in line or "<-" in line:
                parts = re.split(r"--+|->+|<-+", line)
                parts = [self._clean_entity_name(p.strip()) for p in parts if p.strip()]
                if len(parts) >= 2:
                    p1, p2 = parts[0], parts[1]

                    is_p1_act = p1 in actors
                    is_p2_act = p2 in actors
                    is_p1_uc = p1 in usecases
                    is_p2_uc = p2 in usecases

                    if is_p1_act and is_p2_uc:
                        connected_to_actor.add(p2)
                    elif is_p2_act and is_p1_uc:
                        connected_to_actor.add(p1)
                    elif is_p1_uc and is_p2_uc:
                        # Include/Extend bi-directional traversal
                        connections[p1].add(p2)
                        connections[p2].add(p1)

        # BFS to find reachable usecases from actors
        queue = list(connected_to_actor)
        visited = set(queue)
        while queue:
            curr = queue.pop(0)
            for neighbor in connections.get(curr, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        # An aliased declaration has two graph identifiers (display name and
        # alias), but represents one use case. Report only its canonical alias
        # so validation errors are deterministic and do not duplicate labels.
        aliased_display_names = set(aliases.values())
        unconnected_ucs = {
            usecase
            for usecase in usecases - visited
            if usecase not in aliased_display_names
        }
        if unconnected_ucs:
            unconnected_names = ", ".join(sorted(unconnected_ucs))
            raise UMLValidationError(
                "Pelanggaran UML: Use case berikut tidak terhubung ke "
                f"Aktor mana pun: {unconnected_names}"
            )

    def _validate_class(self, code: str):
        """
        Validates Class diagrams:
        1. Ensures relationship syntax uses standard arrow heads.
        2. Enforces access modifiers on attributes and methods (+, -, #, ~).
        """
        lines = code.splitlines()

        # Check arrows
        invalid_arrows = ["<-|", "---", "..>"]
        for line in lines:
            for arr in invalid_arrows:
                if arr in line and not line.startswith("'"):
                    raise UMLValidationError(
                        f"Pelanggaran Pedoman UML: Simbol panah relasi "
                        f"'{arr}' tidak sesuai standar UML (Gunakan <|--, "
                        "*--, o--, atau -->)."
                    )

        inside_class_block = False
        expecting_brace = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # If we saw a class declaration and now see the opening brace
            if expecting_brace and stripped == "{":
                inside_class_block = True
                expecting_brace = False
                continue

            expecting_brace = False

            # Detect class declaration
            if any(k in stripped for k in ["class ", "interface ", "enum "]) or any(
                stripped.startswith(k) for k in ["class", "interface", "enum"]
            ):
                # Ensure it's not a relation line or inline definition
                if "{" in stripped:
                    inside_class_block = True
                    continue
                elif ":" not in stripped and not any(
                    sym in stripped for sym in ["--", "..", "->", "<-"]
                ):
                    expecting_brace = True
                    continue

            if stripped == "}":
                inside_class_block = False
                continue

            # Skip comments, annotations, skinparams, notes, relations
            if (
                stripped.startswith("'")
                or stripped.startswith("/'")
                or stripped.startswith("@")
                or stripped.startswith("skinparam")
            ):
                continue
            if stripped.startswith("note") or " note " in stripped:
                continue
            if any(sym in stripped for sym in ["--", "..", "->", "<-", "<|"]):
                continue

            # Now validate fields/methods
            if ":" in stripped:
                if inside_class_block:
                    # Inside class block, the line itself must start with visibility
                    if not any(stripped.startswith(x) for x in ["+", "-", "#", "~"]):
                        raise UMLValidationError(
                            f"Pelanggaran Pedoman UML: Atribut/Metode "
                            f"'{stripped}' di dalam kelas harus dideklarasikan "
                            "dengan visibilitas (+, -, #, ~)."
                        )
                else:
                    # Outside a block, check an inline class member definition.
                    # Supports quoted class names: "ClassName" : attribute
                    match = re.match(r'^("?[\w\-]+"?)\s*:\s*(.+)$', stripped)
                    if match:
                        member_def = match.group(2).strip()
                        # If the member definition does not start with visibility
                        if not any(
                            member_def.startswith(x) for x in ["+", "-", "#", "~"]
                        ):
                            raise UMLValidationError(
                                f"Pelanggaran Pedoman UML: Atribut/Metode "
                                f"'{stripped}' harus dideklarasikan dengan "
                                "visibilitas (+, -, #, ~)."
                            )

    def _validate_sequence(self, code: str):
        """
        Validates Sequence diagrams:
        1. Ensures every activation has a matching deactivation.
        """
        lines = code.splitlines()
        activations = {}

        for line_num, line in enumerate(lines, 1):
            act_match = re.match(r"^activate\s+(\w+)", line)
            deact_match = re.match(r"^deactivate\s+(\w+)", line)

            if act_match:
                name = act_match.group(1)
                activations[name] = activations.get(name, 0) + 1
            elif deact_match:
                name = deact_match.group(1)
                if activations.get(name, 0) <= 0:
                    raise UMLValidationError(
                        f"Pelanggaran Pedoman UML: Lifeline '{name}' "
                        f"dideaktivasi pada baris {line_num} tanpa "
                        "diaktivasi terlebih dahulu."
                    )
                activations[name] -= 1

        # Check leftover activations
        for name, count in activations.items():
            if count > 0:
                raise UMLValidationError(
                    f"Pelanggaran Pedoman UML: Lifeline '{name}' diaktivasi "
                    "tetapi tidak dideaktivasi di akhir diagram."
                )

    def _validate_activity(self, code: str):
        """
        Validates Activity diagrams (New syntax):
        1. Ensures start and stop/end exist.
        2. Ensures conditionals (if/else/endif) are balanced.
        """
        lines = code.splitlines()

        has_start = any(re.match(r"^start\b", line) for line in lines)
        has_stop = any(re.match(r"^(stop|end)\b", line) for line in lines)

        if not has_start:
            raise UMLValidationError(
                "Pelanggaran UML: Activity diagram harus memiliki node "
                "mulai ('start')."
            )
        if not has_stop:
            raise UMLValidationError(
                "Pelanggaran UML: Activity diagram harus memiliki node "
                "akhir ('stop' atau 'end')."
            )

        # Check if/endif balance
        if_count = 0
        for line in lines:
            if re.match(r"^if\s*\(", line):
                if_count += 1
            elif re.match(r"^endif\b", line):
                if_count -= 1
                if if_count < 0:
                    raise UMLValidationError(
                        "Pelanggaran UML: 'endif' ditemukan tanpa pembuka 'if'."
                    )

        if if_count > 0:
            raise UMLValidationError(
                f"Pelanggaran Pedoman UML: Terdapat {if_count} blok 'if' "
                "yang tidak ditutup dengan 'endif'."
            )

    def get_render_url(self, code: str) -> str:
        """
        Generates a PlantUML server rendering URL using raw DEFLATE compression.
        """
        # Compress and encode
        encoded = self._encode_deflate(code)
        return f"https://www.plantuml.com/plantuml/svg/~1{encoded}"

    def _encode_deflate(self, text: str) -> str:
        """PlantUML custom base64 Deflate encoding."""
        # 1. Compress with raw DEFLATE
        compressor = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15)
        compressed = compressor.compress(text.encode("utf-8")) + compressor.flush()

        # 2. PlantUML custom Base64 alphabet mapping
        CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
        encoded = []
        i = 0
        n = len(compressed)

        while i < n:
            b1 = compressed[i]
            b2 = compressed[i + 1] if i + 1 < n else 0
            b3 = compressed[i + 2] if i + 2 < n else 0

            c1 = b1 >> 2
            c2 = ((b1 & 0x3) << 4) | (b2 >> 4)
            c3 = ((b2 & 0xF) << 2) | (b3 >> 6)
            c4 = b3 & 0x3F

            encoded.append(CHARS[c1])
            encoded.append(CHARS[c2])
            if i + 1 < n:
                encoded.append(CHARS[c3])
            if i + 2 < n:
                encoded.append(CHARS[c4])
            i += 3

        return "".join(encoded)

    def _clean_code(self, code: str) -> str:
        """Extracts code blocks from markdown wraps."""
        code = code.strip()
        if "```plantuml" in code:
            code = code.split("```plantuml")[1].split("```")[0]
        elif "```" in code:
            code = code.split("```")[1].split("```")[0]
        return code.strip()

    def _clean_entity_name(self, name: str) -> str:
        """Cleans inline parentheses, colons, and quotes from parsed names."""
        name = name.strip()
        if name.startswith(":") and name.endswith(":"):
            name = name[1:-1].strip()
        elif name.startswith("(") and name.endswith(")"):
            name = name[1:-1].strip()

        # Strip surrounding double or single quotes
        if name.startswith('"') and name.endswith('"'):
            name = name[1:-1].strip()
        elif name.startswith("'") and name.endswith("'"):
            name = name[1:-1].strip()

        return name

    def _build_prompt(self, spec: str, diagram_type: str) -> str:
        """Constructs strict rules prompt for the LLM based on diagram type."""
        rules = {
            "usecase": (
                "- Gunakan batas sistem (rectangle boundary)\n"
                "- Aktor dilambangkan dengan :Nama Aktor:\n"
                "- Use Case dilambangkan dengan (Nama Use Case)\n"
                "- Dilarang menghubungkan aktor langsung ke aktor lain!\n"
                "- Setiap Use Case wajib terhubung langsung atau tidak "
                "langsung ke aktor."
            ),
            "class": (
                "- Definisikan atribut dan metode di dalam kelas\n"
                "- Wajib mencantumkan visibilitas (+ public, - private, "
                "# protected)\n"
                "- Gunakan panah standar: pewarisan (<|--), komposisi "
                "(*--), agregasi (o--)."
            ),
            "sequence": (
                "- Cantumkan participant / lifeline\n"
                "- Aktivasi lifeline wajib seimbang menggunakan 'activate' "
                "dan 'deactivate'."
            ),
            "activity": (
                "- Gunakan sintaks activity: @startuml, start, :Activity;, "
                "stop, @enduml\n"
                "- Wajib ditutup dengan 'stop' atau 'end'\n"
                "- Blok percabangan wajib diakhiri dengan 'endif'."
            ),
        }

        prompt = f"""Tulis kode PlantUML untuk diagram {diagram_type.upper()}
berdasarkan spesifikasi berikut:

SPESIFIKASI:
{spec}

ATURAN FORMAL DIAS/PEDOMAN UML:
{rules[diagram_type]}

Ketentuan Output:
1. Kembalikan HANYA kode PlantUML terbungkus di dalam block ```plantuml ... ```.
2. Dilarang memberikan narasi penjelasan tambahan di luar kode block.
"""
        return prompt


if __name__ == "__main__":
    # Self-test
    try:
        gen = UMLGenerator()
        print("[TEST] Generating Use Case...")
        code, url = gen.generate_diagram(
            "Aktor Mahasiswa login dan melihat nilai, Dosen login dan mengisi nilai.",
            "usecase",
        )
        print("Code:\n", code)
        print("URL:\n", url)
    except Exception as e:
        print("[TEST ERROR] Fail:", e)
