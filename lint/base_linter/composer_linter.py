"""This module exports the ComposerLinter subclass of Linter."""

import logging

from ..linter import Linter

from .manifest_linter_mixin import ManifestLinterMixin


logger = logging.getLogger(__name__)


class ComposerLinter(ManifestLinterMixin, Linter):
    """
    This Linter subclass provides composer-specific functionality.

    Linters installed with composer should inherit from this class.
    By doing so, they not only automatically get the features in the
    ManifestLinterMixin, but also the following features:

    """

    def __init__(self, view, settings):
        """Initialize a new ComposerLinter instance."""
        super().__init__(view, settings)

        self.manifest_init(logger, manifest='composer.json', bin_path='vendor/bin/')
