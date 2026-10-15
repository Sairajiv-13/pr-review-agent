from pr_review.diff import parse_diff

SINGLE_HUNK = """\
diff --git a/app.py b/app.py
index 1111111..2222222 100644
--- a/app.py
+++ b/app.py
@@ -1,3 +1,4 @@
 one
+two-new
 two
 three
"""

MULTI_HUNK = """\
diff --git a/app.py b/app.py
index 1111111..2222222 100644
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 a
-b
+B
@@ -10,2 +10,3 @@
 j
+k
 l
"""

DELETED_FILE = """\
diff --git a/old.py b/old.py
deleted file mode 100644
index 1111111..0000000
--- a/old.py
+++ /dev/null
@@ -1,2 +0,0 @@
-x
-y
"""

NEW_FILE = """\
diff --git a/new.py b/new.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+alpha
+beta
"""


def test_single_hunk_positions():
    files = parse_diff(SINGLE_HUNK)
    assert len(files) == 1
    f = files[0]
    assert f.path == "app.py"
    # Hunk header is position 1, then one line each after that.
    assert f.position_for_new_line(1) == 2
    assert f.position_for_new_line(2) == 3  # the added line
    assert f.position_for_new_line(3) == 4
    assert f.position_for_new_line(4) == 5
    assert f.position_for_new_line(99) is None


def test_added_lines_carry_new_numbers():
    f = parse_diff(SINGLE_HUNK)[0]
    added = f.added_lines()
    assert len(added) == 1
    assert added[0].content == "two-new"
    assert added[0].new_lineno == 2
    assert added[0].position == 3


def test_multi_hunk_positions_continue_counting():
    f = parse_diff(MULTI_HUNK)[0]
    assert len(f.hunks) == 2
    # First hunk: header 1, a=2, -b=3, +B=4.
    assert f.position_for_new_line(2) == 4
    # Second hunk header is position 5, j=6, +k=7, l=8.
    assert f.position_for_new_line(10) == 6
    assert f.position_for_new_line(11) == 7
    assert f.position_for_new_line(12) == 8


def test_deleted_file_has_no_new_lines():
    f = parse_diff(DELETED_FILE)[0]
    assert f.is_deleted is True
    assert f.new_path is None
    assert f.path == "old.py"
    assert f.added_lines() == []
    assert f.position_for_new_line(1) is None


def test_new_file_positions():
    f = parse_diff(NEW_FILE)[0]
    assert f.is_new is True
    assert f.old_path is None
    assert f.position_for_new_line(1) == 2
    assert f.position_for_new_line(2) == 3


def test_multiple_files_in_one_diff():
    files = parse_diff(SINGLE_HUNK + NEW_FILE)
    assert [f.path for f in files] == ["app.py", "new.py"]
    # Positions restart at 1 for each file.
    assert files[1].position_for_new_line(1) == 2
