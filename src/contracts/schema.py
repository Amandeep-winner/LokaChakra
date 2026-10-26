from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_validator
import re


class ReachabilityTier(int, Enum):
    TIER_1_CLOSE = 1        # Direct friend, regular contact
    TIER_2_WARM = 2         # Acquaintance or 2nd-degree via Tier 1
    TIER_3_COLD_TARGET = 3  # Target person / 3rd-degree


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    PENDING_HITL = "pending_hitl"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"


class ResolutionAction(str, Enum):
    AUTO_MERGE = "AUTO_MERGE"
    QUEUE_HITL = "QUEUE_HITL"
    CREATE_NEW_NODE = "CREATE_NEW_NODE"


class EntityType(str, Enum):
    PERSON = "Person"
    ORGANIZATION = "Organization"
    LOCATION = "Location"
    SKILL_DOMAIN = "SkillDomain"
    GOAL = "Goal"


class RelationType(str, Enum):
    KNOWS = "KNOWS"
    BATCHMATE_OF = "BATCHMATE_OF"
    ROOMMATE_OF = "ROOMMATE_OF"
    SIBLING_OF = "SIBLING_OF"
    WORKED_WITH = "WORKED_WITH"
    WORKS_AT = "WORKS_AT"
    STUDIED_AT = "STUDIED_AT"
    CO_AUTHORED_WITH = "CO_AUTHORED_WITH"
    LOCATED_IN = "LOCATED_IN"
    HAS_SKILL = "HAS_SKILL"


class ExtractedPerson(BaseModel):
    uid: UUID = Field(default_factory=uuid4)
    full_name: str = Field(..., min_length=2, description="Normalized full or partial name")
    aliases: List[str] = Field(default_factory=list)
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_handle: Optional[str] = None
    x_handle: Optional[str] = None
    current_org: Optional[str] = None
    current_role: Optional[str] = None
    alumni_orgs: List[str] = Field(default_factory=list)
    location_city: Optional[str] = None
    reachability_tier: ReachabilityTier = ReachabilityTier.TIER_2_WARM
    trust_score: float = Field(default=50.0, ge=0.0, le=100.0)
    responsiveness_note: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        digits = re.sub(r"\D", "", v)
        return digits[-10:] if len(digits) >= 10 else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().lower() if v else None


class ExtractedOrganization(BaseModel):
    name: str = Field(..., min_length=2)
    org_type: str = Field(default="company", description="company | college | club | fund")
    location_city: Optional[str] = None


class ExtractedEdge(BaseModel):
    source_name: str
    source_type: EntityType
    target_name: str
    target_type: EntityType
    relation_type: RelationType
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence_score: float = Field(default=0.8, ge=0.0, le=1.0)
    valid_from: Optional[str] = Field(default=None, description="YYYY-MM or YYYY-MM-DD")
    valid_to: Optional[str] = Field(default=None, description="Null if currently active")
    evidence_snippet: str = Field(..., description="Exact quote or reason from source")


class EpisodeExtractionResult(BaseModel):
    episode_id: UUID = Field(default_factory=uuid4)
    episode_hash: Optional[str] = None
    raw_transcript: str
    source_type: str = Field(default="voice_note", description="voice_note | text_note | csv_import")
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    persons: List[ExtractedPerson] = Field(default_factory=list)
    organizations: List[ExtractedOrganization] = Field(default_factory=list)
    edges: List[ExtractedEdge] = Field(default_factory=list)


class HITLEvidenceCard(BaseModel):
    card_id: UUID = Field(default_factory=uuid4)
    langgraph_thread_id: str
    action_type: str = Field(..., description="ENTITY_MERGE | HIDDEN_BRIDGE_DISCOVERY")
    subject_a_uid: Optional[UUID] = None
    subject_a_name: str
    subject_b_uid: Optional[UUID] = None
    subject_b_name: str
    proposed_relation: RelationType
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    evidence_summary: str
    source_urls: List[str] = Field(default_factory=list)
    status: VerificationStatus = VerificationStatus.PENDING_HITL
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResolutionResult(BaseModel):
    action: ResolutionAction
    matched_uid: Optional[UUID] = None
    confidence_score: float
    hitl_card: Optional[HITLEvidenceCard] = None


class PathStep(BaseModel):
    node_uid: str
    node_name: str
    node_type: str
    reachability_tier: Optional[int] = None
    trust_score: Optional[float] = None
    relation_to_next: Optional[str] = None
    edge_confidence: Optional[float] = None


class WarmPathResponse(BaseModel):
    target_query: str
    total_cost: float
    hop_count: int
    steps: List[PathStep]
    recommended_intro_script: str
