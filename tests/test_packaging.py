"""The packaging metadata and the publish workflow, held to their contracts.

Neither is exercised by anything else. ``make check-install`` proves the wheel
installs, but nothing proves the **sdist** carries what an unpacked copy needs;
and ``.github/workflows/publish.yml`` runs only on a ``v*`` tag, so its first
execution is the release itself — a workflow with no local gate is a release
mechanism nobody has ever tested (`R1`). These assertions are that gate.

Text over a YAML parser on purpose: PyYAML is not a declared dependency of this
repo, and a guard that needs an undeclared import is a guard that can vanish.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
PUBLISH = ROOT / ".github" / "workflows" / "publish.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"

REPO_URL = "https://github.com/kkollsga/microbiomekg"


def metadata() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# pyproject: the URLs a PyPI page shows, and what the sdist carries
# --------------------------------------------------------------------------


def test_project_urls_point_at_the_repository():
    """A PyPI page with no links is a dead end for the reader it is for."""
    urls = metadata()["project"]["urls"]
    assert urls["Homepage"] == REPO_URL
    assert urls["Repository"] == REPO_URL
    assert urls["Changelog"].startswith(REPO_URL)
    assert urls["Issues"] == f"{REPO_URL}/issues"
    # The RTD slug is an assumption until the project exists (§5); the scheme
    # and host are not.
    assert urls["Documentation"].startswith("https://")
    assert "readthedocs.io" in urls["Documentation"]


#: Every repo-root file a test module opens through ``ROOT / "<name>"``. An
#: unpacked sdist puts ``tests/`` back at the root, so a root file the tests
#: read and the sdist omits makes those tests fail there — which is how
#: ``blueprint.json`` came to be missing: the composition-drift gate could not
#: run from an sdist at all.
def root_files_the_tests_read() -> set[str]:
    pattern = re.compile(r'ROOT\s*/\s*"([^"/]+\.[a-z]+)"')
    found: set[str] = set()
    for module in (ROOT / "tests").glob("*.py"):
        found |= set(pattern.findall(module.read_text(encoding="utf-8")))
    assert found, "the scan found no ROOT-anchored files — it would pass vacuously"
    return found


def test_the_sdist_carries_every_root_file_the_tests_read():
    include = metadata()["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    # Development-only roots the sdist deliberately omits: the adapter mirror
    # is a checkout concern, not a source-distribution one (see the comment in
    # pyproject.toml), and its tests are the only readers.
    development_only = {"Makefile"}
    missing = root_files_the_tests_read() - set(include) - development_only
    assert not missing, (
        f"the sdist omits root files the tests open: {sorted(missing)} — "
        "add them to [tool.hatch.build.targets.sdist].include"
    )


def test_the_sdist_carries_the_changelog():
    """The one file a packager looks for that no test opens."""
    include = metadata()["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert "CHANGELOG.md" in include


# --------------------------------------------------------------------------
# publish.yml — the workflow whose first run is the release
# --------------------------------------------------------------------------


def jobs(text: str) -> dict[str, str]:
    """``{job id: its block}``, split on the two-space-indented job keys."""
    body = text.split("\njobs:\n", 1)[1]
    starts = [
        (m.start(), m.group(1)) for m in re.finditer(r"^  (\w[\w-]*):$", body, re.M)
    ]
    assert starts, "no jobs found in the workflow"
    out = {}
    for i, (pos, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(body)
        out[name] = body[pos:end]
    return out


def test_publish_fires_on_a_tag_and_never_on_a_branch():
    text = PUBLISH.read_text(encoding="utf-8")
    trigger = text.split("\npermissions:", 1)[0].split("\non:\n", 1)[1]
    assert 'tags: ["v*"]' in trigger
    assert "branches" not in trigger, "a branch push must not be able to publish"
    assert "workflow_dispatch" not in trigger, "a manual run must not publish"


def test_publish_has_three_jobs_and_only_the_upload_holds_the_token():
    text = PUBLISH.read_text(encoding="utf-8")
    blocks = jobs(text)
    assert set(blocks) == {"build", "publish", "verify"}, sorted(blocks)
    holders = [name for name, block in blocks.items() if "id-token: write" in block]
    assert holders == ["publish"], (
        f"only the upload job may request the OIDC token; got {holders}"
    )
    assert "pypa/gh-action-pypi-publish@release/v1" in blocks["publish"]
    # No `environment:` anywhere — the PyPI pending publisher must then be
    # created with its environment field EMPTY, or the upload is rejected.
    # Comments are stripped first: this file *explains* both keys, and an
    # assertion the explanation satisfies is comment subsumption (R1).
    directives = [
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    ]
    assert not [line for line in directives if "environment:" in line]
    assert not [line for line in directives if "continue-on-error" in line]


def test_the_build_job_asserts_both_artifacts_exist():
    """R9: an upload step with no fail-on-empty can upload nothing."""
    build = jobs(PUBLISH.read_text(encoding="utf-8"))["build"]
    assert "dist/*.whl" in build and "dist/*.tar.gz" in build
    assert "set -euo pipefail" in build
    assert "if-no-files-found: error" in build


def test_the_verification_job_installs_the_published_artifact():
    """Not the built one, and not inside a checkout that could shadow it."""
    verify = jobs(PUBLISH.read_text(encoding="utf-8"))["verify"]
    assert "actions/checkout" not in verify
    assert 'pip install "microbiomekg==${tag}"' in verify
    assert "microbiomekg status --data" in verify
    # The artifact SET on the index, not just a version that answers.
    assert "bdist_wheel" in verify and "sdist" in verify


def test_ci_and_publish_agree_on_the_default_branch():
    """CI gates `main`; publish gates tags. A rename that missed one would
    leave a branch ungated or a tag unpublishable."""
    assert "branches: [main]" in CI.read_text(encoding="utf-8")
