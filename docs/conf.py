# Sphinx configuration — the same stack as the kglite siblings (furo,
# myst-parser, sphinx-autoapi, sphinx-copybutton) so the estate has one.
# `make docs` builds with -W: a warning is a broken cross-reference or a
# docstring that no longer parses, and a build that tolerates warnings
# tolerates rot.

project = "MicrobiomeKG"
copyright = "2026, Kristian dF Kollsgård"
author = "Kristian dF Kollsgård"

extensions = [
    "myst_parser",
    "sphinx.ext.napoleon",
    "sphinx_copybutton",
    "autoapi.extension",
]

# A NamedTuple's `Attributes:` section and autoapi's own attribute entries
# would describe each field twice; ivar fields describe them once, inline.
napoleon_use_ivar = True

# -- MyST (Markdown) settings ------------------------------------------------

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
]
myst_heading_anchors = 6

# -- API reference, generated from the package's docstrings -----------------

autoapi_dirs = ["../microbiomekg"]
autoapi_type = "python"
autoapi_options = [
    "members",
    "undoc-members",
    "show-inheritance",
    "show-module-summary",
]
autoapi_add_toctree_entry = True
autoapi_keep_files = False
autoapi_python_class_content = "both"
autoapi_member_order = "groupwise"
# The preps are scripts with a main(); their reference value is the module
# docstring, which autoapi renders from the source without importing.

# -- General settings ---------------------------------------------------------

# `claims/` are the claim-gate sidecars for the pages beside them, parsed by
# tests/skill_claims.py — annotations, not documentation.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "claims"]
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# The Cypher snippets use a Pygments lexer that does not recognise every
# kglite expression; keep that presentation-only warning narrow so -W stays
# useful. autoapi's import-resolution warnings are the same class: a
# `from microbiomekg import x` it cannot follow statically is not a broken doc.
suppress_warnings = ["misc.highlighting_failure", "autoapi.python_import_resolution"]

# -- HTML output --------------------------------------------------------------

html_theme = "furo"
html_title = "MicrobiomeKG"
