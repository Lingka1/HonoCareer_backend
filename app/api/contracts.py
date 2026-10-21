"""Typed contracts; rendered in OpenAPI and used at the service boundary."""
from typing import Annotated, Generic, Literal, TypeVar
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Short = Annotated[str, Field(min_length=1, max_length=120)]
Text = Annotated[str, Field(min_length=1, max_length=10000)]
Password = Annotated[str, StringConstraints(strip_whitespace=False), Field(min_length=8,max_length=128)]
Scene = Literal['employment','volunteer','club']
Stage = Literal['opening','self_introduction','experience_followup','situational_questions','candidate_questions','review']
DimensionKey = Literal['expression_clarity','logic','role_match','adaptability']
T = TypeVar('T')

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class R(BaseModel, Generic[T]):
    code: int | str = 0
    message: str = 'ok'
    data: T
    requestId: str

class Page(BaseModel, Generic[T]):
    items: list[T]
    nextCursor: str | None
    hasMore: bool

class RegisterDTO(Contract):
    account: Annotated[str, Field(min_length=3, max_length=120)]
    password: Password
    nickname: Annotated[str, Field(min_length=1, max_length=40)] = '新同学'

class LoginDTO(Contract):
    account: Short
    password: Annotated[str, StringConstraints(strip_whitespace=False), Field(min_length=1,max_length=128)]
    clientType: Literal['harmonyos','android','ios','web'] = 'harmonyos'

class RefreshDTO(Contract):
    refreshToken: Annotated[str, Field(min_length=20, max_length=256)]

class NonEmptyPatch(Contract):
    @model_validator(mode='after')
    def not_empty(self):
        fields = self.model_fields_set - {'version'}
        if not fields or any(getattr(self, x) is None for x in fields):
            raise ValueError('至少提供一个非空的可修改字段')
        return self

class UserPatchDTO(NonEmptyPatch):
    nickname: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    avatarUrl: Annotated[str, Field(max_length=2048, pattern=r'^https://')] | None = None

class BaseInfo(Contract):
    name: Annotated[str, Field(max_length=60)] | None = None
    school: Annotated[str, Field(max_length=120)] | None = None
    department: Annotated[str, Field(max_length=120)] | None = None
    major: Annotated[str, Field(max_length=120)] | None = None
    degree: Annotated[str, Field(max_length=40)] | None = None
    grade: Annotated[str, Field(max_length=40)] | None = None
    enrollmentYear: Annotated[int, Field(ge=1950, le=2100)] | None = None
    expectedGraduationYear: Annotated[int, Field(ge=1950, le=2100)] | None = None

class EmploymentDetail(Contract):
    targetRole: Annotated[str, Field(max_length=120)] = ''
    roleDirection: Annotated[str, Field(max_length=120)] = ''
    targetCompany: Annotated[str, Field(max_length=120)] = ''
    targetIndustry: Annotated[str, Field(max_length=120)] = ''
    expectedSalary: Annotated[str, Field(max_length=80)] = ''
    availableStartDate: Annotated[str, Field(max_length=30)] = ''
    skills: list[Short] = Field(default_factory=list, max_length=50)
    certificates: list[Short] = Field(default_factory=list, max_length=50)
    projectExperience: list[Text] = Field(default_factory=list, max_length=20)
    internshipExperience: list[Text] = Field(default_factory=list, max_length=20)

class VolunteerDetail(Contract):
    activityType: Annotated[str, Field(max_length=120)] = ''
    availableTime: Annotated[str, Field(max_length=120)] = ''
    volunteerExperience: list[Text] = Field(default_factory=list, max_length=20)
    relevantSkills: list[Short] = Field(default_factory=list, max_length=50)
    motivation: Annotated[str, Field(max_length=2000)] = ''

class ClubDetail(Contract):
    targetClub: Annotated[str, Field(max_length=120)] = ''
    clubDescription: Annotated[str, Field(max_length=2000)] = ''
    requirements: Annotated[str, Field(max_length=2000)] = ''
    interests: list[Short] = Field(default_factory=list, max_length=50)
    relevantExperience: list[Text] = Field(default_factory=list, max_length=20)
    motivation: Annotated[str, Field(max_length=2000)] = ''

