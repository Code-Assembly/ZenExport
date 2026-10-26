"""Small Fusion-shaped fixtures for domain regression tests."""

from types import SimpleNamespace
import uuid


class Attributes:
    def __init__(self):
        self.values = {}
        self.writes = 0

    def itemByName(self, group, name):
        return self.values.get((group, name))

    def add(self, group, name, value):
        self.writes += 1
        item = SimpleNamespace(value=value)
        self.values[(group, name)] = item
        return item


class Body:
    def __init__(self, name, visible=True):
        self.name = name
        self.isVisible = visible
        self.nativeObject = None
        self.revisionId = "body-revision-1"
        self.entityToken = str(uuid.uuid4())


class Component:
    def __init__(self, name, bodies=()):
        self.name = name
        self.id = str(uuid.uuid4())
        self.revisionId = "component-revision-1"
        self.bRepBodies = list(bodies)
        self.occurrences = []
        self.attributes = Attributes()


class Occurrence:
    def __init__(self, component, path, visible=True, children=(), bodies=None):
        self.component = component
        self.fullPathName = path
        self.isVisible = visible
        self.childOccurrences = list(children)
        self.bRepBodies = component.bRepBodies if bodies is None else bodies
        self.transform2 = SimpleNamespace(asArray=lambda: [1.0, 0.0, 0.0, 0.0])


def design(root=None):
    return SimpleNamespace(rootComponent=root or Component("Root"), userParameters=[],
                           parentDocument=SimpleNamespace(name="Untitled", dataFile=None,
                                                          isValid=True))
