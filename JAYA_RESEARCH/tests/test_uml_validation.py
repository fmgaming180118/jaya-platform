import unittest
import sys, os
from pathlib import Path

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from research.uml_generator import UMLGenerator, UMLValidationError

class TestUMLValidation(unittest.TestCase):
    
    def setUp(self):
        self.validator = UMLGenerator()
        
    # ── USE CASE DIAGRAM TESTS ───────────────────────────────────────────────
    def test_valid_usecase(self):
        code = """@startuml
left to right direction
actor Mahasiswa as m
actor Dosen as d
rectangle SistemAkademik {
  usecase "Login" as uc1
  usecase "Melihat Nilai" as uc2
  usecase "Mengisi Nilai" as uc3
}
m -- uc1
m -- uc2
d -- uc1
d -- uc3
@enduml"""
        # Should not raise exception
        try:
            self.validator.validate_diagram(code, "usecase")
        except UMLValidationError as e:
            self.fail(f"Valid Use Case diagram failed validation: {e}")

    def test_invalid_usecase_actor_association(self):
        code = """@startuml
actor Mahasiswa as m
actor Dosen as d
m -- d
@enduml"""
        with self.assertRaises(UMLValidationError) as context:
            self.validator.validate_diagram(code, "usecase")
        self.assertIn("Aktor 'm' tidak boleh terhubung langsung ke Aktor 'd'", str(context.exception))

    def test_invalid_usecase_unconnected_usecase(self):
        code = """@startuml
actor Mahasiswa as m
rectangle Sistem {
  usecase (Login) as uc1
  usecase (Mencetak KHS) as uc2
}
m -- uc1
@enduml"""
        with self.assertRaises(UMLValidationError) as context:
            self.validator.validate_diagram(code, "usecase")
        self.assertIn("Use case berikut tidak terhubung ke Aktor mana pun: uc2", str(context.exception))

    # ── CLASS DIAGRAM TESTS ──────────────────────────────────────────────────
    def test_valid_class_diagram(self):
        code = """@startuml
class Mahasiswa {
  - nim : String
  + nama : String
  # ipk : float
  + cetakKHS() : void
}
class SIIOStudent {
  + prodi : String
}
SIIOStudent --|> Mahasiswa
@enduml"""
        try:
            self.validator.validate_diagram(code, "class")
        except UMLValidationError as e:
            self.fail(f"Valid Class diagram failed validation: {e}")

    def test_class_diagram_with_note_and_labeled_relations(self):
        code = """@startuml
class Mahasiswa {
  - nim : String
}
class Dosen {
  - nip : String
}
Mahasiswa "1" -- "0..*" Dosen : bimbingan
note top of Mahasiswa : Ini adalah catatan akademik
@enduml"""
        try:
            self.validator.validate_diagram(code, "class")
        except UMLValidationError as e:
            self.fail(f"Class diagram with notes and labeled relations failed validation: {e}")

    def test_usecase_diagram_with_quoted_actors(self):
        code = """@startuml
actor "Dosen Pembimbing" as dp
rectangle Sistem {
  usecase (Bimbingan Online) as uc1
}
"Dosen Pembimbing" -- uc1
@enduml"""
        try:
            self.validator.validate_diagram(code, "usecase")
        except UMLValidationError as e:
            self.fail(f"Use case with quoted actors failed validation: {e}")

    def test_invalid_class_missing_visibility(self):
        code = """@startuml
class Mahasiswa {
  nim : String
  + nama : String
}
@enduml"""
        with self.assertRaises(UMLValidationError) as context:
            self.validator.validate_diagram(code, "class")
        self.assertIn("Atribut/Metode 'nim : String'", str(context.exception))
        self.assertIn("harus dideklarasikan dengan visibilitas", str(context.exception))

    def test_invalid_class_arrow(self):
        code = """@startuml
class Parent
class Child
Child --- Parent
@enduml"""
        with self.assertRaises(UMLValidationError) as context:
            self.validator.validate_diagram(code, "class")
        self.assertIn("Simbol panah relasi '---' tidak sesuai standar UML", str(context.exception))

    # ── SEQUENCE DIAGRAM TESTS ───────────────────────────────────────────────
    def test_valid_sequence(self):
        code = """@startuml
participant User
participant System
User -> System : login()
activate System
System --> User : success
deactivate System
@enduml"""
        try:
            self.validator.validate_diagram(code, "sequence")
        except UMLValidationError as e:
            self.fail(f"Valid Sequence diagram failed: {e}")

    def test_invalid_sequence_unbalanced_deactivate(self):
        code = """@startuml
participant User
participant System
User -> System : login()
deactivate System
@enduml"""
        with self.assertRaises(UMLValidationError) as context:
            self.validator.validate_diagram(code, "sequence")
        self.assertIn("Lifeline 'System' dideaktivasi pada baris 5 tanpa diaktivasi terlebih dahulu", str(context.exception))

    def test_invalid_sequence_leftover_activation(self):
        code = """@startuml
participant User
participant System
User -> System : login()
activate System
@enduml"""
        with self.assertRaises(UMLValidationError) as context:
            self.validator.validate_diagram(code, "sequence")
        self.assertIn("Lifeline 'System' diaktivasi tetapi tidak dideaktivasi di akhir diagram", str(context.exception))

    # ── ACTIVITY DIAGRAM TESTS ───────────────────────────────────────────────
    def test_valid_activity(self):
        code = """@startuml
start
:Login;
if (Valid?) then (yes)
  :Tampilkan Menu;
else (no)
  :Tampilkan Error;
endif
stop
@enduml"""
        try:
            self.validator.validate_diagram(code, "activity")
        except UMLValidationError as e:
            self.fail(f"Valid Activity diagram failed: {e}")

    def test_invalid_activity_missing_start(self):
        code = """@startuml
:Login;
stop
@enduml"""
        with self.assertRaises(UMLValidationError) as context:
            self.validator.validate_diagram(code, "activity")
        self.assertIn("Activity diagram harus memiliki node mulai ('start')", str(context.exception))

    def test_invalid_activity_unclosed_if(self):
        code = """@startuml
start
:Login;
if (Valid?) then (yes)
  :Tampilkan Menu;
else (no)
  :Tampilkan Error;
stop
@enduml"""
        with self.assertRaises(UMLValidationError) as context:
            self.validator.validate_diagram(code, "activity")
        self.assertIn("Terdapat 1 blok 'if' yang tidak ditutup dengan 'endif'", str(context.exception))

    # ── RENDER ENCODING TESTS ────────────────────────────────────────────────
    def test_get_render_url(self):
        code = "@startuml\nBob -> Alice : hello\n@enduml"
        url = self.validator.get_render_url(code)
        self.assertTrue(url.startswith("http://www.plantuml.com/plantuml/svg/~1"))
        # Ensure it generated a non-empty compressed hash payload
        payload = url.replace("http://www.plantuml.com/plantuml/svg/~1", "")
        self.assertGreater(len(payload), 10)

if __name__ == '__main__':
    unittest.main()
