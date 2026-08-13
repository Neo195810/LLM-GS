import tempfile
import unittest
from pathlib import Path

from prog_policies.karel import KarelDSL
from prog_policies.skills import SkillLibrary


class SkillLibraryTest(unittest.TestCase):
    def test_extract_persist_retrieve_and_parse(self):
        dsl = KarelDSL()
        program = dsl.parse_str_to_node(
            "DEF run m( WHILE c( frontIsClear c) w( move w) turnLeft m)"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "skills.json"
            def embedding(text):
                return [float("maze" in text.lower()), float("while" in text.lower()), 1.0]

            library = SkillLibrary(path, "karel", embedding_fn=embedding)
            self.assertGreaterEqual(library.extract_and_store(program, 1.0, "Maze", dsl), 2)
            loaded = SkillLibrary(path, "karel", embedding_fn=embedding)
            skills = loaded.retrieve("Maze", limit=5)
            self.assertTrue(skills)
            for skill in skills:
                self.assertTrue(dsl.parse_str_to_node(skill["dsl_program"]).is_complete())
            self.assertIn("Verified reusable DSL skills", loaded.prompt_block(skills))


if __name__ == "__main__":
    unittest.main()