DETAILS = {'employment':EmploymentDetail,'volunteer':VolunteerDetail,'club':ClubDetail}

class ProfileCreateDTO(Contract):
    type: Scene
    displayName: Short
    baseInfo: BaseInfo = Field(default_factory=BaseInfo)
    detail: EmploymentDetail | VolunteerDetail | ClubDetail
    @model_validator(mode='before')
    @classmethod
    def select_detail(cls, values):
        if isinstance(values, dict) and values.get('type') in DETAILS:
            values = dict(values)
            values['detail'] = DETAILS[values['type']].model_validate(values.get('detail', {}))
        return values

class ProfilePatchDTO(NonEmptyPatch):
    version: Annotated[int, Field(ge=1)]
    displayName: Short | None = None
    baseInfo: BaseInfo | None = None
    detail: dict | None = Field(default=None, description='按既有 type 校验并合并 detail')

class Education(Contract):
    school: Short
    major: Annotated[str, Field(max_length=120)] = ''
    degree: Annotated[str, Field(max_length=60)] = ''
    startDate: Annotated[str, Field(max_length=30)] = ''
    endDate: Annotated[str, Field(max_length=30)] = ''

class Project(Contract):
    name: Short
    role: Annotated[str, Field(max_length=120)] = ''
    description: Annotated[str, Field(max_length=5000)] = ''

class ParsedContent(Contract):
    education: list[Education] = Field(default_factory=list, max_length=20)
    projects: list[Project] = Field(default_factory=list, max_length=30)
    skills: list[Short] = Field(default_factory=list, max_length=100)
    certificates: list[Short] = Field(default_factory=list, max_length=50)
    warnings: list[Short] = Field(default_factory=list, max_length=30)

class ParsedPatchDTO(NonEmptyPatch):
    education: list[Education] | None = Field(default=None, max_length=20)
    projects: list[Project] | None = Field(default=None, max_length=30)
    skills: list[Short] | None = Field(default=None, max_length=100)
    certificates: list[Short] | None = Field(default=None, max_length=50)

class ResumeImportDTO(Contract):
    resumeId: Short
    selectedFields: list[Literal['education','projects','skills','certificates']] = Field(min_length=1, max_length=4)

class SceneConfig(Contract):
    targetRole: Annotated[str, Field(max_length=120)] = ''
    jobDescription: Annotated[str, Field(max_length=12000)] = ''
    activityType: Annotated[str, Field(max_length=120)] = ''
    targetClub: Annotated[str, Field(max_length=120)] = ''
    clubDescription: Annotated[str, Field(max_length=2000)] = ''
    requirements: Annotated[str, Field(max_length=2000)] = ''

class SessionCreateDTO(Contract):
    mode: Literal['interview']
    scene: Scene
    sceneConfig: SceneConfig
    profileId: Short
    modality: Literal['text','voice'] = 'text'
    resumeId: Short | None = None
    clientSessionId: Short
    @model_validator(mode='after')
    def scene_required(self):
        name = {'employment':'targetRole','volunteer':'activityType','club':'targetClub'}[self.scene]
        if not getattr(self.sceneConfig, name):
            raise ValueError(f'{self.scene} 场景需要填写 {name}')
        return self

class SessionPatchDTO(NonEmptyPatch):
    title: Short | None = None
    modality: Literal['text','voice'] | None = None

class FinishDTO(Contract):
    reason: Literal['user_end','flow_complete'] = 'user_end'

class MessageCreateDTO(Contract):
    clientMessageId: Short
    kind: Literal['answer'] = 'answer'
    content: Text
    inputMode: Literal['text','voice'] = 'text'
    audioId: Short | None = None

class WeakPointDTO(Contract):
    dimensionKey: DimensionKey
    messageIds: list[Short] = Field(default_factory=list, max_length=50)
    note: Annotated[str, Field(max_length=2000)] = ''

