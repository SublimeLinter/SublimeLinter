"""This module exports the NodeLinter subclass of Linter."""

import logging

from ..linter import Linter

from .manifest_linter_mixin import ManifestLinterMixin


logger = logging.getLogger(__name__)


class NodeLinter(ManifestLinterMixin, Linter):
    """
    This Linter subclass provides NodeJS-specific functionality.

    Linters installed with npm should inherit from this class.
    By doing so, they not only automatically get the features in
    the ManifestLinterMixin, but also the following features:

    """

    def __init__(self, view, settings):
        """Initialize a new NodeLinter instance."""
        super().__init__(view, settings)

        self.manifest_register_executable_check(self.executable_disable_if_not_dependency)

        self.manifest_init(logger, manifest='package.json', bin_path='node_modules/.bin/')

    def executable_disable_if_not_dependency(self, cmd):
        if self.get_view_settings().get('disable_if_not_dependency', False):
            logger.info(
                "Skipping '{}' since it is not installed locally.\n"
                "You can change this behavior by setting 'disable_if_not_dependency' to 'false'."
                .format(self.name)
            )
            self.notify_unassign()
            raise linter.PermanentError('disable_if_not_dependency')

        return False, None
