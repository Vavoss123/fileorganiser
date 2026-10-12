"""Tests for the organiser engine. No GUI, no real Downloads folder."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Settings and journals go to a throwaway folder, never the real undo history.
_APPDATA = tempfile.TemporaryDirectory()
os.environ["LOCALAPPDATA"] = _APPDATA.name

from organiser import apply as apply_module
from organiser import auto, cleanup, config, duplicates, plan as plan_module, rules, scan, startup
from organiser import graph as graph_module


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

    def test_custom_rules_win(self):
        self.assertEqual(
            rules.destination_for("receipt.pdf", {"pdf": "Documents/Receipts"}),
            "Documents/Receipts",
        )

    def test_custom_rule_validation(self):
        self.assertEqual(rules.clean_rule(" .PDF ", "\\Documents\\Receipts\\"),
                         ("pdf", "Documents/Receipts"))
        for ext, folder in [("", "Docs"), ("pdf", ""), ("pdf", "../Elsewhere"),
                            ("pdf", "C:/Windows"), ("p df", "Docs"), ("pdf", "Do?cs")]:
            with self.assertRaises(ValueError, msg=(ext, folder)):
                rules.clean_rule(ext, folder)

    def test_custom_rule_folders_are_skipped_on_rescan(self):
        self.assertIn("Receipts", rules.known_destinations({"pdf": "Receipts"}))

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

    def test_freshly_changed_files_are_left_alone(self):
        old = write(self.root, "old.png")
        write(self.root, "arriving.mp4")
        os.utime(old, (1_000_000, 1_000_000))
        built = self.plan_for(settle_seconds=120)
        self.assertEqual([m.info.name for m in built.moves], ["old.png"])
        self.assertIn(os.path.join(self.root, "arriving.mp4"), [p for p, _ in built.skipped])

    def test_date_folders_split_photos_and_videos_only(self):
        import datetime
        when = datetime.datetime(2025, 3, 14, 12).timestamp()
        for name in ("cat.png", "clip.mp4", "notes.txt"):
            os.utime(write(self.root, name), (when, when))
        by_month = {m.info.name: m.bucket for m in self.plan_for(date_folders="month").moves}
        self.assertEqual(by_month, {"cat.png": "Pictures/2025/03",
                                    "clip.mp4": "Videos/2025/03",
                                    "notes.txt": "Documents"})
        by_year = {m.info.name: m.destination for m in self.plan_for(date_folders="year").moves}
        self.assertEqual(by_year["cat.png"],
                         os.path.join(self.root, "Pictures", "2025", "cat.png"))

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


class RecycleTests(unittest.TestCase):
    """The Recycle Bin itself is stubbed out; these test the safety checks."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        self.binned: list[str] = []

    def recycler(self, path):
        self.binned.append(os.path.basename(path))
        os.remove(path)

    def groups(self):
        return duplicates.find_duplicates(scan.scan(self.root).files)

    def test_redundant_copies_are_recycled_and_the_keeper_stays(self):
        write(self.root, "report.docx", b"same")
        write(self.root, "report - Copy.docx", b"same")
        report = cleanup.recycle_duplicates(self.groups(), recycler=self.recycler)
        self.assertEqual(self.binned, ["report - Copy.docx"])
        self.assertEqual(report.freed, 4)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "report.docx")))

    def test_nothing_is_recycled_if_the_keeper_changed(self):
        write(self.root, "report.docx", b"same")
        write(self.root, "report - Copy.docx", b"same")
        groups = self.groups()
        write(self.root, "report.docx", b"edited since the scan")
        report = cleanup.recycle_duplicates(groups, recycler=self.recycler)
        self.assertEqual(self.binned, [])
        self.assertEqual(len(report.failed), 1)

    def test_a_copy_edited_since_the_scan_is_spared(self):
        write(self.root, "report.docx", b"same")
        write(self.root, "report - Copy.docx", b"same")
        groups = self.groups()
        write(self.root, "report - Copy.docx", b"now different")
        cleanup.recycle_duplicates(groups, recycler=self.recycler)
        self.assertEqual(self.binned, [])


    def test_old_installers_are_found_by_age_and_extension(self):
        day = 86400
        now = 100 * day
        for name, age in [("old.exe", 45), ("new.msi", 3), ("old-photo.png", 90)]:
            when = now - age * day
            os.utime(write(self.root, name), (when, when))
        found = cleanup.old_installers(scan.scan(self.root).files, days=30, now=now)
        self.assertEqual([f.name for f in found], ["old.exe"])


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

    def test_journal_is_on_disk_before_the_run_finishes(self):
        write(self.root, "cat.png", b"image")
        write(self.root, "clip.mp4", b"video")
        seen: list[int] = []

        def progress(done, _total):
            journals = apply_module.list_journals()
            moves = apply_module.read_journal(journals[0])["moves"] if journals else []
            seen.append(len(moves))

        apply_module.apply_moves(self.build().moves, progress=progress)
        self.assertEqual(seen, [1, 2])

    def test_interrupted_run_can_still_be_undone(self):
        write(self.root, "cat.png", b"image")
        write(self.root, "clip.mp4", b"video")

        def crash(done, _total):
            if done == 1:
                raise KeyboardInterrupt  # stands in for a crash or power cut

        with self.assertRaises(KeyboardInterrupt):
            apply_module.apply_moves(self.build().moves, progress=crash)
        journal = apply_module.list_journals()[0]
        undone = apply_module.undo(journal)
        self.assertFalse(undone.failed)
        self.assertEqual(sorted(os.listdir(self.root)), ["cat.png", "clip.mp4"])

    def test_torn_last_line_is_ignored(self):
        write(self.root, "cat.png", b"image")
        report = apply_module.apply_moves(self.build().moves)
        with open(report.journal_path, "a", encoding="utf-8") as handle:
            handle.write('{"from": "half')
        self.assertFalse(apply_module.undo(report.journal_path).failed)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "cat.png")))

    def test_old_json_journals_still_undo(self):
        write(self.root, os.path.join("Pictures", "cat.png"), b"image")
        legacy = os.path.join(self.journals.name, "20250101-120000.json")
        with open(legacy, "w", encoding="utf-8") as handle:
            json.dump({
                "created": 0,
                "created_folders": [os.path.join(self.root, "Pictures")],
                "moves": [{"from": os.path.join(self.root, "cat.png"),
                           "to": os.path.join(self.root, "Pictures", "cat.png")}],
            }, handle)
        self.assertFalse(apply_module.undo(legacy).failed)
        self.assertEqual(os.listdir(self.root), ["cat.png"])

    def test_history_lists_undoable_runs_newest_first(self):
        write(self.root, "cat.png")
        first = apply_module.apply_moves(self.build().moves)
        os.utime(first.journal_path, (1_000_000, 1_000_000))
        write(self.root, "clip.mp4")
        write(self.root, "song.mp3")
        second = apply_module.apply_moves(self.build().moves)
        history = apply_module.run_history()
        self.assertEqual([run.path for run in history], [second.journal_path, first.journal_path])
        self.assertEqual(history[0].moves, 2)
        self.assertEqual(os.path.normcase(history[0].source_folder), os.path.normcase(self.root))

        apply_module.undo(first.journal_path)  # an older run, not the latest
        self.assertTrue(os.path.isfile(os.path.join(self.root, "cat.png")))
        self.assertEqual([run.path for run in apply_module.run_history()], [second.journal_path])

    def test_missing_source_is_reported_not_raised(self):
        write(self.root, "cat.png")
        built = self.build()
        os.remove(os.path.join(self.root, "cat.png"))
        report = apply_module.apply_moves(built.moves)
        self.assertEqual(report.moved, [])
        self.assertEqual(len(report.failed), 1)


class AutoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        self.settings = dict(config.DEFAULTS, folder=self.root)

    def test_auto_run_tidies_and_logs(self):
        os.utime(write(self.root, "cat.png"), (1_000_000, 1_000_000))
        write(self.root, "arriving.mp4")  # too fresh to touch
        report = auto.run(self.settings)
        self.assertEqual(len(report.moved), 1)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "Pictures", "cat.png")))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "arriving.mp4")))
        with open(auto.log_path(), encoding="utf-8") as handle:
            self.assertIn("1 file(s) moved", handle.read())
        self.assertFalse(apply_module.undo(report.journal_path).failed)

    def test_auto_run_with_a_missing_folder_does_nothing(self):
        self.settings["folder"] = os.path.join(self.root, "gone")
        self.assertIsNone(auto.run(self.settings))

    def test_startup_commands_run_windowless(self):
        self.assertTrue(startup.command_for("auto").endswith("--auto"))
        self.assertTrue(startup.command_for("tray").endswith("--tray"))
        self.assertNotIn('python.exe"', startup.command_for("auto").lower())

    def test_quiet_run_logs_nothing_when_there_is_nothing_to_do(self):
        def log_size():
            return os.path.getsize(auto.log_path()) if os.path.exists(auto.log_path()) else 0

        before = log_size()
        auto.run(self.settings, quiet=True)
        self.assertEqual(log_size(), before)

    @unittest.skipUnless(sys.platform == "win32", "Windows registry")
    def test_startup_entry_round_trip(self):
        name = "FileOrganiserTest-{}".format(os.getpid())
        self.addCleanup(startup.set_mode, "off", name)
        for mode in ("auto", "tray", "off"):
            startup.set_mode(mode, name)
            self.assertEqual(startup.current_mode(name), mode)

class GraphTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def graph_for(self, **kwargs):
        result = scan.scan(self.root, ignore_folders=set(rules.known_destinations()))
        built = plan_module.build_plan(result, date_folders="year")
        groups = duplicates.find_duplicates(result.files)
        return graph_module.build_graph(built, groups, **kwargs)

    def test_files_hang_off_their_destination_folder(self):
        write(self.root, "cat.png", b"cat")
        write(self.root, "model.blend")
        graph = self.graph_for()
        cat = graph.nodes[graph.index["file:" + os.path.normcase(os.path.join(self.root, "cat.png"))]]
        folder = graph.nodes[next(iter(cat.neighbours))]
        self.assertEqual(folder.kind, "folder")
        self.assertEqual(folder.group, "Pictures")
        self.assertIn("folder:apps/blender", graph.index)
        self.assertEqual(graph.nodes[graph.index["folder:apps"]].count, 1)
        self.assertEqual(graph.nodes[graph.index["root"]].count, 2)

    def test_duplicates_are_linked(self):
        write(self.root, "a.pdf", b"same")
        write(self.root, "a (1).pdf", b"same")
        graph = self.graph_for()
        self.assertEqual([e.kind for e in graph.edges].count("duplicate"), 1)
        self.assertEqual(sum(node.duplicate for node in graph.nodes), 2)
        self.assertEqual(
            [e.kind for e in self.graph_for(show_duplicates=False).edges].count("duplicate"), 0
        )

    def test_too_many_files_folds_the_biggest_folders(self):
        for index in range(5):
            write(self.root, "photo{}.jpg".format(index), str(index).encode())
        write(self.root, "notes.txt", b"n")
        graph = self.graph_for(max_files=3)
        self.assertFalse(graph.truncated)
        self.assertEqual(graph.collapsed, {"folder:pictures"})
        pictures = graph.nodes[graph.index["folder:pictures"]]
        self.assertTrue(pictures.collapsed)
        self.assertEqual((pictures.hidden, pictures.count), (5, 5))
        self.assertEqual([n.label for n in graph.nodes if n.kind == "file"], ["notes.txt"])

    def test_folding_hides_subfolders_and_unfolding_shows_them(self):
        write(self.root, "photo.jpg")
        write(self.root, "shot.dng", b"raw")
        folded = self.graph_for(collapsed={"folder:pictures"})
        self.assertNotIn("folder:pictures/raw", folded.index)
        self.assertEqual(folded.nodes[folded.index["folder:pictures"]].hidden, 2)
        opened = self.graph_for(collapsed=set())
        self.assertIn("folder:pictures/raw", opened.index)
        self.assertEqual(sum(n.kind == "file" for n in opened.nodes), 2)

    def test_folders_know_where_they_are_on_disk(self):
        write(self.root, "shot.dng", b"raw")
        graph = self.graph_for(collapsed=set())
        raw = graph.nodes[graph.index["folder:pictures/raw"]]
        self.assertEqual(raw.path, os.path.join(self.root, "Pictures", "Raw"))
        folded = self.graph_for(collapsed={"folder:pictures"})
        self.assertEqual(folded.nodes[folded.index["folder:pictures"]].path,
                         os.path.join(self.root, "Pictures"))

    def test_size_by_space_makes_big_files_bigger(self):
        write(self.root, "big.zip", b"x" * 100000)
        write(self.root, "small.zip", b"x")
        graph = self.graph_for(size_by="space")
        weight = {n.label: n.weight for n in graph.nodes}
        self.assertGreater(weight["big.zip"], weight["small.zip"] * 3)

    def test_simulation_settles(self):
        for index in range(40):
            write(self.root, "file{}.{}".format(index, ("jpg", "pdf", "zip", "mp3")[index % 4]),
                  str(index).encode())
        graph = self.graph_for()
        sim = graph_module.Simulation(graph)
        for _ in range(400):
            sim.step()
        self.assertFalse(sim.running)
        for node in graph.nodes:
            self.assertTrue(abs(node.x) < 1e5 and abs(node.y) < 1e5)
        # Files end up nearer their own folder than the far side of the graph.
        for edge in graph.edges:
            if edge.kind == "move":
                a, b = graph.nodes[edge.a], graph.nodes[edge.b]
                self.assertLess(((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