class MemorySettingsDTO(Contract):
    enabled: bool

class Dimension(Contract):
    key: DimensionKey
    label: Short
    score: Annotated[int, Field(ge=0, le=100)]
    evidence: list[Short] = Field(max_length=100)
    strengths: list[Short] = Field(min_length=1, max_length=10)
    issues: list[Short] = Field(min_length=1, max_length=10)
    suggestions: list[Short] = Field(min_length=1, max_length=10)

class Scorecard(Contract):
    dimensions: list[Dimension] = Field(min_length=4, max_length=4)
    summary: Annotated[str, Field(min_length=1, max_length=2000)]
    actionItems: list[Short] = Field(min_length=1, max_length=10)

class MessageVO(Contract):
    messageId: str
    sessionId: str
    seq: int
    role: Literal['user','assistant']
    kind: Literal['answer','question','review']
    content: str
    inputMode: Literal['text','voice']
    stage: Stage
    createdAt: str
    audioId: str | None = None

class UserVO(Contract):
    userId: str
    nickname: str
    avatarUrl: str | None = None
    emailMasked: str
    createdAt: str

class UserRef(Contract):
    userId: str
    nickname: str

class RegisterVO(Contract):
    userId: str

class TokensVO(Contract):
    accessToken: str
    refreshToken: str
    expiresIn: int
    user: UserRef | None = None

class ProfileVO(ProfileCreateDTO):
    profileId: str
    completionStatus: Literal['ready','draft']
    version: int
    createdAt: str
    updatedAt: str

class ProfileMatchVO(ProfileVO):
    matchReason: str
    isRecommended: bool

class ResumeVO(Contract):
    resumeId: str
    fileName: str
    mimeType: str
    status: Literal['uploaded','queued','processing','review_required','confirmed','failed']
    createdAt: str
    updatedAt: str
    parsedContent: ParsedContent | None = None
    error: str | None = None

class ParseJobVO(Contract):
    jobId: str
    status: str

class ResumeParseVO(ParsedContent):
    status: str
    jobId: str | None
    error: str | None

class ResumeSnapshot(Contract):
    resumeId: str
    fileName: str
    parsedContent: ParsedContent

class SessionVO(Contract):
    sessionId: str
    title: str
    mode: Literal['interview']
    scene: Scene
    status: Literal['active','generating_report','completed','failed','cancelled']
    stage: Stage
    modality: Literal['text','voice']
    profileSnapshotVersion: int
    createdAt: str
    startedAt: str
    updatedAt: str
    endedAt: str | None
    reportId: str | None
    reportStatus: Literal['pending','ready','failed'] | None
    overallScore: int | None
    sceneConfig: SceneConfig | None = None
    profileSnapshot: ProfileVO | None = None
    resumeSnapshot: ResumeSnapshot | None = None
    firstPrompt: str | None = None
    messagesUrl: str | None = None
    activeResponseId: str | None = None

class FinishVO(Contract):
    status: Literal['generating_report','completed']
    reportId: str

class CancelVO(Contract):
    status: Literal['cancelled']
    cancelledAt: str

class MessageAcceptedVO(Contract):
    userMessageId: str
    responseId: str
    status: Literal['queued']

class ReportVO(Scorecard):
    reportId: str
    sessionId: str
    mode: Literal['interview']
    status: Literal['completed']
    overallScore: int
    weakPointTags: list[DimensionKey]
    evaluationSource: str
    generatedAt: str

class WeakPointVO(Contract):
    weakPointId: str
    sessionId: str
    mode: Literal['interview']
    dimensionKey: DimensionKey
    messageIds: list[str]
    note: str
    createdAt: str

class MemorySource(Contract):
    sessionId: str

class MemoryVO(Contract):
    memoryId: str
    content: str
    source: MemorySource
    createdAt: str

class ErrorVO(BaseModel):
    code: str
    message: str
    requestId: str
    details: list[dict[str,str]] | None = None
