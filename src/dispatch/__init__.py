import os
import os.path
from subprocess import check_output


try:
    VERSION = __import__("pkg_resources").get_distribution("dispatch").version
except Exception:
    VERSION = "unknown"

# sometimes we pull version info before dispatch is totally installed
from dispatch.job.models import Job  # noqa lgtm[py/unused-import]
from dispatch.worker.models import Worker  # noqa lgtm[py/unused-import]
from dispatch.team.models import Team  # noqa lgtm[py/unused-import]
from dispatch.location.models import Location  # noqa lgtm[py/unused-import]
from dispatch.event.models import Event  # noqa lgtm[py/unused-import]

from dispatch.service.models import Service  # noqa lgtm[py/unused-import]
from dispatch.tag.models import Tag  # noqa lgtm[py/unused-import]
from dispatch.plugin.models import Plugin  # noqa lgtm[py/unused-import]


def _get_git_revision(path):
    if not os.path.exists(os.path.join(path, ".git")):
        return None
    try:
        revision = check_output(["git", "rev-parse", "HEAD"], cwd=path, env=os.environ)
    except Exception:
        # binary didn't exist, wasn't on path, etc
        return None
    return revision.decode("utf-8").strip()


def get_revision():
    """
    :returns: Revision number of this branch/checkout, if available. None if
        no revision number can be determined.
    """
    if "DISPATCH_BUILD" in os.environ:
        return os.environ["DISPATCH_BUILD"]
    package_dir = os.path.dirname(__file__)
    checkout_dir = os.path.normpath(os.path.join(package_dir, os.pardir, os.pardir))
    path = os.path.join(checkout_dir)
    if os.path.exists(path):
        return _get_git_revision(path)
    return None


def get_version():
    if __build__:
        return f"{__version__}.{__build__}"
    return __version__


def is_docker():
    # One of these environment variables are guaranteed to exist
    # from our official docker images.
    # DISPATCH_VERSION is from a tagged release, and DISPATCH_BUILD is from a
    # a git based image.
    return "DISPATCH_VERSION" in os.environ or "DISPATCH_BUILD" in os.environ


__version__ = VERSION
__build__ = get_revision()
