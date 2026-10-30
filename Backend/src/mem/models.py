from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')

class TopicChange(Model):
    action: Literal['create','rename'] = 'create'
    ref: str
    title: str = Field(min_length=1,max_length=300)
    expected_revision: int | None = None

class DocumentChange(Model):
    action: Literal['create','replace','move'] = 'create'
    ref: str
    layer: Literal['L1','L2'] | None = None
    topic_refs: list[str] = Field(default_factory=list)
    title: str | None = None
    path: str
    markdown: str = ''
    expected_sha256: str | None = None
    source_refs: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_change(self):
        if self.action != 'create' and not self.expected_sha256:
            raise ValueError('expected_sha256 required')
        if self.action != 'move' and (not self.title or not self.layer or not self.topic_refs or not self.source_refs):
            raise ValueError('title, layer, topics and sources required')
        if len(self.markdown.encode()) > 1024*1024:
            raise ValueError('document too large')
        return self

class SourceDraft(Model):
    ref: str
    kind: Literal['inbox','session','artifact']
    origin_ref: str = Field(min_length=1,max_length=2000)
    relative_path: str | None = None
    expected_sha256: str | None = None
    excerpt: str = ''

    @model_validator(mode='after')
    def validate_source(self):
        if len(self.excerpt.encode()) > 65536:
            raise ValueError('excerpt exceeds 64 KiB')
        if self.kind != 'inbox' and not self.excerpt.strip():
            raise ValueError('evidence excerpt required')
        if self.kind == 'inbox' and (not self.relative_path or not self.expected_sha256):
            raise ValueError('inbox path and hash required')
        return self

class EventDraft(Model):
    ref: str
    topic_refs: list[str] = Field(min_length=1)
    kind: Literal['action','result','test','decision','change','correction']
    summary: str = Field(min_length=1,max_length=2000)
    details: str = ''
    occurred_at: str | None = None
    evidence_kind: Literal['user_reported','tool_observed']
    source_refs: list[str] = Field(min_length=1)
    corrects_event_id: str | None = None

    @model_validator(mode='after')
    def validate_correction(self):
        if (self.kind == 'correction') != bool(self.corrects_event_id):
            raise ValueError('correction requires its target; other events cannot correct')
        if self.occurred_at:
            from datetime import datetime
            value = datetime.fromisoformat(self.occurred_at)
            if value.tzinfo is None: raise ValueError('occurred_at requires timezone')
        return self

class InboxCompletion(Model):
    relative_path: str
    expected_sha256: str
    archive_filename: str
    outcome: Literal['recorded','no_memory']
    reason: str = ''

class MemoryPatch(Model):
    idempotency_key: str = Field(min_length=1,max_length=128)
    topics: list[TopicChange] = Field(default_factory=list)
    documents: list[DocumentChange] = Field(default_factory=list,max_length=20)
    events: list[EventDraft] = Field(default_factory=list,max_length=100)
    sources: list[SourceDraft] = Field(default_factory=list)
    close_inbox: list[InboxCompletion] = Field(default_factory=list)

class ApplyResult(Model):
    operation_id: str
    state: Literal['PREPARED','APPLIED','DONE']
    id_map: dict[str,str]
    document_etags: dict[str,str] = Field(default_factory=dict)
    archive_status: str = 'not_requested'
    index_dirty: bool = True

class SearchRequest(Model):
    query: str = Field(min_length=1,max_length=500)
    layers: list[Literal['L1','L2','L3']] | None = None
    topic_ids: list[str] | None = None
    limit: int = Field(default=20,ge=1,le=100)

    @field_validator('query')
    @classmethod
    def nonempty(cls,v):
        if not v.strip(): raise ValueError('query cannot be blank')
        return v

class ReadResult(Model):
    ref: str
    kind: str
    data: dict
    source_etag: str

class HealthReport(Model):
    ready: bool
    issues: list[dict] = Field(default_factory=list)
    source_revision: int = 0
    index_revision: int | None = None
    pending_operations: list[str] = Field(default_factory=list)

class SearchHit(Model):
    ref: str
    layer: str
    topic_ids: list[str]
    title: str
    snippet: str
    source_etag: str
    score: float
    record_status: str = 'active'
    latest_correction_ref: str | None = None
    effective_summary: str | None = None
    evidence_kind: str | None = None

class SearchPage(Model):
    items: list[SearchHit]
    index_revision: int

class IndexReport(Model):
    documents: int
    events: int
    source_revision: int
    invalid_sources: list[str] = Field(default_factory=list)
