"""Read a Fusion assembly through duck-typed objects; no adsk import required."""

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import time
import uuid

from .config import ATTRIBUTE_GROUP
from .paths import NameAllocator


@dataclass
class ComponentTarget:
    folder: str
    component: object
    bodies: list = field(default_factory=list)
    names: NameAllocator = field(default_factory=NameAllocator)
    seen_bodies: dict = field(default_factory=dict)


@dataclass
class Snapshot:
    components: list
    fingerprint: str
    occurrences_visited: int
    capture_seconds: float = 0.0
    parts_collected: bool = True


def attribute(root, name):
    value = root.attributes.itemByName(ATTRIBUTE_GROUP, name)
    return value.value if value else None


def file_identity(document):
    data_file = document.dataFile
    return data_file.id if data_file else None


def resolve_context(design, store):
    root = design.rootComponent
    context_id = attribute(root, "ContextId")
    file_id = file_identity(design.parentDocument)
    # The local store wins over older paths embedded in earlier archive versions.
    context = store.get(context_id, file_id)
    if context:
        return context
    legacy_root = attribute(root, "LocalPath")
    if legacy_root:
        legacy_context = {"root": legacy_root, "name": attribute(root, "ProjectName") or root.name,
                          "context_id": context_id}
        if Path(legacy_root).is_dir():
            return legacy_context
    else:
        legacy_context = None
    recovered = store.find_legacy_context(design.parentDocument.name, root.revisionId)
    return recovered or legacy_context


def bind_context(design, store, root_folder, name, context_id=None):
    root = design.rootComponent
    context_id = context_id or attribute(root, "ContextId") or str(uuid.uuid4())
    # Bind before the first archive so a reopened v01 already carries its identity.
    for key, value in (("ContextId", context_id), ("LocalPath", str(Path(root_folder).resolve())),
                       ("ProjectName", name)):
        if attribute(root, key) != value:
            if not root.attributes.add(ATTRIBUTE_GROUP, key, value):
                raise RuntimeError(f"Unable to bind design attribute {key}")
    store.bind(context_id, str(Path(root_folder).resolve()), name,
               file_identity(design.parentDocument))
    return context_id


def capture_snapshot(design, include_parts=True):
    """Union visible instances into a unique native part library.

    STL files use native component coordinates. Assembly placement lives in the
    full-design STEP/F3D. Occurrence proxies are used to test effective visibility.
    The fingerprint is diagnostic; it never authorizes skipping a backup.
    """
    started = time.perf_counter()
    folders = NameAllocator()
    targets = {}
    components = []
    state = []
    visited = 0

    def target_for(component):
        # External revisions/copies can share an ID: compare actual API entities.
        bucket = targets.setdefault(component.id, [])
        for candidate in bucket:
            if candidate.component == component:
                return candidate
        target = ComponentTarget(folders.allocate(component.name), component)
        bucket.append(target)
        components.append(target)
        state.append(["component", component.id, component.name, component.revisionId])
        return target

    def add_bodies(target, bodies):
        for body in bodies:
            native = body.nativeObject or body
            body_name, revision = native.name, native.revisionId
            visible = body.isVisible
            state.append(["body", target.folder, body_name, revision, visible])
            # Names/revisions narrow the search; API entity equality decides identity.
            # Autodesk explicitly forbids using token string equality as entity identity.
            bucket = target.seen_bodies.setdefault((body_name, revision), [])
            if visible and not any(native == previous for previous in bucket):
                bucket.append(native)
                target.bodies.append((target.names.allocate(native.name), native))

    root = design.rootComponent
    root_target = target_for(root)
    if include_parts:
        add_bodies(root_target, root.bRepBodies)
    stack = list(reversed(list(root.occurrences))) if include_parts else []
    while stack:
        occurrence = stack.pop()
        visited += 1
        state.append(["occurrence", occurrence.fullPathName, occurrence.isVisible,
                      occurrence.transform2.asArray()])
        if not occurrence.isVisible:
            continue
        target = target_for(occurrence.component)
        add_bodies(target, occurrence.bRepBodies)
        stack.extend(reversed(list(occurrence.childOccurrences)))
    state.extend(["parameter", p.name, p.expression, p.value] for p in (design.userParameters or ()))
    fingerprint = hashlib.sha256(json.dumps(state, ensure_ascii=False, sort_keys=True,
                                            allow_nan=False).encode("utf-8")).hexdigest()
    return Snapshot(components, fingerprint, visited, time.perf_counter() - started, include_parts)
