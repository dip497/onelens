"""Pydantic models matching the JSON export schema from the IntelliJ plugin."""

from pydantic import BaseModel


class ProjectInfo(BaseModel):
    name: str
    basePath: str
    jdkVersion: str = ""


class ClassData(BaseModel):
    fqn: str
    name: str
    kind: str
    modifiers: list[str] = []
    filePath: str
    lineStart: int
    lineEnd: int = 0
    packageName: str = ""
    enclosingClass: str | None = None
    superClass: str | None = None
    interfaces: list[str] = []


class MethodData(BaseModel):
    fqn: str
    name: str
    classFqn: str
    returnType: str = ""
    modifiers: list[str] = []
    isConstructor: bool = False
    filePath: str = ""
    lineStart: int = 0
    lineEnd: int = 0


class FieldData(BaseModel):
    fqn: str
    name: str
    classFqn: str
    type: str
    modifiers: list[str] = []
    filePath: str = ""
    lineStart: int = 0


class CallEdge(BaseModel):
    callerFqn: str
    calleeFqn: str
    line: int = 0
    filePath: str = ""


class InheritanceEdge(BaseModel):
    childFqn: str
    parentFqn: str
    relationType: str


class ExportDocument(BaseModel):
    version: str
    exportType: str
    timestamp: str
    project: ProjectInfo
    classes: list[ClassData] = []
    methods: list[MethodData] = []
    fields: list[FieldData] = []
    callGraph: list[CallEdge] = []
    inheritance: list[InheritanceEdge] = []
