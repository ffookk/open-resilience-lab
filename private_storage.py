"""Exclusive private writes for the guided and bundle workflows.

These POSIX helpers never follow destination-directory links and never replace
an existing output. Errors are deliberately free of paths and entered values.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import secrets
import stat


class StorageError(ValueError):
    """A fixed diagnostic safe to display without private path information."""


def require_private_storage():
    if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
            or os.open not in os.supports_dir_fd or os.link not in os.supports_dir_fd):
        raise StorageError("This workflow requires POSIX private directory and no-follow file operations.")


def _destination_parts(destination, root_name, suffix=None):
    require_private_storage()
    try:
        base = Path.cwd().resolve()
        supplied = Path(destination)
        if ".." in supplied.parts or "\x00" in str(supplied):
            raise ValueError
        absolute = supplied if supplied.is_absolute() else base / supplied
        relative = absolute.relative_to(base / root_name)
        if not relative.parts or (suffix is not None and relative.suffix.lower() != suffix):
            raise ValueError
        return base, (root_name, *relative.parts[:-1]), relative.name
    except (OSError, ValueError, RuntimeError):
        raise StorageError("Choose a new destination inside the required private directory with the expected file type.") from None


@contextmanager
def private_parent(destination, root_name, suffix=None, *, create=False):
    """Yield a held parent fd; missing parents are left untouched during preflight."""
    base, components, leaf = _destination_parts(destination, root_name, suffix)
    descriptors = []
    try:
        descriptor = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(descriptor)
        for component in components:
            try:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    yield None, leaf
                    return
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass  # Open and check a competing directory without following links.
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            descriptors.append(child)
            metadata = os.fstat(child)
            if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
                raise StorageError("Existing private directories must be owned by the current user and accessible only to that user.")
            descriptor = child
        yield descriptor, leaf
    except StorageError:
        raise
    except (OSError, ValueError, RuntimeError):
        raise StorageError("Unable to access the private destination safely. Check its directories and permissions locally.") from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def require_absent(parent, leaf):
    if parent is None:
        return
    try:
        os.stat(leaf, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise StorageError("The destination already exists. Choose a new destination; this workflow never overwrites output.")


def check_private_destination(destination, root_name, suffix=None):
    with private_parent(destination, root_name, suffix) as (parent, leaf):
        require_absent(parent, leaf)


def write_private_bytes(parent, name, payload):
    """Create and completely write a fixed private file under a held directory."""
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        os.unlink(name, dir_fd=parent)
        raise


def publish_private_bytes(parent, name, payload):
    """Publish a complete file with an exclusive hard link, never replacing a file."""
    temporary = ".pending-" + secrets.token_hex(16)
    created = False
    try:
        write_private_bytes(parent, temporary, payload)
        created = True
        os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
    finally:
        if created:
            os.unlink(temporary, dir_fd=parent)


def save_private_json(document, destination):
    try:
        with private_parent(destination, "private-input", ".json", create=True) as (parent, leaf):
            require_absent(parent, leaf)
            publish_private_bytes(parent, leaf, document.encode("utf-8"))
    except StorageError:
        raise
    except (OSError, ValueError, RuntimeError):
        raise StorageError("Unable to save the private plan. No existing output was overwritten.") from None
