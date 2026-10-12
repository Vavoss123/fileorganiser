"""Tests for the organiser engine. No GUI, no real Downloads folder."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from organiser import apply as apply_module
from organiser import duplicates, plan as plan_module, rules, scan


def write(folder: str, name: str, content: bytes = b"x") -> str:
    path = os.path.join(folder, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(content)
    return path


class RuleTests(unittest.TestCase):
    def test_media_buckets(self):
        self.assertEqual(rules.destination_for("holiday.JPG"), "Pictures")
        self.assertEqual(rules.destination_for("clip.mkv"), "Videos")
        self.assertEqual(rules.destination_for("song.flac"), "Audio")
        self.assertEqual(rules.destination_for("notes.txt"), "Documents")
        self.assertEqual(rules.destination_for("budget.xlsx"), "Documents/Spreadsheets")

    def test_application_files_get_their_own_folder(self):
        self.assertEqual(rules.destination_for("donut.blend"), "Apps/Blender")
        self.assertEqual(rules.destination_for("donut.blend1"), "Apps/Blender")
        self.assertEqual(rules.destination_for("poster.psd"), "Apps/Photoshop")
        self.assertEqual(rules.destination_for("track.flp"), "Apps/FL Studio")

    def test_screenshots_are_separated(self):
        self.assertEqual(rules.destination_for("Screenshot 2026-01-02.png"), "Pictures/Screenshots")

    def test_unknown_goes_to_other(self):
        self.assertEqual(rules.destination_for("mystery.qzx"), "Other")
        self.assertEqual(rules.destination_for("no-extension"), "Other")

    def test_in_progress_downloads_are_skipped(self):
        self.assertTrue(rules.should_skip("big.iso.crdownload"))
        self.assertTrue(rules.should_skip("movie.mp4.part"))
        self.assertTrue(rules.should_skip("Thumbs.db"))
        self.assertTrue(rules.should_skip("~$report.docx"))
        self.assertFalse(rules.should_skip("movie.mp4"))


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def plan_for(self, **kwargs) -> plan_module.Plan:
        result = scan.scan(self.root, ignore_folders=set(rules.known_destinations()),
                           **kwargs.pop("scan_kwargs", {}))
        return plan_module.build_plan(result, **kwargs)

    def test_plan_routes_files_into_subfolders(self):
        write(self.root, "cat.png")
        write(self.root, "model.blend")
        built = self.plan_for()
        destinations = {m.info.name: m.destination for m in built.moves}
        self.assertEqual(destinations["cat.png"], os.path.join(self.root, "Pictures", "cat.png"))
        self.assertEqual(
            destinations["model.blend"],
            os.path.join(self.root, "Apps", "Blender", "model.blend"),
        )

    def test_folders_the_rules_own_are_left_out_of_the_scan(self):
        write(self.root, os.path.join("Pictures", "cat.png"))
        built = self.plan_for(scan_kwargs={"max_depth": 1})
        self.assertEqual(built.moves, [])
        self.assertEqual(built.already_tidy, [])

    def test_a_file_already_in_its_bucket_is_counted_as_tidy(self):
        # "Other" is a bucket, so a scan that does see it must not plan a move.
        write(self.root, os.path.join("Other", "mystery.qzx"))
        result = scan.scan(self.root, max_depth=1)
        built = plan_module.build_plan(result)
        self.assertEqual(built.moves, [])
        self.assertEqual(len(built.already_tidy), 1)

    def test_rescan_ignores_folders_we_created(self):
        write(self.root, "cat.png")
        first = self.plan_for()
        apply_module.apply_moves(first.moves)
        second = self.plan_for(scan_kwargs={"max_depth": 2})
        self.assertEqual(second.moves, [])

    def test_name_clash_is_renamed_not_overwritten(self):
        write(self.root, os.path.join("Pictures", "cat.png"), b"original")
        write(self.root, "cat.png", b"different")
        built = self.plan_for()
        move = built.moves[0]
        self.assertTrue(move.renamed)
        self.assertEqual(os.path.basename(move.destination), "cat (2).png")

    def test_two_incoming_files_with_the_same_name_do_not_collide(self):
        write(self.root, os.path.join("a", "cat.png"), b"one")
        write(self.root, os.path.join("b", "cat.png"), b"two")
        built = self.plan_for(scan_kwargs={"max_depth": 1})
        names = sorted(os.path.basename(m.destination) for m in built.moves)
        self.assertEqual(names, ["cat (2).png", "cat.png"])

    def test_other_bucket_can_be_turned_off(self):
        write(self.root, "mystery.qzx")
        self.assertEqual(len(self.plan_for().moves), 1)
        self.assertEqual(len(self.plan_for(include_other=False).moves), 0)

    def test_library_routing_sends_media_home(self):
        write(self.root, "cat.png")
        write(self.root, "model.blend")
        home = os.path.join(self.root, "_home")
        result = scan.scan(self.root, ignore_folders=set(rules.known_destinations()))
        built = plan_module.build_plan(result, route_to_libraries=True, home=home)
        by_name = {m.info.name: m.destination for m in built.moves}
        self.assertEqual(by_name["cat.png"], os.path.join(home, "Pictures", "cat.png"))
        self.assertEqual(
            by_name["model.blend"], os.path.join(self.root, "Apps", "Blender", "model.blend")
        )


class DuplicateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def files(self):
        return scan.scan(self.root, max_depth=2).files

    def test_same_content_different_names_is_a_duplicate(self):
        body = b"CURRICULUM VITAE" * 100
        write(self.root, "victor cv 1.pdf", body)
        write(self.root, "victor stokoe cv.pdf", body)
        groups = duplicates.find_duplicates(self.files())
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].files), 2)
        self.assertEqual(groups[0].keeper.name, "victor stokoe cv.pdf")
        self.assertEqual([f.name for f in groups[0].redundant], ["victor cv 1.pdf"])
        self.assertEqual(groups[0].wasted, len(body))

    def test_copy_marker_names_are_never_the_keeper(self):
        body = b"report" * 50
        write(self.root, "report - Copy.docx", body)
        write(self.root, "report.docx", body)
        group = duplicates.find_duplicates(self.files())[0]
        self.assertEqual(group.keeper.name, "report.docx")

    def test_same_size_different_content_is_not_a_duplicate(self):
        write(self.root, "a.bin", b"a" * 5000)
        write(self.root, "b.bin", b"b" * 5000)
        self.assertEqual(duplicates.find_duplicates(self.files()), [])

    def test_large_files_needing_the_full_hash(self):
        shared_head = b"H" * (1 << 16)
        write(self.root, "one.bin", shared_head + b"tail-a")
        write(self.root, "two.bin", shared_head + b"tail-b")
        write(self.root, "three.bin", shared_head + b"tail-a")
        groups = duplicates.find_duplicates(self.files())
        self.assertEqual(len(groups), 1)
        self.assertEqual({f.name for f in groups[0].files}, {"one.bin", "three.bin"})

    def test_empty_files_are_ignored(self):
        write(self.root, "empty1.txt", b"")
        write(self.root, "empty2.txt", b"")
        self.assertEqual(duplicates.find_duplicates(self.files()), [])

    def test_normalised_stem_strips_copy_markers(self):
        self.assertEqual(duplicates.normalised_stem("report (1).pdf"), "report")
        self.assertEqual(duplicates.normalised_stem("report - Copy.pdf"), "report")
        self.assertEqual(duplicates.normalised_stem("report copy 2.pdf"), "report")
        self.assertEqual(duplicates.normalised_stem("report_final.pdf"), "report")
        self.assertEqual(duplicates.normalised_stem("my_report v2.pdf"), "my report")
        self.assertEqual(duplicates.normalised_stem("victor cv 1.pdf"), "victor cv")

    def test_timestamped_names_are_not_eroded_into_one_bucket(self):
        # Two unrelated screenshots must not look like versions of each other.
        self.assertNotEqual(
            duplicates.normalised_stem("Screenshot 2026-03-11 141022.png"),
            duplicates.normalised_stem("Screenshot 2026-03-12 090533.png"),
        )
        write(self.root, "Screenshot 2026-03-11 141022.png", b"one")
        write(self.root, "Screenshot 2026-03-12 090533.png", b"two different")
        self.assertEqual(duplicates.find_possible_versions(self.files()), [])

    def test_possible_versions_are_name_based_and_exclude_exact_duplicates(self):
        write(self.root, "essay.docx", b"draft one")
        write(self.root, "essay (1).docx", b"draft two, longer")
        groups = duplicates.find_possible_versions(self.files())
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].stem, "essay")

        same = b"identical"
        write(self.root, "photo.png", same)
        write(self.root, "photo (1).png", same)
        exact = duplicates.find_duplicates(self.files())
        versions = duplicates.find_possible_versions(self.files(), exact)
        self.assertNotIn("photo", [g.stem for g in versions])


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        self.journals = tempfile.TemporaryDirectory()
        self.addCleanup(self.journals.cleanup)
        original = apply_module.journal_dir
        apply_module.journal_dir = lambda: self.journals.name
        self.addCleanup(lambda: setattr(apply_module, "journal_dir", original))

    def build(self):
        result = scan.scan(self.root, ignore_folders=set(rules.known_destinations()))
        return plan_module.build_plan(result)

    def test_apply_moves_files_and_writes_a_journal(self):
        write(self.root, "cat.png", b"image")
        report = apply_module.apply_moves(self.build().moves)
        self.assertEqual(len(report.moved), 1)
        self.assertFalse(report.failed)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "Pictures", "cat.png")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "cat.png")))
        self.assertTrue(os.path.isfile(report.journal_path))

    def test_nothing_is_deleted_when_the_destination_exists(self):
        write(self.root, os.path.join("Pictures", "cat.png"), b"original")
        write(self.root, "cat.png", b"new")
        apply_module.apply_moves(self.build().moves)
        with open(os.path.join(self.root, "Pictures", "cat.png"), "rb") as handle:
            self.assertEqual(handle.read(), b"original")
        self.assertTrue(os.path.isfile(os.path.join(self.root, "Pictures", "cat (2).png")))

    def test_only_selected_moves_run(self):
        write(self.root, "cat.png")
        write(self.root, "clip.mp4")
        built = self.build()
        for move in built.moves:
            move.include = move.info.name == "cat.png"
        apply_module.apply_moves(built.selected)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "Pictures", "cat.png")))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "clip.mp4")))

    def test_undo_puts_everything_back_and_removes_empty_folders(self):
        write(self.root, "cat.png", b"image")
        write(self.root, "model.blend", b"mesh")
        report = apply_module.apply_moves(self.build().moves)
        undone = apply_module.undo(report.journal_path)
        self.assertFalse(undone.failed)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "cat.png")))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "model.blend")))
        self.assertFalse(os.path.isdir(os.path.join(self.root, "Pictures")))
        self.assertFalse(os.path.isdir(os.path.join(self.root, "Apps", "Blender")))
        self.assertFalse(os.path.isdir(os.path.join(self.root, "Apps")))
        self.assertEqual(sorted(os.listdir(self.root)), ["cat.png", "model.blend"])

    def test_undo_skips_files_the_user_moved_on(self):
        write(self.root, "cat.png", b"image")
        report = apply_module.apply_moves(self.build().moves)
        os.remove(os.path.join(self.root, "Pictures", "cat.png"))
        undone = apply_module.undo(report.journal_path)
        self.assertEqual(len(undone.failed), 1)
        self.assertEqual(undone.moved, [])

    def test_missing_source_is_reported_not_raised(self):
        write(self.root, "cat.png")
        built = self.build()
        os.remove(os.path.join(self.root, "cat.png"))
        report = apply_module.apply_moves(built.moves)
        self.assertEqual(report.moved, [])
        self.assertEqual(len(report.failed), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
